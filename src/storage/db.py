from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import psycopg2
from psycopg2 import Error
from psycopg2.extras import Json, RealDictCursor

from core.config import settings
from core.domains import DOMAIN_DEFINITIONS
from core.logger import get_logger
from processing.preprocessing import tokenize

_STOPWORD_SEED: tuple[str, ...] = (
    "기자",
    "뉴스",
    "이번",
    "관련",
    "통해",
    "대한",
    "경우",
    "이후",
    "당시",
    "이날",
    "사진",
    "정도",
    "발표",
    "계획",
    "진행",
    "기업",
    "시장",
    "기술",
    "정부",
    "국회",
    "기반",
    "확대",
    "지원",
    "글로벌",
    "지역",
    "공개",
    "강화",
    "전략",
    "운영",
    "활용",
    "최대",
    "규모",
    "핵심",
    "대비",
    "분야",
    "추진",
    "구축",
    "가능",
    "주요",
)

logger = get_logger(__name__)
_SCHEMA_INIT_LOCK_ID = 94721531
_SCHEMA_INIT_DONE = False


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(settings.postgres_dsn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database() -> None:
    schema_path = Path(__file__).with_name("models.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(schema_sql)
    logger.info("Database schema initialized")
    seed_initial_data()


def safe_initialize_database() -> None:
    global _SCHEMA_INIT_DONE
    if _SCHEMA_INIT_DONE:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (_SCHEMA_INIT_LOCK_ID,))
                acquired = bool(cursor.fetchone()[0])
                if not acquired:
                    logger.info("Database initialization skipped: schema lock busy")
                    return
                try:
                    cursor.execute("SET lock_timeout TO '2s'")
                    cursor.execute("SET statement_timeout TO '60s'")
                    schema_path = Path(__file__).with_name("models.sql")
                    schema_sql = schema_path.read_text(encoding="utf-8")
                    cursor.execute(schema_sql)
                finally:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_INIT_LOCK_ID,))
        logger.info("Database schema initialized")
        seed_initial_data()
        _SCHEMA_INIT_DONE = True
    except Error as exc:
        logger.warning("Database initialization skipped: %s", exc)


def seed_initial_data() -> None:
    _seed_domain_catalog_and_queries()
    _seed_compound_nouns_from_file()
    _seed_stopwords()


def _seed_domain_catalog_and_queries() -> None:
    domain_rows = [
        (domain.id, domain.label, index + 1)
        for index, domain in enumerate(DOMAIN_DEFINITIONS)
    ]
    query_rows = [
        ("naver", domain.id, query, index + 1)
        for domain in DOMAIN_DEFINITIONS
        for index, query in enumerate(domain.query_keywords)
    ]
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO domain_catalog (domain_id, label, sort_order)
                VALUES (%s, %s, %s)
                ON CONFLICT (domain_id) DO UPDATE SET
                    label = EXCLUDED.label,
                    sort_order = EXCLUDED.sort_order,
                    is_active = TRUE
                """,
                domain_rows,
            )
            cursor.executemany(
                """
                INSERT INTO query_keywords (provider, domain_id, query, sort_order)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider, domain_id, query) DO UPDATE SET
                    sort_order = EXCLUDED.sort_order,
                    is_active = TRUE,
                    updated_at = NOW()
                """,
                query_rows,
            )


def fetch_domain_catalog() -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT domain_id AS id, label, is_active AS available
                FROM domain_catalog
                WHERE is_active = TRUE
                ORDER BY sort_order ASC, domain_id ASC
                """
            )
            return list(cursor.fetchall())


def fetch_active_query_keywords(provider: str = "naver") -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT provider, domain_id AS domain, query, sort_order
                FROM query_keywords
                WHERE provider = %s
                  AND is_active = TRUE
                ORDER BY domain_id ASC, sort_order ASC, query ASC
                """,
                (provider,),
            )
            return list(cursor.fetchall())


def fetch_all_query_keywords(provider: str = "naver") -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    q.id,
                    q.provider,
                    q.domain_id,
                    d.label AS domain_label,
                    q.query,
                    q.sort_order,
                    q.is_active,
                    q.created_at,
                    q.updated_at
                FROM query_keywords q
                JOIN domain_catalog d
                  ON d.domain_id = q.domain_id
                WHERE q.provider = %s
                ORDER BY d.sort_order ASC, q.sort_order ASC, q.query ASC
                """,
                (provider,),
            )
            return list(cursor.fetchall())


