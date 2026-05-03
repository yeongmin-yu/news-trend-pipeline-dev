from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg2.extras import RealDictCursor

from storage.db import get_connection


def insert_news_raw(articles: list[dict[str, Any]]) -> None:
    """수집된 뉴스 기사 목록을 news_raw 테이블에 삽입한다 (중복 URL은 무시)."""
    if not articles:
        return
    rows = [
        (
            article.get("provider"),
            article.get("domain", "ai_tech"),
            article.get("query"),
            article.get("source"),
            article.get("title"),
            article.get("summary") or article.get("description") or article.get("content"),
            article.get("url"),
            article.get("published_at"),
            article.get("ingested_at"),
        )
        for article in articles
        if article.get("url") and article.get("title")
    ]
    if not rows:
        return
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO news_raw (provider, domain, query, source, title, summary, url, published_at, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (provider, domain, url) DO NOTHING
                """,
                rows,
            )


def insert_keyword_trends(rows: list[dict[str, Any]]) -> None:
    """키워드 트렌드 집계 결과를 keyword_trends 테이블에 삽입한다."""
    if not rows:
        return
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO keyword_trends (provider, domain, window_start, window_end, keyword, keyword_count, processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        row.get("provider"),
                        row.get("domain", "ai_tech"),
                        row["window_start"],
                        row["window_end"],
                        row["keyword"],
                        row.get("keyword_count", row.get("count")),
                        row["processed_at"],
                    )
                    for row in rows
                ],
            )


def insert_keyword_relations(rows: list[dict[str, Any]]) -> None:
    """키워드 동시 출현 관계를 keyword_relations 테이블에 삽입한다."""
    if not rows:
        return
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO keyword_relations (
                    provider, domain, window_start, window_end,
                    keyword_a, keyword_b, cooccurrence_count, processed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        row.get("provider"),
                        row.get("domain", "ai_tech"),
                        row["window_start"],
                        row["window_end"],
                        row["keyword_a"],
                        row["keyword_b"],
                        row.get("cooccurrence_count", row.get("count")),
                        row["processed_at"],
                    )
                    for row in rows
                ],
            )


def insert_collection_metric(row: dict[str, Any]) -> None:
    """수집 사이클별 메트릭(요청·성공·기사 수 등)을 collection_metrics 테이블에 기록한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO collection_metrics (
                    provider, domain, query, window_start, window_end,
                    request_count, success_count, article_count,
                    duplicate_count, publish_count, error_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["provider"], row["domain"], row["query"],
                    row["window_start"], row["window_end"],
                    row.get("request_count", 0), row.get("success_count", 0),
                    row.get("article_count", 0), row.get("duplicate_count", 0),
                    row.get("publish_count", 0), row.get("error_count", 0),
                ),
            )


def replace_keyword_events(
    rows: list[dict[str, Any]],
    *,
    since: datetime,
    until: datetime,
    provider: str | None = None,
    domain: str | None = None,
) -> None:
    """지정 기간의 keyword_events를 삭제 후 새 데이터로 교체한다 (충돌 시 upsert)."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM keyword_events WHERE event_time >= %s AND event_time < %s AND (%s IS NULL OR provider = %s) AND (%s IS NULL OR domain = %s)",
                (since, until, provider, provider, domain, domain),
            )
            if rows:
                cursor.executemany(
                    """
                    INSERT INTO keyword_events (
                        provider, domain, keyword, event_time, window_start, window_end,
                        current_mentions, prev_mentions, growth, event_score, is_spike, detected_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (provider, domain, keyword, window_start)
                    DO UPDATE SET
                        current_mentions = EXCLUDED.current_mentions,
                        prev_mentions = EXCLUDED.prev_mentions,
                        growth = EXCLUDED.growth,
                        event_score = EXCLUDED.event_score,
                        is_spike = EXCLUDED.is_spike,
                        detected_at = EXCLUDED.detected_at
                    """,
                    [
                        (
                            row.get("provider", "naver"), row.get("domain", "ai_tech"),
                            row["keyword"], row["event_time"], row["window_start"], row["window_end"],
                            row["current_mentions"], row.get("prev_mentions", 0),
                            row["growth"], row["event_score"], row.get("is_spike", False),
                            row.get("detected_at", datetime.now(timezone.utc)),
                        )
                        for row in rows
                    ],
                )


def fetch_keyword_events(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    provider: str | None = None,
    domain: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """조건에 맞는 키워드 이벤트 목록을 최신순으로 반환한다."""
    conditions: list[str] = []
    params: list[Any] = []
    if since:
        conditions.append("event_time >= %s")
        params.append(since)
    if until:
        conditions.append("event_time < %s")
        params.append(until)
    if provider:
        conditions.append("provider = %s")
        params.append(provider)
    if domain:
        conditions.append("domain = %s")
        params.append(domain)
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT provider, domain, keyword, event_time, window_start, window_end,
               current_mentions, prev_mentions, growth, event_score, is_spike, detected_at
        FROM keyword_events
        {where_clause}
        ORDER BY event_time DESC, event_score DESC, keyword ASC
        LIMIT %s
    """
    params.append(limit)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())


