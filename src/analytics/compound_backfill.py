from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Any

from psycopg2.extras import execute_values

from core.config import settings
from core.logger import get_logger
from processing.preprocessing import tokenize
from storage.db import get_connection


logger = get_logger(__name__)


def _parse_datetime(value: str | datetime | None, *, field: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_window_duration(value: str) -> timedelta:
    amount, unit = value.strip().split(maxsplit=1)
    count = int(amount)
    unit = unit.lower()
    if unit.startswith("minute"):
        return timedelta(minutes=count)
    if unit.startswith("hour"):
        return timedelta(hours=count)
    if unit.startswith("day"):
        return timedelta(days=count)
    raise ValueError(f"Unsupported KEYWORD_WINDOW_DURATION: {value!r}")


def _window_bounds(event_time: datetime, duration: timedelta) -> tuple[datetime, datetime]:
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    seconds = int(duration.total_seconds())
    epoch = int(event_time.timestamp())
    start_epoch = epoch - (epoch % seconds)
    start = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
    return start, start + duration


def _compact(text: str | None) -> str:
    return "".join((text or "").split())


def run_compound_keyword_backfill(
    *,
    word: str,
    domain: str = "all",
    since: str | datetime | None = None,
    until: str | datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_word = word.strip()
    normalized_domain = (domain or "all").strip() or "all"
    since_dt = _parse_datetime(since, field="since")
    until_dt = _parse_datetime(until, field="until")
    if not normalized_word:
        raise ValueError("word is required")
    if since_dt and until_dt and since_dt >= until_dt:
        raise ValueError("since must be earlier than until")

    conditions = ["COALESCE(published_at, ingested_at) IS NOT NULL"]
    params: list[Any] = []
    if normalized_domain != "all":
        conditions.append("domain = %s")
        params.append(normalized_domain)
    if since_dt:
        conditions.append("COALESCE(published_at, ingested_at) >= %s")
        params.append(since_dt)
    if until_dt:
        conditions.append("COALESCE(published_at, ingested_at) < %s")
        params.append(until_dt)

    where_clause = " AND ".join(conditions)
    window_duration = _parse_window_duration(settings.keyword_window_duration)
    affected_windows: set[tuple[str, str, datetime, datetime]] = set()
    keyword_rows: list[tuple[str, str, str, str, int, datetime]] = []
    article_keys: list[tuple[str, str, str]] = []

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT provider, domain, url, title, summary, COALESCE(published_at, ingested_at) AS event_time
                FROM news_raw
                WHERE {where_clause}
                ORDER BY COALESCE(published_at, ingested_at) ASC
                """,
                params,
            )
            articles = cursor.fetchall()

            for provider, article_domain, url, title, summary, event_time in articles:
                article_text = f"{title or ''} {summary or ''}"
                if normalized_word not in _compact(article_text):
                    continue
                token_counts = Counter(tokenize(article_text, article_domain or normalized_domain))
                if not token_counts:
                    continue

                article_keys.append((provider, article_domain, url))
                window_start, window_end = _window_bounds(event_time, window_duration)
                affected_windows.add((provider, article_domain, window_start, window_end))
                processed_at = datetime.now(timezone.utc)
                for keyword, count in token_counts.items():
                    keyword_rows.append((provider, article_domain, url, keyword, int(count), processed_at))

            if dry_run:
                return {
                    "status": "dry_run",
                    "word": normalized_word,
                    "domain": normalized_domain,
                    "scanned_articles": len(articles),
                    "affected_articles": len(article_keys),
                    "affected_windows": len(affected_windows),
                    "keyword_rows": len(keyword_rows),
                }

            if not article_keys:
                return {
                    "status": "ok",
                    "word": normalized_word,
                    "domain": normalized_domain,
                    "scanned_articles": len(articles),
                    "affected_articles": 0,
                    "affected_windows": 0,
                    "keyword_rows": 0,
                    "trend_rows": 0,
                    "relation_rows": 0,
                }

            execute_values(
                cursor,
                """
                DELETE FROM keywords AS k
                USING (VALUES %s) AS v(provider, domain, url)
                WHERE k.article_provider = v.provider
                  AND k.article_domain = v.domain
                  AND k.article_url = v.url
                """,
                article_keys,
            )
            execute_values(
                cursor,
                """
                INSERT INTO keywords (article_provider, article_domain, article_url, keyword, keyword_count, processed_at)
                VALUES %s
                ON CONFLICT (article_provider, article_domain, article_url, keyword)
                DO UPDATE SET
                    keyword_count = EXCLUDED.keyword_count,
                    processed_at = EXCLUDED.processed_at
                """,
                keyword_rows,
            )

            window_rows = list(affected_windows)
            execute_values(
                cursor,
                """
                DELETE FROM keyword_trends AS kt
                USING (VALUES %s) AS v(provider, domain, window_start, window_end)
                WHERE kt.provider = v.provider
                  AND kt.domain = v.domain
                  AND kt.window_start = v.window_start::timestamptz
                  AND kt.window_end = v.window_end::timestamptz
                """,
                window_rows,
            )
            execute_values(
                cursor,
                """
                DELETE FROM keyword_relations AS kr
                USING (VALUES %s) AS v(provider, domain, window_start, window_end)
                WHERE kr.provider = v.provider
                  AND kr.domain = v.domain
                  AND kr.window_start = v.window_start::timestamptz
                  AND kr.window_end = v.window_end::timestamptz
                """,
                window_rows,
            )

            trend_counts: dict[tuple[str, str, datetime, datetime, str], int] = defaultdict(int)
            relation_counts: dict[tuple[str, str, datetime, datetime, str, str], int] = defaultdict(int)
            for provider, article_domain, window_start, window_end in window_rows:
                cursor.execute(
                    """
                    SELECT k.article_provider, k.article_domain, k.article_url, k.keyword, k.keyword_count
                    FROM keywords k
                    JOIN news_raw n
                      ON n.provider = k.article_provider
                     AND n.domain = k.article_domain
                     AND n.url = k.article_url
                    WHERE k.article_provider = %s
                      AND k.article_domain = %s
                      AND COALESCE(n.published_at, n.ingested_at) >= %s
                      AND COALESCE(n.published_at, n.ingested_at) < %s
                    """,
                    (provider, article_domain, window_start, window_end),
                )
                article_keywords: dict[str, list[tuple[str, int]]] = defaultdict(list)
                for p, d, url, keyword, count in cursor.fetchall():
                    trend_counts[(p, d, window_start, window_end, keyword)] += int(count)
                    article_keywords[url].append((keyword, int(count)))

                for keywords in article_keywords.values():
                    ranked = sorted(keywords, key=lambda item: (-item[1], item[0]))[: settings.relation_keyword_limit]
                    for left, right in combinations([keyword for keyword, _ in ranked], 2):
                        keyword_a, keyword_b = sorted((left, right))
                        if keyword_a != keyword_b:
                            relation_counts[(provider, article_domain, window_start, window_end, keyword_a, keyword_b)] += 1

            trend_rows = [
                (*key, count, datetime.now(timezone.utc))
                for key, count in trend_counts.items()
            ]
            relation_rows = [
                (*key, count, datetime.now(timezone.utc))
                for key, count in relation_counts.items()
            ]
            if trend_rows:
                execute_values(
                    cursor,
                    """
                    INSERT INTO keyword_trends (provider, domain, window_start, window_end, keyword, keyword_count, processed_at)
                    VALUES %s
                    ON CONFLICT (provider, domain, window_start, window_end, keyword)
                    DO UPDATE SET keyword_count = EXCLUDED.keyword_count,
                                  processed_at = EXCLUDED.processed_at
                    """,
                    trend_rows,
                )
            if relation_rows:
                execute_values(
                    cursor,
                    """
                    INSERT INTO keyword_relations (provider, domain, window_start, window_end, keyword_a, keyword_b, cooccurrence_count, processed_at)
                    VALUES %s
                    ON CONFLICT (provider, domain, window_start, window_end, keyword_a, keyword_b)
                    DO UPDATE SET cooccurrence_count = EXCLUDED.cooccurrence_count,
                                  processed_at = EXCLUDED.processed_at
                    """,
                    relation_rows,
                )

    result = {
        "status": "ok",
        "word": normalized_word,
        "domain": normalized_domain,
        "scanned_articles": len(articles),
        "affected_articles": len(article_keys),
        "affected_windows": len(affected_windows),
        "keyword_rows": len(keyword_rows),
        "trend_rows": len(trend_rows),
        "relation_rows": len(relation_rows),
    }
    logger.info("Compound keyword backfill complete: %s", result)
    return result