def fetch_query_keyword_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    query_keyword_id,
                    action,
                    before_json,
                    after_json,
                    actor,
                    acted_at
                FROM query_keyword_audit_logs
                ORDER BY acted_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())


def fetch_dictionary_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    entity_type,
                    entity_id,
                    action,
                    before_json,
                    after_json,
                    actor,
                    acted_at
                FROM dictionary_audit_logs
                ORDER BY acted_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())


def fetch_collection_metrics_summary(hours: int = 24, provider: str = "naver") -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    provider,
                    domain,
                    query,
                    SUM(request_count) AS request_count,
                    SUM(success_count) AS success_count,
                    SUM(article_count) AS article_count,
                    SUM(duplicate_count) AS duplicate_count,
                    SUM(publish_count) AS publish_count,
                    SUM(error_count) AS error_count,
                    MAX(window_end) AS last_seen_at
                FROM collection_metrics
                WHERE provider = %s
                  AND window_end >= NOW() - (%s || ' hours')::interval
                GROUP BY provider, domain, query
                ORDER BY domain ASC, article_count DESC, query ASC
                """,
                (provider, hours),
            )
            return list(cursor.fetchall())


def fetch_compound_nouns(domain: str = "all") -> list[str]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if domain == "all":
                cursor.execute("SELECT word FROM compound_noun_dict ORDER BY word")
            else:
                cursor.execute(
                    "SELECT word FROM compound_noun_dict WHERE domain = %s OR domain = 'all' ORDER BY word",
                    (domain,),
                )
            return [row[0] for row in cursor.fetchall()]


def fetch_compound_noun_item(item_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, word, domain, source, created_at
                FROM compound_noun_dict
                WHERE id = %s
                """,
                (item_id,),
            )
            return cursor.fetchone()


def fetch_stopwords(language: str = "ko", domain: str = "all") -> set[str]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if domain == "all":
                cursor.execute(
                    "SELECT word FROM stopword_dict WHERE language = %s",
                    (language,),
                )
            else:
                cursor.execute(
                    "SELECT word FROM stopword_dict WHERE language = %s AND (domain = %s OR domain = 'all')",
                    (language, domain),
                )
            return {row[0] for row in cursor.fetchall()}


def fetch_stopword_item(item_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, word, domain, language, created_at
                FROM stopword_dict
                WHERE id = %s
                """,
                (item_id,),
            )
            return cursor.fetchone()


def fetch_compound_candidate_item(item_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, word, domain, frequency, doc_count, first_seen_at, last_seen_at, status, reviewed_at, reviewed_by
                FROM compound_noun_candidates
                WHERE id = %s
                """,
                (item_id,),
            )
            return cursor.fetchone()


def update_compound_noun_domain(*, item_id: int, domain: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE compound_noun_dict SET domain = %s
                WHERE id = %s
                RETURNING id, word, domain, source, created_at
                """,
                (domain, item_id),
            )
            return cursor.fetchone()


def update_stopword_domain(*, item_id: int, domain: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE stopword_dict SET domain = %s
                WHERE id = %s
                RETURNING id, word, domain, language, created_at
                """,
                (domain, item_id),
            )
            return cursor.fetchone()


def fetch_dictionary_versions() -> dict[str, int]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT dict_name, version
                FROM dictionary_versions
                WHERE dict_name IN ('compound_noun_dict', 'stopword_dict')
                ORDER BY dict_name
                """
            )
            return {row[0]: int(row[1]) for row in cursor.fetchall()}


def log_dictionary_audit(
    *,
    entity_type: str,
    entity_id: int | None,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO dictionary_audit_logs (entity_type, entity_id, action, before_json, after_json, actor)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    entity_type,
                    entity_id,
                    action,
                    Json(_jsonable(before)) if before is not None else None,
                    Json(_jsonable(after)) if after is not None else None,
                    actor,
                ),
            )


def log_query_keyword_audit(
    *,
    query_keyword_id: int | None,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO query_keyword_audit_logs (query_keyword_id, action, before_json, after_json, actor)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    query_keyword_id,
                    action,
                    Json(_jsonable(before)) if before is not None else None,
                    Json(_jsonable(after)) if after is not None else None,
                    actor,
                ),
            )


def fetch_articles_for_extraction(since: datetime, until: datetime) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT title, summary
                FROM news_raw
                WHERE ingested_at >= %s AND ingested_at < %s
                ORDER BY ingested_at ASC
                """,
                (since, until),
            )
            return list(cursor.fetchall())