def upsert_from_staging_news_raw() -> None:
    """stg_news_raw를 news_raw로 upsert하고 스테이징 테이블을 초기화한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH ranked AS (
                    SELECT
                        COALESCE(provider, 'naver') AS provider,
                        COALESCE(domain, 'ai_tech') AS domain,
                        query, source, title, summary, url, published_at,
                        COALESCE(ingested_at, NOW()) AS ingested_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY COALESCE(provider, 'naver'), COALESCE(domain, 'ai_tech'), url
                            ORDER BY COALESCE(ingested_at, NOW()) DESC, published_at DESC NULLS LAST, title DESC NULLS LAST
                        ) AS row_rank
                    FROM stg_news_raw
                    WHERE url IS NOT NULL
                )
                INSERT INTO news_raw (provider, domain, query, source, title, summary, url, published_at, ingested_at)
                SELECT provider, domain, query, source, title, summary, url, published_at, ingested_at
                FROM ranked
                WHERE row_rank = 1
                ON CONFLICT (provider, domain, url) DO UPDATE SET
                    query = EXCLUDED.query, source = EXCLUDED.source, title = EXCLUDED.title,
                    summary = EXCLUDED.summary, published_at = EXCLUDED.published_at, ingested_at = EXCLUDED.ingested_at;
                TRUNCATE stg_news_raw;
                """
            )


def upsert_from_staging_keywords() -> None:
    """stg_keywords를 keywords로 upsert하고 스테이징 테이블을 초기화한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH dedup AS (
                    SELECT COALESCE(article_provider, 'naver') AS article_provider,
                           COALESCE(article_domain, 'ai_tech') AS article_domain,
                           article_url, keyword,
                           MAX(keyword_count) AS keyword_count, MAX(processed_at) AS processed_at
                    FROM stg_keywords
                    GROUP BY article_provider, article_domain, article_url, keyword
                )
                INSERT INTO keywords (article_provider, article_domain, article_url, keyword, keyword_count, processed_at)
                SELECT article_provider, article_domain, article_url, keyword, keyword_count, processed_at
                FROM dedup
                ON CONFLICT (article_provider, article_domain, article_url, keyword)
                DO UPDATE SET keyword_count = EXCLUDED.keyword_count, processed_at = EXCLUDED.processed_at;
                TRUNCATE stg_keywords;
                """
            )


