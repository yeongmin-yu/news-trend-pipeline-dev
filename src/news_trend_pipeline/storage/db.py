from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import psycopg2
from psycopg2 import Error
from psycopg2.extras import RealDictCursor

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.logger import get_logger
from news_trend_pipeline.processing.preprocessing import tokenize

_STOPWORD_SEED: tuple[str, ...] = (
    "기자", "뉴스", "이번", "지난", "통해", "대한", "관련", "위해",
    "대해", "경우", "이후", "이날", "오전", "오후", "사진", "정도",
    "가장", "때문", "지난해", "올해", "기사", "제공", "사용", "진행",
    "기준", "중심", "사업", "기업", "서비스", "시장", "기술", "최근",
    "예정", "대표", "이상", "이하", "모든", "부분", "현장", "내용",
    "결과", "발표", "계획", "설명",
)


logger = get_logger(__name__)


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
    try:
        initialize_database()
    except Error as exc:
        logger.warning("Database initialization skipped: %s", exc)


# ---------------------------------------------------------------------------
# 사전 CRUD
# ---------------------------------------------------------------------------

def fetch_compound_nouns() -> list[str]:
    """compound_noun_dict에서 승인된 복합명사 목록을 반환한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT word FROM compound_noun_dict ORDER BY word")
            return [row[0] for row in cursor.fetchall()]


def fetch_stopwords(language: str = "ko") -> set[str]:
    """stopword_dict에서 불용어 집합을 반환한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT word FROM stopword_dict WHERE language = %s",
                (language,),
            )
            return {row[0] for row in cursor.fetchall()}


def fetch_articles_for_extraction(since: datetime, until: datetime) -> list[dict[str, Any]]:
    """복합명사 후보 추출용 기사 목록을 ingested_at 범위로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT title, description, content
                FROM news_raw
                WHERE ingested_at >= %s AND ingested_at < %s
                ORDER BY ingested_at ASC
                """,
                (since, until),
            )
            return list(cursor.fetchall())