def upsert_compound_candidates(candidates: dict[str, tuple[int, int]], domain: str = "all") -> tuple[int, int]:
    if not candidates:
        return 0, 0

    now = datetime.now(timezone.utc)
    new_count = 0
    updated_count = 0

    insert_sql = """
        INSERT INTO compound_noun_candidates (word, domain, frequency, doc_count, first_seen_at, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (word, domain) DO NOTHING
    """
    update_sql = """
        UPDATE compound_noun_candidates
        SET frequency = frequency + %s,
            doc_count = doc_count + %s,
            last_seen_at = %s
        WHERE word = %s AND domain = %s AND status = 'pending'
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for word, (freq, doc_cnt) in candidates.items():
                cursor.execute(insert_sql, (word, domain, freq, doc_cnt, now, now))
                if cursor.rowcount > 0:
                    new_count += 1
                else:
                    cursor.execute(update_sql, (freq, doc_cnt, now, word, domain))
                    if cursor.rowcount > 0:
                        updated_count += 1

    return new_count, updated_count


def fetch_query_keyword_by_id(item_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    q.id,
                    q.provider,
                    q.domain_id,
                    d.label AS domain_label,
                    q.query,
                    q.sort_order,
                    q.is_active,
                    q.created_at,
                    q.updated_at
                FROM query_keywords q
                JOIN domain_catalog d
                  ON d.domain_id = q.domain_id
                WHERE q.id = %s
                """,
                (item_id,),
            )
            return cursor.fetchone()


def create_query_keyword(
    *,
    provider: str,
    domain_id: str,
    query: str,
    sort_order: int,
    actor: str,
) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO query_keywords (provider, domain_id, query, sort_order, is_active, updated_at)
                VALUES (%s, %s, %s, %s, TRUE, NOW())
                RETURNING id
                """,
                (provider, domain_id, query, sort_order),
            )
            row = cursor.fetchone()
    created = fetch_query_keyword_by_id(int(row["id"]))
    log_query_keyword_audit(
        query_keyword_id=int(row["id"]),
        action="create",
        before=None,
        after=created,
        actor=actor,
    )
    return created or {}


def update_query_keyword(
    *,
    item_id: int,
    domain_id: str,
    query: str,
    sort_order: int,
    is_active: bool,
    actor: str,
) -> dict[str, Any]:
    before = fetch_query_keyword_by_id(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE query_keywords
                SET domain_id = %s,
                    query = %s,
                    sort_order = %s,
                    is_active = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (domain_id, query, sort_order, is_active, item_id),
            )
    after = fetch_query_keyword_by_id(item_id)
    log_query_keyword_audit(
        query_keyword_id=item_id,
        action="update",
        before=before,
        after=after,
        actor=actor,
    )
    return after or {}


def delete_query_keyword(*, item_id: int, actor: str) -> None:
    before = fetch_query_keyword_by_id(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM query_keywords WHERE id = %s", (item_id,))
    log_query_keyword_audit(
        query_keyword_id=item_id,
        action="delete",
        before=before,
        after=None,
        actor=actor,
    )


def _seed_compound_nouns_from_file() -> None:
    dict_path = Path(__file__).resolve().parents[1] / "core" / "korean_user_dict.txt"
    if not dict_path.exists():
        return
    words = [
        line.strip()
        for line in dict_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not words:
        return
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO compound_noun_dict (word, domain, source)
                VALUES (%s, 'all', 'manual')
                ON CONFLICT (word, domain) DO NOTHING
                """,
                [(word,) for word in words],
            )


def _seed_stopwords() -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO stopword_dict (word, domain, language)
                VALUES (%s, 'all', 'ko')
                ON CONFLICT (word, domain, language) DO NOTHING
                """,
                [(word,) for word in _STOPWORD_SEED],
            )


def upsert_from_staging_news_raw() -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH ranked AS (
                    SELECT
                        COALESCE(provider, 'naver') AS provider,
                        COALESCE(domain, 'ai_tech') AS domain,
                        query,
                        source,
                        title,
                        summary,
                        url,
                        published_at,
                        COALESCE(ingested_at, NOW()) AS ingested_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                COALESCE(provider, 'naver'),
                                COALESCE(domain, 'ai_tech'),
                                url
                            ORDER BY
                                COALESCE(ingested_at, NOW()) DESC,
                                published_at DESC NULLS LAST,
                                title DESC NULLS LAST
                        ) AS row_rank
                    FROM stg_news_raw
                    WHERE url IS NOT NULL
                )
                INSERT INTO news_raw (provider, domain, query, source, title, summary, url, published_at, ingested_at)
                SELECT provider, domain, query, source, title, summary, url, published_at, ingested_at
                FROM ranked
                WHERE row_rank = 1
                ON CONFLICT (provider, domain, url) DO UPDATE SET
                    query = EXCLUDED.query,
                    source = EXCLUDED.source,
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    published_at = EXCLUDED.published_at,
                    ingested_at = EXCLUDED.ingested_at;
                TRUNCATE stg_news_raw;
                """
            )