def upsert_from_staging_keyword_trends() -> None:
    """stg_keyword_trends를 keyword_trends로 upsert하고 스테이징 테이블을 초기화한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH dedup AS (
                    SELECT COALESCE(provider, 'naver') AS provider, COALESCE(domain, 'ai_tech') AS domain,
                           window_start, window_end, keyword,
                           SUM(keyword_count) AS keyword_count, MAX(processed_at) AS processed_at
                    FROM stg_keyword_trends
                    GROUP BY provider, domain, window_start, window_end, keyword
                )
                INSERT INTO keyword_trends (provider, domain, window_start, window_end, keyword, keyword_count, processed_at)
                SELECT provider, domain, window_start, window_end, keyword, keyword_count, processed_at
                FROM dedup
                ON CONFLICT (provider, domain, window_start, window_end, keyword)
                DO UPDATE SET keyword_count = EXCLUDED.keyword_count, processed_at = EXCLUDED.processed_at;
                TRUNCATE stg_keyword_trends;
                """
            )


def upsert_from_staging_keyword_relations() -> None:
    """stg_keyword_relations를 keyword_relations로 upsert하고 스테이징 테이블을 초기화한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH dedup AS (
                    SELECT COALESCE(provider, 'naver') AS provider, COALESCE(domain, 'ai_tech') AS domain,
                           window_start, window_end, keyword_a, keyword_b,
                           SUM(cooccurrence_count) AS cooccurrence_count, MAX(processed_at) AS processed_at
                    FROM stg_keyword_relations
                    GROUP BY provider, domain, window_start, window_end, keyword_a, keyword_b
                )
                INSERT INTO keyword_relations (provider, domain, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at)
                SELECT provider, domain, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at
                FROM dedup
                ON CONFLICT (provider, domain, window_start, window_end, keyword_a, keyword_b)
                DO UPDATE SET cooccurrence_count = EXCLUDED.cooccurrence_count, processed_at = EXCLUDED.processed_at;
                TRUNCATE stg_keyword_relations;
                """
            )


def aggregate_keyword_trends() -> None:
    """keywords 테이블을 시간 단위로 집계하여 keyword_trends에 upsert한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO keyword_trends (provider, domain, window_start, window_end, keyword, keyword_count, processed_at)
                SELECT
                    article_provider AS provider, article_domain AS domain,
                    date_trunc('hour', processed_at) AS window_start,
                    date_trunc('hour', processed_at) + interval '1 hour' AS window_end,
                    keyword, SUM(keyword_count) AS keyword_count, MAX(processed_at) AS processed_at
                FROM keywords
                GROUP BY article_provider, article_domain, date_trunc('hour', processed_at), keyword
                ON CONFLICT (provider, domain, window_start, window_end, keyword)
                DO UPDATE SET keyword_count = EXCLUDED.keyword_count, processed_at = EXCLUDED.processed_at;
                """
            )


def aggregate_keyword_relations() -> None:
    """기사별 키워드 쌍에서 동시 출현 관계를 집계하여 keyword_relations에 upsert한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT provider, domain, url FROM news_raw")
            articles = cursor.fetchall()
            for provider, domain, url in articles:
                cursor.execute(
                    "SELECT keyword, keyword_count FROM keywords WHERE article_provider = %s AND article_domain = %s AND article_url = %s",
                    (provider, domain, url),
                )
                kws = cursor.fetchall()
                if len(kws) < 2:
                    continue
                for i in range(len(kws)):
                    for j in range(i + 1, len(kws)):
                        a, count_a = kws[i]
                        b, count_b = kws[j]
                        if a == b:
                            continue
                        keyword_a, keyword_b = sorted([a, b])
                        cursor.execute(
                            """
                            INSERT INTO keyword_relations (provider, domain, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at)
                            VALUES (%s, %s, date_trunc('hour', NOW()), date_trunc('hour', NOW()) + interval '1 hour', %s, %s, %s, NOW())
                            ON CONFLICT (provider, domain, window_start, window_end, keyword_a, keyword_b)
                            DO UPDATE SET cooccurrence_count = keyword_relations.cooccurrence_count + EXCLUDED.cooccurrence_count, processed_at = NOW()
                            """,
                            (provider, domain, keyword_a, keyword_b, min(count_a, count_b)),
                        )


def cleanup_old_trends(days_to_keep: int = 30) -> None:
    """보존 기간이 지난 keyword_trends 레코드를 삭제한다."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM keyword_trends WHERE window_end < %s", (cutoff,))