def upsert_compound_candidates(candidates: dict[str, tuple[int, int]]) -> tuple[int, int]:
    """복합명사 후보를 upsert한다.

    신규 단어는 INSERT, 이미 pending 상태인 단어는 frequency/doc_count 누적.
    approved/rejected 단어는 건드리지 않는다.
    Returns (new_count, updated_count).
    """
    if not candidates:
        return 0, 0

    now = datetime.now(timezone.utc)
    new_count = 0
    updated_count = 0

    insert_sql = """
        INSERT INTO compound_noun_candidates (word, frequency, doc_count, first_seen_at, last_seen_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (word) DO NOTHING
    """
    update_sql = """
        UPDATE compound_noun_candidates
        SET frequency    = frequency + %s,
            doc_count    = doc_count + %s,
            last_seen_at = %s
        WHERE word = %s AND status = 'pending'
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for word, (freq, doc_cnt) in candidates.items():
                cursor.execute(insert_sql, (word, freq, doc_cnt, now, now))
                if cursor.rowcount > 0:
                    new_count += 1
                else:
                    cursor.execute(update_sql, (freq, doc_cnt, now, word))
                    if cursor.rowcount > 0:
                        updated_count += 1

    return new_count, updated_count


def seed_initial_data() -> None:
    """초기 사전 데이터를 DB에 적재한다 (이미 존재하면 건너뜀).

    - compound_noun_dict: korean_user_dict.txt 내 단어
    - stopword_dict: 기본 한국어 불용어 목록
    """
    _seed_compound_nouns_from_file()
    _seed_stopwords()


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
                "INSERT INTO compound_noun_dict (word, source) VALUES (%s, 'manual') ON CONFLICT (word) DO NOTHING",
                [(w,) for w in words],
            )
    logger.info("Seeded %d compound nouns from user dict file", len(words))


def _seed_stopwords() -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO stopword_dict (word, language) VALUES (%s, 'ko') ON CONFLICT (word, language) DO NOTHING",
                [(w,) for w in _STOPWORD_SEED],
            )
    logger.info("Seeded %d Korean stopwords", len(_STOPWORD_SEED))


def upsert_from_staging_news_raw() -> None:
    """stg_news_raw → news_raw upsert 후 staging TRUNCATE."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO news_raw (provider, source, author, title, description, content, url, published_at, ingested_at)
                SELECT provider, source, author, title, description, content, url, published_at, ingested_at
                FROM stg_news_raw
                ON CONFLICT (provider, url) DO NOTHING;
                TRUNCATE stg_news_raw;
            """)


def upsert_from_staging_keywords() -> None:
    """stg_keywords → keywords upsert 후 staging TRUNCATE."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                WITH dedup AS (
                    SELECT
                        article_provider,
                        article_url,
                        keyword,
                        MAX(keyword_count) AS keyword_count,
                        MAX(processed_at) AS processed_at
                    FROM stg_keywords
                    GROUP BY article_provider, article_url, keyword
                )
                INSERT INTO keywords (article_provider, article_url, keyword, keyword_count, processed_at)
                SELECT article_provider, article_url, keyword, keyword_count, processed_at
                FROM dedup
                ON CONFLICT (article_provider, article_url, keyword)
                DO UPDATE SET
                    keyword_count = EXCLUDED.keyword_count,
                    processed_at  = EXCLUDED.processed_at;
                TRUNCATE stg_keywords;
            """)


def upsert_from_staging_keyword_trends() -> None:
    """stg_keyword_trends → keyword_trends upsert (누적) 후 staging TRUNCATE."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                WITH dedup AS (
                    SELECT
                        provider,
                        window_start,
                        window_end,
                        keyword,
                        SUM(keyword_count) AS keyword_count,
                        MAX(processed_at) AS processed_at
                    FROM stg_keyword_trends
                    GROUP BY provider, window_start, window_end, keyword
                )
                INSERT INTO keyword_trends (provider, window_start, window_end, keyword, keyword_count, processed_at)
                SELECT provider, window_start, window_end, keyword, keyword_count, processed_at
                FROM dedup
                ON CONFLICT (provider, window_start, window_end, keyword)
                DO UPDATE SET
                    keyword_count = keyword_trends.keyword_count + EXCLUDED.keyword_count,
                    processed_at  = EXCLUDED.processed_at;
                TRUNCATE stg_keyword_trends;
            """)


def upsert_from_staging_keyword_relations() -> None:
    """stg_keyword_relations → keyword_relations upsert (누적) 후 staging TRUNCATE."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                WITH dedup AS (
                    SELECT
                        provider,
                        window_start,
                        window_end,
                        keyword_a,
                        keyword_b,
                        SUM(cooccurrence_count) AS cooccurrence_count,
                        MAX(processed_at) AS processed_at
                    FROM stg_keyword_relations
                    GROUP BY provider, window_start, window_end, keyword_a, keyword_b
                )
                INSERT INTO keyword_relations (provider, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at)
                SELECT provider, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at
                FROM dedup
                ON CONFLICT (provider, window_start, window_end, keyword_a, keyword_b)
                DO UPDATE SET
                    cooccurrence_count = keyword_relations.cooccurrence_count + EXCLUDED.cooccurrence_count,
                    processed_at       = EXCLUDED.processed_at;
                TRUNCATE stg_keyword_relations;
            """)


def insert_news_raw(articles: list[dict[str, Any]]) -> None:
    if not articles:
        return

    query = """
        INSERT INTO news_raw (
            provider,
            source,
            author,
            title,
            description,
            content,
            url,
            published_at,
            ingested_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (provider, url) DO NOTHING
    """
    rows = [
        (
            article.get("provider"),
            article.get("source"),
            article.get("author"),
            article.get("title"),
            article.get("description"),
            article.get("content"),
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
            cursor.executemany(query, rows)


def insert_keyword_trends(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    query = """
        INSERT INTO keyword_trends (provider, window_start, window_end, keyword, keyword_count, processed_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    values = [
        (
            row.get("provider"),
            row["window_start"],
            row["window_end"],
            row["keyword"],
            row["count"],
            row["processed_at"],
        )
        for row in rows
    ]
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(query, values)


def insert_keyword_relations(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    query = """
        INSERT INTO keyword_relations (
            provider,
            window_start,
            window_end,
            keyword_a,
            keyword_b,
            cooccurrence_count,
            processed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    values = [
        (
            row.get("provider"),
            row["window_start"],
            row["window_end"],
            row["keyword_a"],
            row["keyword_b"],
            row["count"],
            row["processed_at"],
        )
        for row in rows
    ]
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(query, values)


def fetch_news_raw_between(start_at: datetime, end_at: datetime, provider: str | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT provider, source, author, title, description, content, url, published_at, ingested_at
        FROM news_raw
        WHERE published_at >= %s
          AND published_at < %s
          AND (%s IS NULL OR provider = %s)
        ORDER BY published_at ASC
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (start_at, end_at, provider, provider))
            return list(cursor.fetchall())


def replace_keyword_trends(rows: list[dict[str, Any]], *, window_start: datetime, window_end: datetime, provider: str | None = None) -> None:
    delete_query = """
        DELETE FROM keyword_trends
        WHERE window_start >= %s
          AND window_start < %s
          AND (%s IS NULL OR provider = %s)
    """
    insert_query = """
        INSERT INTO keyword_trends (provider, window_start, window_end, keyword, keyword_count, processed_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    values = [
        (
            row.get("provider", provider),
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
            cursor.execute(delete_query, (window_start, window_end, provider, provider))
            if values:
                cursor.executemany(insert_query, values)


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start_at = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    return start_at, start_at + timedelta(days=1)


def rebuild_keywords_for_date(target_date: date, provider: str | None = None) -> dict[str, int]:
    start_at, end_at = _day_bounds(target_date)
    articles = fetch_news_raw_between(start_at, end_at, provider=provider)
    processed_at = datetime.now(timezone.utc)
    rows: list[tuple[str, str, str, int, datetime]] = []
    article_keys = [
        (article.get("provider"), article["url"])
        for article in articles
        if article.get("url")
    ]

    for article in articles:
        article_url = article.get("url")
        if not article_url:
            continue
        article_text = " ".join(
            part for part in [article.get("title"), article.get("description"), article.get("content")] if part
        )
        counts = Counter(tokenize(article_text))
        rows.extend(
            (
                article.get("provider"),
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
                    "DELETE FROM keywords WHERE article_provider = %s AND article_url = %s",
                    article_keys,
                )
            if rows:
                cursor.executemany(
                    """
                    INSERT INTO keywords (article_provider, article_url, keyword, keyword_count, processed_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    rows,
                )

    return {"article_count": len(articles), "keyword_row_count": len(rows)}


def rebuild_keyword_trends_for_date(target_date: date, provider: str | None = None) -> dict[str, int]:
    start_at, end_at = _day_bounds(target_date)
    articles = fetch_news_raw_between(start_at, end_at, provider=provider)
    window_counts: defaultdict[tuple[str, datetime, datetime, str], int] = defaultdict(int)
    processed_at = datetime.now(timezone.utc)

    for article in articles:
        published_at = article.get("published_at")
        if not published_at:
            continue
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        normalized = published_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
        minute_bucket = normalized.minute - (normalized.minute % 10)
        window_start = normalized.replace(minute=minute_bucket)
        window_end = window_start + timedelta(minutes=10)
        article_text = " ".join(
            part for part in [article.get("title"), article.get("description"), article.get("content")] if part
        )
        for keyword, count in Counter(tokenize(article_text)).items():
            window_counts[(article.get("provider"), window_start, window_end, keyword)] += count

    rows = [
        {
            "provider": provider_name,
            "window_start": item_window_start,
            "window_end": item_window_end,
            "keyword": keyword,
            "keyword_count": keyword_count,
            "processed_at": processed_at,
        }
        for (provider_name, item_window_start, item_window_end, keyword), keyword_count in sorted(window_counts.items())
    ]
    replace_keyword_trends(rows, window_start=start_at, window_end=end_at, provider=provider)
    return {"article_count": len(articles), "trend_row_count": len(rows)}


def rebuild_keyword_relations_for_date(target_date: date, provider: str | None = None) -> dict[str, int]:
    start_at, end_at = _day_bounds(target_date)
    articles = fetch_news_raw_between(start_at, end_at, provider=provider)
    relation_counts: defaultdict[tuple[str, datetime, datetime, str, str], int] = defaultdict(int)
    processed_at = datetime.now(timezone.utc)

    for article in articles:
        published_at = article.get("published_at")
        if not published_at:
            continue
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        normalized = published_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
        minute_bucket = normalized.minute - (normalized.minute % 10)
        window_start = normalized.replace(minute=minute_bucket)
        window_end = window_start + timedelta(minutes=10)
        article_text = " ".join(
            part for part in [article.get("title"), article.get("description"), article.get("content")] if part
        )
        keyword_counts = Counter(tokenize(article_text))
        representative_keywords = [
            keyword
            for keyword, _ in sorted(keyword_counts.items(), key=lambda item: (-item[1], item[0]))[: settings.relation_keyword_limit]
        ]
        for idx, keyword_a in enumerate(representative_keywords):
            for keyword_b in representative_keywords[idx + 1 :]:
                relation_counts[(article.get("provider"), window_start, window_end, keyword_a, keyword_b)] += 1

    rows = [
        {
            "provider": provider_name,
            "window_start": item_window_start,
            "window_end": item_window_end,
            "keyword_a": keyword_a,
            "keyword_b": keyword_b,
            "count": relation_count,
            "processed_at": processed_at,
        }
        for (provider_name, item_window_start, item_window_end, keyword_a, keyword_b), relation_count in sorted(
            relation_counts.items()
        )
    ]

    delete_query = """
        DELETE FROM keyword_relations
        WHERE (%s IS NULL OR provider = %s)
          AND window_start >= %s
          AND window_start < %s
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(delete_query, (provider, provider, start_at, end_at))
            if rows:
                insert_query = """
                    INSERT INTO keyword_relations (
                        provider,
                        window_start,
                        window_end,
                        keyword_a,
                        keyword_b,
                        cooccurrence_count,
                        processed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.executemany(
                    insert_query,
                    [
                        (
                            row["provider"],
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