def upsert_from_staging_keywords() -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH dedup AS (
                    SELECT
                        COALESCE(article_provider, 'naver') AS article_provider,
                        COALESCE(article_domain, 'ai_tech') AS article_domain,
                        article_url,
                        keyword,
                        MAX(keyword_count) AS keyword_count,
                        MAX(processed_at) AS processed_at
                    FROM stg_keywords
                    GROUP BY article_provider, article_domain, article_url, keyword
                )
                INSERT INTO keywords (article_provider, article_domain, article_url, keyword, keyword_count, processed_at)
                SELECT article_provider, article_domain, article_url, keyword, keyword_count, processed_at
                FROM dedup
                ON CONFLICT (article_provider, article_domain, article_url, keyword)
                DO UPDATE SET
                    keyword_count = EXCLUDED.keyword_count,
                    processed_at  = EXCLUDED.processed_at;
                TRUNCATE stg_keywords;
                """
            )


def upsert_from_staging_keyword_trends() -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH dedup AS (
                    SELECT
                        COALESCE(provider, 'naver') AS provider,
                        COALESCE(domain, 'ai_tech') AS domain,
                        window_start,
                        window_end,
                        keyword,
                        SUM(keyword_count) AS keyword_count,
                        MAX(processed_at) AS processed_at
                    FROM stg_keyword_trends
                    GROUP BY provider, domain, window_start, window_end, keyword
                )
                INSERT INTO keyword_trends (provider, domain, window_start, window_end, keyword, keyword_count, processed_at)
                SELECT provider, domain, window_start, window_end, keyword, keyword_count, processed_at
                FROM dedup
                ON CONFLICT (provider, domain, window_start, window_end, keyword)
                DO UPDATE SET
                    keyword_count = EXCLUDED.keyword_count,
                    processed_at = EXCLUDED.processed_at;
                TRUNCATE stg_keyword_trends;
                """
            )


def upsert_from_staging_keyword_relations() -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH dedup AS (
                    SELECT
                        COALESCE(provider, 'naver') AS provider,
                        COALESCE(domain, 'ai_tech') AS domain,
                        window_start,
                        window_end,
                        keyword_a,
                        keyword_b,
                        SUM(cooccurrence_count) AS cooccurrence_count,
                        MAX(processed_at) AS processed_at
                    FROM stg_keyword_relations
                    GROUP BY provider, domain, window_start, window_end, keyword_a, keyword_b
                )
                INSERT INTO keyword_relations (provider, domain, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at)
                SELECT provider, domain, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at
                FROM dedup
                ON CONFLICT (provider, domain, window_start, window_end, keyword_a, keyword_b)
                DO UPDATE SET
                    cooccurrence_count = EXCLUDED.cooccurrence_count,
                    processed_at = EXCLUDED.processed_at;
                TRUNCATE stg_keyword_relations;
                """
            )


def insert_news_raw(articles: list[dict[str, Any]]) -> None:
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
    if not rows:
        return
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO keyword_relations (
                    provider,
                    domain,
                    window_start,
                    window_end,
                    keyword_a,
                    keyword_b,
                    cooccurrence_count,
                    processed_at
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
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO collection_metrics (
                    provider,
                    domain,
                    query,
                    window_start,
                    window_end,
                    request_count,
                    success_count,
                    article_count,
                    duplicate_count,
                    publish_count,
                    error_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["provider"],
                    row["domain"],
                    row["query"],
                    row["window_start"],
                    row["window_end"],
                    row.get("request_count", 0),
                    row.get("success_count", 0),
                    row.get("article_count", 0),
                    row.get("duplicate_count", 0),
                    row.get("publish_count", 0),
                    row.get("error_count", 0),
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
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM keyword_events
                WHERE event_time >= %s
                  AND event_time < %s
                  AND (%s IS NULL OR provider = %s)
                  AND (%s IS NULL OR domain = %s)
                """,
                (since, until, provider, provider, domain, domain),
            )
            if rows:
                cursor.executemany(
                    """
                    INSERT INTO keyword_events (
                        provider,
                        domain,
                        keyword,
                        event_time,
                        window_start,
                        window_end,
                        current_mentions,
                        prev_mentions,
                        growth,
                        event_score,
                        is_spike,
                        detected_at
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
                            row["provider"],
                            row["domain"],
                            row["keyword"],
                            row["event_time"],
                            row["window_start"],
                            row["window_end"],
                            row["current_mentions"],
                            row["prev_mentions"],
                            row["growth"],
                            row["event_score"],
                            row["is_spike"],
                            row["detected_at"],
                        )
                        for row in rows
                    ],
                )


def fetch_keyword_event_rows(
    *,
    start_at: datetime,
    end_at: datetime,
    provider: str | None = None,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    provider,
                    domain,
                    keyword,
                    event_time,
                    window_start,
                    window_end,
                    current_mentions,
                    prev_mentions,
                    growth,
                    event_score,
                    is_spike,
                    detected_at
                FROM keyword_events
                WHERE event_time >= %s
                  AND event_time < %s
                  AND (%s IS NULL OR provider = %s)
                  AND (%s IS NULL OR domain = %s)
                ORDER BY event_time ASC, event_score DESC, keyword ASC
                """,
                (start_at, end_at, provider, provider, domain, domain),
            )
            return list(cursor.fetchall())


