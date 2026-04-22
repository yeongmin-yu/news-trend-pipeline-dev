from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from psycopg2.extras import RealDictCursor

from news_trend_pipeline.core.logger import get_logger
from news_trend_pipeline.storage.db import get_connection, replace_keyword_events


logger = get_logger(__name__)


def _safe_growth(current: int, previous: int) -> float:
    if previous <= 0:
        return 1.0 if current > 0 else 0.0
    return (current - previous) / previous


def _score_keyword(current: int, growth: float) -> tuple[bool, int]:
    spike = current >= 5 and growth >= 0.4
    score = int(min(100, round((growth * 45) + (current ** 0.5 * 6) + (20 if spike else 0))))
    return spike, max(0, score)


def run_event_detection_job(
    *,
    lookback_hours: int = 24,
    until: datetime | None = None,
) -> dict[str, int]:
    until_dt = (until or datetime.now(UTC)).astimezone(UTC)
    since_dt = until_dt - timedelta(hours=lookback_hours)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    provider,
                    domain,
                    keyword,
                    window_start,
                    window_end,
                    keyword_count
                FROM keyword_trends
                WHERE window_start >= %s
                  AND window_start < %s
                ORDER BY provider ASC, domain ASC, keyword ASC, window_start ASC
                """,
                (since_dt, until_dt),
            )
            rows = list(cursor.fetchall())

    grouped: defaultdict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["provider"], row["domain"], row["keyword"])].append(row)

    detected_at = datetime.now(UTC)
    event_rows: list[dict] = []

    for (provider, domain, keyword), items in grouped.items():
        previous = 0
        for item in items:
            current_mentions = int(item["keyword_count"] or 0)
            growth = _safe_growth(current_mentions, previous)
            spike, event_score = _score_keyword(current_mentions, growth)
            if current_mentions > 0 and (spike or current_mentions >= 5 or growth >= 0.15):
                event_rows.append(
                    {
                        "provider": provider,
                        "domain": domain,
                        "keyword": keyword,
                        "event_time": item["window_end"],
                        "window_start": item["window_start"],
                        "window_end": item["window_end"],
                        "current_mentions": current_mentions,
                        "prev_mentions": previous,
                        "growth": growth,
                        "event_score": event_score,
                        "is_spike": spike,
                        "detected_at": detected_at,
                    }
                )
            previous = current_mentions

    replace_keyword_events(event_rows, since=since_dt, until=until_dt)
    logger.info(
        "keyword event detection finished | source_rows=%d | event_rows=%d | since=%s | until=%s",
        len(rows),
        len(event_rows),
        since_dt.isoformat(),
        until_dt.isoformat(),
    )
    return {
        "source_row_count": len(rows),
        "event_row_count": len(event_rows),
    }


if __name__ == "__main__":
    print(run_event_detection_job())
