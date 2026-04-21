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


def safe_initialize_database() -> None:
    try:
        initialize_database()
    except Error as exc:
        logger.warning("Database initialization skipped: %s", exc)


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