def fetch_news_raw_between(
    start_at: datetime,
    end_at: datetime,
    provider: str | None = None,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT provider, domain, query, source, title, summary, url, published_at, ingested_at
                FROM news_raw
                WHERE published_at >= %s
                  AND published_at < %s
                  AND (%s IS NULL OR provider = %s)
                  AND (%s IS NULL OR domain = %s)
                ORDER BY published_at ASC
                """,
                (start_at, end_at, provider, provider, domain, domain),
            )
            return list(cursor.fetchall())


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start_at = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    return start_at, start_at + timedelta(days=1)


def rebuild_keywords_for_date(
    target_date: date,
    provider: str | None = None,
    domain: str | None = None,
) -> dict[str, int]:
    start_at, end_at = _day_bounds(target_date)
    articles = fetch_news_raw_between(start_at, end_at, provider=provider, domain=domain)
    processed_at = datetime.now(timezone.utc)
    rows: list[tuple[str, str, str, str, int, datetime]] = []
    article_keys = [
        (article.get("provider"), article.get("domain"), article["url"])
        for article in articles
        if article.get("url")
    ]

    for article in articles:
        article_url = article.get("url")
        if not article_url:
            continue
        article_text = " ".join(part for part in [article.get("title"), article.get("summary")] if part)
        counts = Counter(tokenize(article_text, article.get("domain", "all")))
        rows.extend(
            (
                article.get("provider"),
                article.get("domain", "ai_tech"),
                article_url,
                keyword,
                count,
                processed_at,
            )
            for keyword, count in counts.items()
        )

    with get_connection() as conn:
        with conn.cursor() as cursor:
            if article_keys:
                cursor.executemany(
                    """
                    DELETE FROM keywords
                    WHERE article_provider = %s
                      AND article_domain = %s
                      AND article_url = %s
                    """,
                    article_keys,
                )
            if rows:
                cursor.executemany(
                    """
                    INSERT INTO keywords (article_provider, article_domain, article_url, keyword, keyword_count, processed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )

    return {"article_count": len(articles), "keyword_row_count": len(rows)}


def replace_keyword_trends(
    rows: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    provider: str | None = None,
    domain: str | None = None,
) -> None:
    values = [
        (
            row.get("provider", provider),
            row.get("domain", domain or "ai_tech"),
            row["window_start"],
            row["window_end"],
            row["keyword"],
            row["keyword_count"],
            row["processed_at"],
        )
        for row in rows
    ]
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM keyword_trends
                WHERE window_start >= %s
                  AND window_start < %s
                  AND (%s IS NULL OR provider = %s)
                  AND (%s IS NULL OR domain = %s)
                """,
                (window_start, window_end, provider, provider, domain, domain),
            )
            if values:
                cursor.executemany(
                    """
                    INSERT INTO keyword_trends (provider, domain, window_start, window_end, keyword, keyword_count, processed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    values,
                )


def rebuild_keyword_trends_for_date(
    target_date: date,
    provider: str | None = None,
    domain: str | None = None,
) -> dict[str, int]:
    start_at, end_at = _day_bounds(target_date)
    articles = fetch_news_raw_between(start_at, end_at, provider=provider, domain=domain)
    window_counts: defaultdict[tuple[str, str, datetime, datetime, str], int] = defaultdict(int)
    processed_at = datetime.now(timezone.utc)

    for article in articles:
        published_at = article.get("published_at")
        if not published_at:
            continue
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        normalized = published_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
        minute_bucket = normalized.minute - (normalized.minute % 10)
        bucket_start = normalized.replace(minute=minute_bucket)
        bucket_end = bucket_start + timedelta(minutes=10)
        article_text = " ".join(part for part in [article.get("title"), article.get("summary")] if part)
        for keyword, count in Counter(tokenize(article_text, article.get("domain", "all"))).items():
            window_counts[(article.get("provider"), article.get("domain", "ai_tech"), bucket_start, bucket_end, keyword)] += count

    rows = [
        {
            "provider": provider_name,
            "domain": domain_name,
            "window_start": item_window_start,
            "window_end": item_window_end,
            "keyword": keyword,
            "keyword_count": keyword_count,
            "processed_at": processed_at,
        }
        for (provider_name, domain_name, item_window_start, item_window_end, keyword), keyword_count in sorted(window_counts.items())
    ]
    replace_keyword_trends(rows, window_start=start_at, window_end=end_at, provider=provider, domain=domain)
    return {"article_count": len(articles), "trend_row_count": len(rows)}


def rebuild_keyword_relations_for_date(
    target_date: date,
    provider: str | None = None,
    domain: str | None = None,
) -> dict[str, int]:
    start_at, end_at = _day_bounds(target_date)
    articles = fetch_news_raw_between(start_at, end_at, provider=provider, domain=domain)
    relation_counts: defaultdict[tuple[str, str, datetime, datetime, str, str], int] = defaultdict(int)
    processed_at = datetime.now(timezone.utc)

    for article in articles:
        published_at = article.get("published_at")
        if not published_at:
            continue
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        normalized = published_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
        minute_bucket = normalized.minute - (normalized.minute % 10)
        bucket_start = normalized.replace(minute=minute_bucket)
        bucket_end = bucket_start + timedelta(minutes=10)
        article_text = " ".join(part for part in [article.get("title"), article.get("summary")] if part)
        keyword_counts = Counter(tokenize(article_text, article.get("domain", "all")))
        representative_keywords = [
            keyword
            for keyword, _ in sorted(keyword_counts.items(), key=lambda item: (-item[1], item[0]))[: settings.relation_keyword_limit]
        ]
        for index, keyword_a in enumerate(representative_keywords):
            for keyword_b in representative_keywords[index + 1 :]:
                relation_counts[(article.get("provider"), article.get("domain", "ai_tech"), bucket_start, bucket_end, keyword_a, keyword_b)] += 1

    rows = [
        {
            "provider": provider_name,
            "domain": domain_name,
            "window_start": item_window_start,
            "window_end": item_window_end,
            "keyword_a": keyword_a,
            "keyword_b": keyword_b,
            "count": relation_count,
            "processed_at": processed_at,
        }
        for (provider_name, domain_name, item_window_start, item_window_end, keyword_a, keyword_b), relation_count in sorted(relation_counts.items())
    ]

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM keyword_relations
                WHERE window_start >= %s
                  AND window_start < %s
                  AND (%s IS NULL OR provider = %s)
                  AND (%s IS NULL OR domain = %s)
                """,
                (start_at, end_at, provider, provider, domain, domain),
            )
            if rows:
                cursor.executemany(
                    """
                    INSERT INTO keyword_relations (
                        provider,
                        domain,
                        window_start,
                        window_end,
                        keyword_a,
                        keyword_b,
                        cooccurrence_count,
                        processed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            row["provider"],
                            row["domain"],
                            row["window_start"],
                            row["window_end"],
                            row["keyword_a"],
                            row["keyword_b"],
                            row["count"],
                            row["processed_at"],
                        )
                        for row in rows
                    ],
                )

    return {"article_count": len(articles), "relation_row_count": len(rows)}
