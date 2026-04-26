from __future__ import annotations

import socket
from math import ceil
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from psycopg2.extras import RealDictCursor

from core.config import settings
from core.domains import DOMAIN_DEFINITIONS, DOMAIN_LABELS
from storage.db import (
    create_query_keyword as db_create_query_keyword,
    delete_query_keyword as db_delete_query_keyword,
    fetch_all_query_keywords,
    fetch_collection_metrics_summary,
    fetch_compound_candidate_item,
    fetch_compound_noun_item,
    fetch_dictionary_audit_logs,
    fetch_dictionary_versions,
    fetch_domain_catalog,
    fetch_query_keyword_audit_logs,
    fetch_stopword_candidate_item,
    fetch_stopword_item,
    get_connection,
    log_dictionary_audit,
    review_stopword_candidate as db_review_stopword_candidate,
    update_compound_noun_domain as db_update_compound_noun_domain,
    update_stopword_domain as db_update_stopword_domain,
    update_query_keyword as db_update_query_keyword,
)


@dataclass(frozen=True)
class RangeSpec:
    id: str
    label: str
    bucket_min: int
    buckets: int

    @property
    def duration(self) -> timedelta:
        return timedelta(minutes=self.bucket_min * self.buckets)


RANGES: dict[str, RangeSpec] = {
    "10m": RangeSpec("10m", "10분", 1, 10),
    "30m": RangeSpec("30m", "30분", 3, 10),
    "1h": RangeSpec("1h", "1시간", 5, 12),
    "6h": RangeSpec("6h", "6시간", 30, 12),
    "12h": RangeSpec("12h", "12시간", 60, 12),
    "1d": RangeSpec("1d", "1일", 120, 12),
}

SOURCES = [
    {"id": "all", "label": "전체", "color": "#7dd3fc"},
    {"id": "naver", "label": "네이버 뉴스", "color": "#34d399"},
    {"id": "global", "label": "글로벌 뉴스", "color": "#f59e0b"},
]

PALETTE = ["#8b5cf6", "#0ea5e9", "#22c55e", "#f59e0b", "#64748b"]
THEME_COLORS = ["#5eead4", "#f472b6", "#fbbf24", "#60a5fa"]
TREND_BUCKETS = {
    "5m": ("5 minutes", 5),
    "15m": ("15 minutes", 15),
    "30m": ("30 minutes", 30),
    "1h": ("1 hour", 60),
    "4h": ("4 hours", 240),
    "1d": ("1 day", 1440),
}


def _provider_filter(source: str) -> str | None:
    return None if source == "all" else source


def _domain_filter(domain: str) -> str | None:
    return None if domain == "all" else domain


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _range_bounds(range_id: str) -> tuple[RangeSpec, datetime, datetime, datetime]:
    spec = RANGES[range_id]
    end_at = _now_utc()
    start_at = end_at - spec.duration
    prev_start_at = start_at - spec.duration
    return spec, start_at, end_at, prev_start_at


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _window_bounds(
    *,
    range_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> tuple[RangeSpec | None, datetime, datetime, datetime]:
    if start_at is not None and end_at is not None:
        start_utc = _normalize_utc(start_at)
        end_utc = _normalize_utc(end_at)
        if end_utc <= start_utc:
            raise ValueError("endAt must be later than startAt")
        duration = end_utc - start_utc
        prev_start_at = start_utc - duration
        return None, start_utc, end_utc, prev_start_at
    if not range_id:
        raise ValueError("range or startAt/endAt is required")
    return _range_bounds(range_id)


def _pick_auto_bucket_for_window(duration: timedelta) -> str:
    if duration <= timedelta(hours=6):
        return "5m"
    if duration <= timedelta(days=2):
        return "15m"
    if duration <= timedelta(days=7):
        return "1h"
    return "4h"


def _window_range_payload(
    *,
    range_spec: RangeSpec | None,
    start_at: datetime,
    end_at: datetime,
    bucket_id: str,
) -> dict[str, Any]:
    bucket_min = TREND_BUCKETS[bucket_id][1]
    buckets = max(1, ceil((end_at - start_at).total_seconds() / (bucket_min * 60)))
    if range_spec is not None:
        return {
            "id": range_spec.id,
            "label": range_spec.label,
            "bucketMin": range_spec.bucket_min,
            "buckets": range_spec.buckets,
        }
    return {
        "id": "custom",
        "label": f"{bucket_id} custom",
        "bucketMin": bucket_min,
        "buckets": buckets,
    }


def _format_relative(value: datetime | None) -> str:
    if value is None:
        return "데이터 없음"
    delta = _now_utc() - value.astimezone(UTC)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "방금 전"
    if seconds < 3600:
        return f"{seconds // 60}분 전"
    if seconds < 86400:
        return f"{seconds // 3600}시간 전"
    return f"{seconds // 86400}일 전"


def _safe_growth(current: int, previous: int) -> float:
    if previous <= 0:
        return 1.0 if current > 0 else 0.0
    return (current - previous) / previous


def _score_keyword(current: int, growth: float) -> tuple[bool, int]:
    spike = current >= 5 and growth >= 0.4
    score = int(min(100, round((growth * 45) + (current ** 0.5 * 6) + (20 if spike else 0))))
    return spike, max(0, score)


def _bucket_index(value: datetime, origin: datetime, bucket_delta: timedelta) -> int:
    return int((value - origin).total_seconds() // bucket_delta.total_seconds())


def _fetch_overview_cache_rows(
    *,
    source: str,
    domain: str,
    data_start: datetime,
    data_end: datetime,
    bucket_id: str,
    keywords: list[str],
) -> dict[str, Any]:
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    bucket_interval, bucket_min = TREND_BUCKETS[bucket_id]
    bucket_delta = timedelta(minutes=bucket_min)
    total_buckets = max(1, ceil((data_end - data_start).total_seconds() / bucket_delta.total_seconds()))
    article_buckets = [
        {
            "bucket": index,
            "timestamp": (data_start + bucket_delta * index).isoformat(),
            "articleCount": 0,
            "lastUpdateAt": None,
        }
        for index in range(total_buckets)
    ]
    keyword_buckets: list[dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    date_bin(%(bucket_interval)s::interval, COALESCE(published_at, ingested_at), %(origin)s::timestamptz) AS bucket_start,
                    COUNT(*) AS article_count,
                    MAX(COALESCE(published_at, ingested_at)) AS last_update_at
                FROM news_raw
                WHERE COALESCE(published_at, ingested_at) >= %(start_at)s
                  AND COALESCE(published_at, ingested_at) < %(end_at)s
                  AND (%(provider)s IS NULL OR provider = %(provider)s)
                  AND (%(domain)s IS NULL OR domain = %(domain)s)
                GROUP BY bucket_start
                ORDER BY bucket_start ASC
                """,
                {
                    "bucket_interval": bucket_interval,
                    "origin": data_start,
                    "start_at": data_start,
                    "end_at": data_end,
                    "provider": provider,
                    "domain": domain_filter,
                },
            )
            for row in cursor.fetchall():
                bucket_start = row["bucket_start"]
                bucket_index = _bucket_index(bucket_start, data_start, bucket_delta)
                if 0 <= bucket_index < total_buckets:
                    article_buckets[bucket_index] = {
                        "bucket": bucket_index,
                        "timestamp": bucket_start.isoformat(),
                        "articleCount": int(row["article_count"] or 0),
                        "lastUpdateAt": row["last_update_at"].isoformat() if row.get("last_update_at") else None,
                    }

            if keywords:
                cursor.execute(
                    """
                    SELECT
                        k.keyword,
                        date_bin(%(bucket_interval)s::interval, COALESCE(n.published_at, n.ingested_at), %(origin)s::timestamptz) AS bucket_start,
                        SUM(k.keyword_count) AS mentions,
                        COUNT(DISTINCT k.article_url) AS article_count
                    FROM keywords k
                    JOIN news_raw n
                      ON n.provider = k.article_provider
                     AND n.domain = k.article_domain
                     AND n.url = k.article_url
                    WHERE COALESCE(n.published_at, n.ingested_at) >= %(start_at)s
                      AND COALESCE(n.published_at, n.ingested_at) < %(end_at)s
                      AND k.keyword = ANY(%(keywords)s)
                      AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                      AND (%(domain)s IS NULL OR n.domain = %(domain)s)
                    GROUP BY k.keyword, bucket_start
                    ORDER BY k.keyword ASC, bucket_start ASC
                    """,
                    {
                        "bucket_interval": bucket_interval,
                        "origin": data_start,
                        "start_at": data_start,
                        "end_at": data_end,
                        "keywords": keywords,
                        "provider": provider,
                        "domain": domain_filter,
                    },
                )
                for row in cursor.fetchall():
                    bucket_start = row["bucket_start"]
                    bucket_index = _bucket_index(bucket_start, data_start, bucket_delta)
                    if 0 <= bucket_index < total_buckets:
                        keyword_buckets.append(
                            {
                                "keyword": row["keyword"],
                                "bucket": bucket_index,
                                "timestamp": bucket_start.isoformat(),
                                "mentions": int(row["mentions"] or 0),
                                "articleCount": int(row["article_count"] or 0),
                            }
                        )

    return {
        "dataStartAt": data_start.isoformat(),
        "dataEndAt": data_end.isoformat(),
        "bucket": bucket_id,
        "bucketMin": bucket_min,
        "buckets": total_buckets,
        "articleBuckets": article_buckets,
        "keywordBuckets": keyword_buckets,
    }


def _derive_overview_from_cache(
    *,
    source: str,
    cache: dict[str, Any],
    start_at: datetime,
    end_at: datetime,
    limit: int,
) -> dict[str, Any]:
    data_start = _normalize_utc(datetime.fromisoformat(cache["dataStartAt"]))
    bucket_min = int(cache["bucketMin"])
    bucket_delta = timedelta(minutes=bucket_min)
    duration = end_at - start_at
    prev_start = start_at - duration
    article_rows = cache["articleBuckets"]
    keyword_rows = cache["keywordBuckets"]

    article_counts = [int(row["articleCount"] or 0) for row in article_rows]
    last_updates = [
        _normalize_utc(datetime.fromisoformat(row["lastUpdateAt"])) if row.get("lastUpdateAt") else None
        for row in article_rows
    ]
    keyword_map: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {
            "mentions": [0] * len(article_rows),
            "articleCounts": [0] * len(article_rows),
        }
    )
    for row in keyword_rows:
        keyword = str(row["keyword"])
        bucket_index = int(row["bucket"])
        if 0 <= bucket_index < len(article_rows):
            keyword_map[keyword]["mentions"][bucket_index] = int(row["mentions"] or 0)
            keyword_map[keyword]["articleCounts"][bucket_index] = int(row["articleCount"] or 0)

    current_indices = [
        index
        for index, row in enumerate(article_rows)
        if start_at <= _normalize_utc(datetime.fromisoformat(row["timestamp"])) < end_at
    ]
    prev_indices = [
        index
        for index, row in enumerate(article_rows)
        if prev_start <= _normalize_utc(datetime.fromisoformat(row["timestamp"])) < start_at
    ]

    current_articles = sum(article_counts[index] for index in current_indices)
    prev_articles = sum(article_counts[index] for index in prev_indices)
    last_update = max((last_updates[index] for index in current_indices if last_updates[index] is not None), default=None)
    article_growth = _safe_growth(current_articles, prev_articles)

    keywords: list[dict[str, Any]] = []
    spike_events: list[dict[str, Any]] = []
    spike_keywords: set[str] = set()
    default_event_source = "global" if source == "global" else "naver"
    current_index_set = set(current_indices)

    for keyword, series in keyword_map.items():
        current_mentions = sum(series["mentions"][index] for index in current_indices)
        prev_mentions = sum(series["mentions"][index] for index in prev_indices)
        if current_mentions <= 0 and prev_mentions <= 0:
            continue
        growth = _safe_growth(current_mentions, prev_mentions)
        spike, event_score = _score_keyword(current_mentions, growth)
        keywords.append(
            {
                "keyword": keyword,
                "mentions": current_mentions,
                "prevMentions": prev_mentions,
                "growth": growth,
                "delta": current_mentions - prev_mentions,
                "spike": spike,
                "eventScore": event_score,
                "articleCount": sum(series["articleCounts"][index] for index in current_indices),
            }
        )

        previous_bucket_count = 0
        for bucket_index, mentions in enumerate(series["mentions"]):
            if mentions <= 0:
                continue
            growth_vs_prev = _safe_growth(mentions, previous_bucket_count)
            if bucket_index in current_index_set and growth_vs_prev >= 0.35 and mentions >= 3:
                spike_keywords.add(keyword)
                spike_events.append(
                    {
                        "bucket": _bucket_index(data_start + bucket_delta * bucket_index, start_at, bucket_delta),
                        "keyword": keyword,
                        "intensity": min(1.0, max(0.12, growth_vs_prev)),
                        "source": default_event_source,
                        "currentMentions": mentions,
                        "prevMentions": previous_bucket_count,
                        "growth": growth_vs_prev,
                        "score": event_score,
                    }
                )
            previous_bucket_count = mentions

    keywords.sort(key=lambda item: (-int(item["mentions"]), item["keyword"]))
    spike_events = [item for item in spike_events if 0 <= int(item["bucket"]) < max(1, ceil(duration.total_seconds() / bucket_delta.total_seconds()))]
    spike_events.sort(key=lambda item: (int(item["score"]), float(item["growth"])), reverse=True)

    return {
        "kpis": {
            "totalArticles": current_articles,
            "uniqueKeywords": sum(1 for item in keywords if int(item["mentions"]) > 0),
            "spikeCount": len(spike_keywords),
            "growth": article_growth,
            "lastUpdateRelative": _format_relative(last_update),
            "lastUpdateAbsolute": last_update.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if last_update else "데이터 없음",
        },
        "keywords": keywords[:limit],
        "spikes": {
            "topKeywords": [item["keyword"] for item in keywords if item["spike"]][:8] or [item["keyword"] for item in keywords[:8]],
            "events": spike_events[: max(limit, 32)],
            "range": _window_range_payload(range_spec=None, start_at=start_at, end_at=end_at, bucket_id=cache["bucket"]),
        },
    }


def get_filters() -> dict[str, Any]:
    domains = [{"id": "all", "label": "전체", "available": True}]
    domains.extend(fetch_domain_catalog())
    return {
        "domains": domains,
        "sources": SOURCES,
        "ranges": [
            {
                "id": spec.id,
                "label": spec.label,
                "bucketMin": spec.bucket_min,
                "buckets": spec.buckets,
            }
            for spec in RANGES.values()
        ],
    }


def get_kpis(
    source: str,
    domain: str,
    range_id: str | None = None,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    _, start_at, end_at, prev_start_at = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE COALESCE(published_at, ingested_at) >= %(start_at)s
                          AND COALESCE(published_at, ingested_at) < %(end_at)s
                    ) AS current_articles,
                    COUNT(*) FILTER (
                        WHERE COALESCE(published_at, ingested_at) >= %(prev_start_at)s
                          AND COALESCE(published_at, ingested_at) < %(start_at)s
                    ) AS prev_articles,
                    MAX(COALESCE(published_at, ingested_at)) AS last_update
                FROM news_raw
                WHERE (%(provider)s IS NULL OR provider = %(provider)s)
                  AND (%(domain)s IS NULL OR domain = %(domain)s)
                """,
                {
                    "start_at": start_at,
                    "end_at": end_at,
                    "prev_start_at": prev_start_at,
                    "provider": provider,
                    "domain": domain_filter,
                },
            )
            article_row = cursor.fetchone() or {}
            cursor.execute(
                """
                SELECT COUNT(DISTINCT keyword) AS unique_keywords
                FROM keyword_trends
                WHERE window_start >= %(start_at)s
                  AND window_start < %(end_at)s
                  AND (%(provider)s IS NULL OR provider = %(provider)s)
                  AND (%(domain)s IS NULL OR domain = %(domain)s)
                """,
                {
                    "start_at": start_at,
                    "end_at": end_at,
                    "provider": provider,
                    "domain": domain_filter,
                },
            )
            unique_row = cursor.fetchone() or {}
            cursor.execute(
                """
                SELECT COUNT(DISTINCT keyword) AS spike_count
                FROM keyword_events
                WHERE window_start >= %(start_at)s
                  AND window_start < %(end_at)s
                  AND is_spike = TRUE
                  AND (%(provider)s IS NULL OR provider = %(provider)s)
                  AND (%(domain)s IS NULL OR domain = %(domain)s)
                """,
                {
                    "start_at": start_at,
                    "end_at": end_at,
                    "provider": provider,
                    "domain": domain_filter,
                },
            )
            spike_row = cursor.fetchone() or {}
    growth = _safe_growth(article_row.get("current_articles") or 0, article_row.get("prev_articles") or 0)
    last_update = article_row.get("last_update")
    return {
        "totalArticles": int(article_row.get("current_articles") or 0),
        "uniqueKeywords": int(unique_row.get("unique_keywords") or 0),
        "spikeCount": int(spike_row.get("spike_count") or 0),
        "growth": growth,
        "lastUpdateRelative": _format_relative(last_update),
        "lastUpdateAbsolute": last_update.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if last_update else "데이터 없음",
    }


def get_top_keywords(
    source: str,
    domain: str,
    range_id: str | None = None,
    limit: int = 30,
    search: str | None = None,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    _, start_at, end_at, prev_start_at = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    params = {
        "start_at": start_at,
        "end_at": end_at,
        "prev_start_at": prev_start_at,
        "provider": provider,
        "domain": domain_filter,
        "search": f"%{search.strip()}%" if search else None,
        "limit": limit,
    }
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                WITH current_counts AS (
                    SELECT keyword, SUM(keyword_count) AS mentions
                    FROM keyword_trends
                    WHERE window_start >= %(start_at)s
                      AND window_start < %(end_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (%(domain)s IS NULL OR domain = %(domain)s)
                    GROUP BY keyword
                ),
                prev_counts AS (
                    SELECT keyword, SUM(keyword_count) AS mentions
                    FROM keyword_trends
                    WHERE window_start >= %(prev_start_at)s
                      AND window_start < %(start_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (%(domain)s IS NULL OR domain = %(domain)s)
                    GROUP BY keyword
                ),
                article_counts AS (
                    SELECT k.keyword, COUNT(DISTINCT k.article_url) AS article_count
                    FROM keywords k
                    JOIN news_raw n
                      ON n.url = k.article_url
                     AND n.provider = k.article_provider
                     AND n.domain = k.article_domain
                    WHERE COALESCE(n.published_at, n.ingested_at) >= %(start_at)s
                      AND COALESCE(n.published_at, n.ingested_at) < %(end_at)s
                      AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                      AND (%(domain)s IS NULL OR n.domain = %(domain)s)
                    GROUP BY k.keyword
                )
                SELECT
                    c.keyword,
                    c.mentions,
                    COALESCE(p.mentions, 0) AS prev_mentions,
                    COALESCE(a.article_count, 0) AS article_count
                FROM current_counts c
                LEFT JOIN prev_counts p ON p.keyword = c.keyword
                LEFT JOIN article_counts a ON a.keyword = c.keyword
                WHERE (%(search)s IS NULL OR c.keyword ILIKE %(search)s)
                ORDER BY c.mentions DESC, c.keyword ASC
                LIMIT %(limit)s
                """,
                params,
            )
            rows = list(cursor.fetchall())

    result: list[dict[str, Any]] = []
    for row in rows:
        mentions = int(row["mentions"] or 0)
        prev_mentions = int(row["prev_mentions"] or 0)
        growth = _safe_growth(mentions, prev_mentions)
        spike, event_score = _score_keyword(mentions, growth)
        if source == "naver":
            source_share_naver, source_share_global = 1.0, 0.0
        elif source == "global":
            source_share_naver, source_share_global = 0.0, 1.0
        else:
            source_share_naver, source_share_global = 0.5, 0.5
        result.append(
            {
                "keyword": row["keyword"],
                "mentions": mentions,
                "prevMentions": prev_mentions,
                "growth": growth,
                "delta": mentions - prev_mentions,
                "spike": spike,
                "eventScore": event_score,
                "articleCount": int(row["article_count"] or 0),
                "sourceShareNaver": source_share_naver,
                "sourceShareGlobal": source_share_global,
            }
        )
    return result


def get_trend_series(
    source: str,
    domain: str,
    range_id: str,
    keyword: str | None = None,
    keywords: list[str] | None = None,
    compare_limit: int = 4,
) -> dict[str, Any]:
    spec, start_at, end_at, _ = _range_bounds(range_id)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    top_keywords = get_top_keywords(source=source, domain=domain, range_id=range_id, limit=max(compare_limit * 2, 20))
    compare_keywords: list[str] = []
    if keywords:
        for item in keywords:
            normalized = item.strip()
            if normalized and normalized not in compare_keywords:
                compare_keywords.append(normalized)
        compare_keywords = compare_keywords[:5]
    elif keyword:
        compare_keywords = [keyword]
        compare_keywords.extend(item["keyword"] for item in top_keywords if item["keyword"] != keyword)
        compare_keywords = compare_keywords[:compare_limit]
    bucket_edges = [start_at + timedelta(minutes=spec.bucket_min * index) for index in range(spec.buckets + 1)]
    bucket_map = {index: bucket_edges[index] for index in range(spec.buckets)}
    series_lookup = {
        name: [{"bucket": index, "timestamp": bucket_map[index], "value": 0} for index in range(spec.buckets)]
        for name in compare_keywords
    }
    if compare_keywords:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT keyword, window_start, SUM(keyword_count) AS keyword_count
                    FROM keyword_trends
                    WHERE window_start >= %(start_at)s
                      AND window_start < %(end_at)s
                      AND keyword = ANY(%(keywords)s)
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (%(domain)s IS NULL OR domain = %(domain)s)
                    GROUP BY keyword, window_start
                    ORDER BY window_start ASC
                    """,
                    {
                        "start_at": start_at,
                        "end_at": end_at,
                        "keywords": compare_keywords,
                        "provider": provider,
                        "domain": domain_filter,
                    },
                )
                for row in cursor.fetchall():
                    bucket_index = int((row["window_start"] - start_at).total_seconds() // (spec.bucket_min * 60))
                    if 0 <= bucket_index < spec.buckets:
                        series_lookup[row["keyword"]][bucket_index]["value"] = int(row["keyword_count"] or 0)
    summary_lookup = {item["keyword"]: item for item in top_keywords}
    return {
        "series": [
            {
                "name": name,
                "color": PALETTE[index % len(PALETTE)],
                "spike": bool(summary_lookup.get(name, {}).get("spike", False)),
                "points": points,
            }
            for index, (name, points) in enumerate(series_lookup.items())
        ],
        "range": {
            "id": spec.id,
            "label": spec.label,
            "bucketMin": spec.bucket_min,
            "buckets": spec.buckets,
        },
    }


def get_spike_events(
    source: str,
    domain: str,
    range_id: str | None = None,
    limit: int = 32,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    bucket_id: str | None = None,
    top_keywords: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    range_spec, start_at, end_at, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    effective_bucket_id = bucket_id or _pick_auto_bucket_for_window(end_at - start_at)
    if effective_bucket_id not in TREND_BUCKETS:
        raise ValueError(f"Unsupported bucket: {effective_bucket_id}")
    bucket_interval, bucket_min = TREND_BUCKETS[effective_bucket_id]
    bucket_delta = timedelta(minutes=bucket_min)
    total_buckets = max(1, ceil((end_at - start_at).total_seconds() / bucket_delta.total_seconds()))
    if top_keywords is None:
        top_keywords = get_top_keywords(
            source=source,
            domain=domain,
            range_id=range_id,
            limit=limit,
            start_at=start_at,
            end_at=end_at,
        )
    top_lookup = {item["keyword"]: item for item in top_keywords}
    events: list[dict[str, Any]] = []
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    k.keyword,
                    date_bin(%(bucket_interval)s::interval, n.published_at, %(origin)s::timestamptz) AS bucket_start,
                    SUM(k.keyword_count) AS keyword_count
                FROM keywords k
                JOIN news_raw n
                  ON n.provider = k.article_provider
                 AND n.domain = k.article_domain
                 AND n.url = k.article_url
                WHERE n.published_at >= %(start_at)s
                  AND n.published_at < %(end_at)s
                  AND k.keyword = ANY(%(keywords)s)
                  AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                  AND (%(domain)s IS NULL OR n.domain = %(domain)s)
                GROUP BY k.keyword, bucket_start
                ORDER BY k.keyword ASC, bucket_start ASC
                """,
                {
                    "start_at": start_at,
                    "end_at": end_at,
                    "provider": provider,
                    "domain": domain_filter,
                    "bucket_interval": bucket_interval,
                    "origin": start_at,
                    "keywords": [item["keyword"] for item in top_keywords] or [""],
                },
            )
            rows = list(cursor.fetchall())
    per_keyword: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for row in rows:
        bucket_index = int((row["bucket_start"] - start_at).total_seconds() // bucket_delta.total_seconds())
        if 0 <= bucket_index < total_buckets:
            per_keyword[row["keyword"]].append((bucket_index, int(row["keyword_count"] or 0)))
    for keyword_name, values in per_keyword.items():
        previous = 0
        for bucket_index, count in values:
            if count <= 0:
                continue
            growth = _safe_growth(count, previous)
            if growth >= 0.35 and count >= 3:
                summary = top_lookup.get(keyword_name)
                naver_share = float(summary["sourceShareNaver"]) if summary else 0.5
                events.append(
                    {
                        "bucket": bucket_index,
                        "keyword": keyword_name,
                        "intensity": min(1.0, max(0.12, growth)),
                        "source": "naver" if naver_share >= 0.5 else "global",
                        "currentMentions": count,
                        "prevMentions": previous,
                        "growth": growth,
                        "score": int(summary["eventScore"]) if summary else 0,
                    }
                )
            previous = count
    events.sort(key=lambda item: (item["score"], item["growth"]), reverse=True)
    return {
        "topKeywords": [item["keyword"] for item in top_keywords if item["spike"]][:8] or [item["keyword"] for item in top_keywords[:8]],
        "events": events[:limit],
        "range": _window_range_payload(range_spec=range_spec, start_at=start_at, end_at=end_at, bucket_id=effective_bucket_id),
        "sampleSeries": [],
    }


def get_dashboard_overview(
    source: str,
    domain: str,
    range_id: str | None = None,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    fetch_start_at: datetime | None = None,
    fetch_end_at: datetime | None = None,
    bucket_id: str | None = None,
    search: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    _, resolved_start, resolved_end, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    fetch_range_spec, resolved_fetch_start, resolved_fetch_end, _ = _window_bounds(
        range_id=range_id,
        start_at=fetch_start_at or resolved_start,
        end_at=fetch_end_at or resolved_end,
    )
    effective_bucket_id = bucket_id or _pick_auto_bucket_for_window(resolved_end - resolved_start)
    raw_data_start = resolved_fetch_start - (resolved_fetch_end - resolved_fetch_start)
    cache_keywords = get_top_keywords(
        source=source,
        domain=domain,
        range_id=None,
        limit=max(limit * 4, 80),
        search=search,
        start_at=resolved_fetch_start,
        end_at=resolved_fetch_end,
    )
    overview_cache = _fetch_overview_cache_rows(
        source=source,
        domain=domain,
        data_start=raw_data_start,
        data_end=resolved_fetch_end,
        bucket_id=effective_bucket_id,
        keywords=[item["keyword"] for item in cache_keywords],
    )
    derived = _derive_overview_from_cache(
        source=source,
        cache=overview_cache,
        start_at=resolved_start,
        end_at=resolved_end,
        limit=limit,
    )
    return {
        **derived,
        "cache": {
            **overview_cache,
            "fetch_start_at": resolved_fetch_start.isoformat(),
            "fetch_end_at": resolved_fetch_end.isoformat(),
            "requested_start_at": resolved_start.isoformat(),
            "requested_end_at": resolved_end.isoformat(),
            "candidate_keywords": [item["keyword"] for item in cache_keywords],
            "range": _window_range_payload(
                range_spec=fetch_range_spec,
                start_at=resolved_fetch_start,
                end_at=resolved_fetch_end,
                bucket_id=effective_bucket_id,
            ),
        },
    }


def get_related_keywords(
    source: str,
    domain: str,
    range_id: str | None,
    keyword: str,
    limit: int = 10,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    _, start_at, end_at, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                WITH combined AS (
                    SELECT keyword_b AS related_keyword, SUM(cooccurrence_count) AS weight
                    FROM keyword_relations
                    WHERE keyword_a = %(keyword)s
                      AND window_start >= %(start_at)s
                      AND window_start < %(end_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (%(domain)s IS NULL OR domain = %(domain)s)
                    GROUP BY keyword_b
                    UNION ALL
                    SELECT keyword_a AS related_keyword, SUM(cooccurrence_count) AS weight
                    FROM keyword_relations
                    WHERE keyword_b = %(keyword)s
                      AND window_start >= %(start_at)s
                      AND window_start < %(end_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (%(domain)s IS NULL OR domain = %(domain)s)
                    GROUP BY keyword_a
                )
                SELECT related_keyword, SUM(weight) AS weight
                FROM combined
                GROUP BY related_keyword
                ORDER BY SUM(weight) DESC, related_keyword ASC
                LIMIT %(limit)s
                """,
                {
                    "keyword": keyword,
                    "start_at": start_at,
                    "end_at": end_at,
                    "provider": provider,
                    "domain": domain_filter,
                    "limit": limit,
                },
            )
            rows = list(cursor.fetchall())
    if not rows:
        return []
    max_weight = max(float(row["weight"] or 0.0) for row in rows) or 1.0
    return [{"keyword": row["related_keyword"], "weight": round(float(row["weight"] or 0.0) / max_weight, 4)} for row in rows]


def get_theme_distribution(
    source: str,
    range_id: str | None,
    keyword: str,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    _, start_at, end_at, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_definitions = list(DOMAIN_DEFINITIONS)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT domain, SUM(keyword_count) AS mentions
                FROM keyword_trends
                WHERE keyword = %(keyword)s
                  AND window_start >= %(start_at)s
                  AND window_start < %(end_at)s
                  AND (%(provider)s IS NULL OR provider = %(provider)s)
                GROUP BY domain
                """,
                {
                    "keyword": keyword,
                    "start_at": start_at,
                    "end_at": end_at,
                    "provider": provider,
                },
            )
            rows = list(cursor.fetchall())

    mentions_by_domain = {str(row["domain"]): int(row["mentions"] or 0) for row in rows if row.get("domain")}
    total_mentions = sum(mentions_by_domain.values())
    items: list[dict[str, Any]] = []
    for index, domain in enumerate(domain_definitions):
        mentions = mentions_by_domain.get(domain.id, 0)
        items.append(
            {
                "id": domain.id,
                "label": DOMAIN_LABELS.get(domain.id, domain.id),
                "mentions": mentions,
                "share": (mentions / total_mentions) if total_mentions else 0.0,
                "color": THEME_COLORS[index % len(THEME_COLORS)],
            }
        )
    items.sort(key=lambda item: (-item["mentions"], item["label"]))
    return {
        "keyword": keyword,
        "totalMentions": total_mentions,
        "items": items,
    }


def get_articles(
    source: str,
    domain: str,
    range_id: str | None,
    keyword: str | None = None,
    limit: int = 30,
    sort: str = "latest",
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    _, start_at, end_at, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    order_clause = "article_time DESC" if sort == "latest" else "keyword_match DESC, article_time DESC"
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"""
                WITH filtered_articles AS (
                    SELECT
                        n.provider,
                        n.domain,
                        n.url,
                        n.title,
                        COALESCE(n.summary, '') AS summary,
                        COALESCE(NULLIF(n.source, ''), n.provider) AS publisher,
                        COALESCE(n.published_at, n.ingested_at) AS article_time
                    FROM news_raw n
                    WHERE COALESCE(n.published_at, n.ingested_at) >= %(start_at)s
                      AND COALESCE(n.published_at, n.ingested_at) < %(end_at)s
                      AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                      AND (%(domain)s IS NULL OR n.domain = %(domain)s)
                      AND (
                        %(keyword)s IS NULL
                        OR EXISTS (
                            SELECT 1
                            FROM keywords kf
                            WHERE kf.article_provider = n.provider
                              AND kf.article_domain = n.domain
                              AND kf.article_url = n.url
                              AND kf.keyword = %(keyword)s
                        )
                      )
                ),
                article_keywords AS (
                    SELECT
                        k.article_provider,
                        k.article_domain,
                        k.article_url,
                        ARRAY_AGG(k.keyword ORDER BY k.keyword_count DESC, k.keyword ASC) AS keywords
                    FROM keywords k
                    JOIN filtered_articles fa
                      ON fa.provider = k.article_provider
                     AND fa.domain = k.article_domain
                     AND fa.url = k.article_url
                    GROUP BY k.article_provider, k.article_domain, k.article_url
                )
                SELECT
                    CONCAT(fa.provider, ':', fa.domain, ':', fa.url) AS id,
                    fa.title,
                    fa.summary,
                    fa.publisher,
                    fa.provider AS source,
                    fa.domain,
                    fa.article_time,
                    ak.keywords,
                    CASE WHEN %(keyword)s IS NOT NULL AND ak.keywords IS NOT NULL AND %(keyword)s = ANY(ak.keywords) THEN 1 ELSE 0 END AS keyword_match,
                    fa.url
                FROM filtered_articles fa
                LEFT JOIN article_keywords ak
                  ON ak.article_provider = fa.provider
                 AND ak.article_domain = fa.domain
                 AND ak.article_url = fa.url
                ORDER BY {order_clause}
                LIMIT %(limit)s
                """,
                {
                    "start_at": start_at,
                    "end_at": end_at,
                    "provider": provider,
                    "domain": domain_filter,
                    "keyword": keyword,
                    "limit": limit,
                },
            )
            rows = list(cursor.fetchall())
    now = _now_utc()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "publisher": row["publisher"],
            "source": row["source"],
            "domain": row["domain"],
            "publishedAt": row["article_time"],
            "minutesAgo": int(max(0, (now - row["article_time"].astimezone(UTC)).total_seconds() // 60)) if row["article_time"] else None,
            "keywords": row["keywords"] or [],
            "primaryKeyword": (row["keywords"] or [None])[0],
            "duplicates": 0,
            "url": row["url"],
        }
        for row in rows
    ]


def _probe_http(url: str, timeout: float = 1.5) -> tuple[str, str, int | None]:
    try:
        response = requests.get(url, timeout=timeout)
        if response.ok:
            return "ok", "", response.status_code
        return "warn", "", response.status_code
    except requests.RequestException:
        return "down", "", 503


def _probe_tcp(host: str, port: int, timeout: float = 1.0) -> tuple[str, str, int | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok", "", 200
    except OSError:
        return "down", "", 503


def get_system_status() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    kafka_status, kafka_detail, kafka_code = _probe_tcp("kafka", 29092)
    spark_status, spark_detail, spark_code = _probe_http("http://spark-master:8080")
    airflow_status, airflow_detail, airflow_code = _probe_http("http://airflow-apiserver:8080/api/v2/version")
    return {
        "services": [
            {"key": "kafka", "label": "Kafka ingest", "status": kafka_status, "detail": kafka_detail, "statusCode": kafka_code},
            {"key": "spark", "label": "Spark", "status": spark_status, "detail": spark_detail, "statusCode": spark_code},
            {"key": "airflow", "label": "Airflow", "status": airflow_status, "detail": airflow_detail, "statusCode": airflow_code},
            {"key": "api", "label": "API", "status": "ok", "detail": "", "statusCode": 200},
            {"key": "db", "label": "PostgreSQL", "status": "ok", "detail": "", "statusCode": 200},
        ]
    }


def get_trend_window_series(
    source: str,
    domain: str,
    start_at: datetime,
    end_at: datetime,
    bucket_id: str,
    keywords: list[str],
) -> dict[str, Any]:
    if bucket_id not in TREND_BUCKETS:
        raise ValueError(f"Unsupported bucket: {bucket_id}")
    if not keywords:
        return {"series": [], "range": {"id": bucket_id, "label": bucket_id, "bucketMin": TREND_BUCKETS[bucket_id][1], "buckets": 0}}
    if end_at <= start_at:
        raise ValueError("endAt must be later than startAt")

    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    bucket_interval, bucket_min = TREND_BUCKETS[bucket_id]
    bucket_delta = timedelta(minutes=bucket_min)
    start_utc = start_at.astimezone(UTC)
    end_utc = end_at.astimezone(UTC)
    total_buckets = max(1, ceil((end_utc - start_utc).total_seconds() / bucket_delta.total_seconds()))
    if total_buckets > 720:
        raise ValueError("Requested range is too wide for the selected bucket")

    bucket_edges = [start_utc + (bucket_delta * index) for index in range(total_buckets + 1)]
    series_lookup = {
        name: [{"bucket": index, "timestamp": bucket_edges[index], "value": 0} for index in range(total_buckets)]
        for name in keywords
    }
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    k.keyword,
                    date_bin(%(bucket_interval)s::interval, n.published_at, %(origin)s::timestamptz) AS bucket_start,
                    SUM(k.keyword_count) AS keyword_count
                FROM keywords k
                JOIN news_raw n
                  ON n.provider = k.article_provider
                 AND n.domain = k.article_domain
                 AND n.url = k.article_url
                WHERE k.keyword = ANY(%(keywords)s)
                  AND n.published_at >= %(start_at)s
                  AND n.published_at < %(end_at)s
                  AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                  AND (%(domain)s IS NULL OR n.domain = %(domain)s)
                GROUP BY k.keyword, bucket_start
                ORDER BY bucket_start ASC
                """,
                {
                    "start_at": start_utc,
                    "end_at": end_utc,
                    "provider": provider,
                    "domain": domain_filter,
                    "bucket_interval": bucket_interval,
                    "origin": start_utc,
                    "keywords": keywords,
                },
            )
            for row in cursor.fetchall():
                bucket_index = int((row["bucket_start"] - start_utc).total_seconds() // bucket_delta.total_seconds())
                if 0 <= bucket_index < total_buckets and row["keyword"] in series_lookup:
                    series_lookup[row["keyword"]][bucket_index]["value"] = int(row["keyword_count"] or 0)

    return {
        "series": [
            {
                "name": name,
                "color": PALETTE[index % len(PALETTE)],
                "spike": False,
                "points": points,
            }
            for index, (name, points) in enumerate(series_lookup.items())
        ],
        "range": {
            "id": bucket_id,
            "label": bucket_id,
            "bucketMin": bucket_min,
            "buckets": total_buckets,
        },
    }


def get_dictionary_overview() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT COUNT(*) AS cnt FROM compound_noun_dict")
            compound_noun_count = int(cursor.fetchone()["cnt"])
            cursor.execute("SELECT COUNT(*) AS cnt FROM compound_noun_candidates")
            candidate_count = int(cursor.fetchone()["cnt"])
            cursor.execute("SELECT COUNT(*) AS cnt FROM stopword_dict")
            stopword_count = int(cursor.fetchone()["cnt"])
    versions = fetch_dictionary_versions()
    return {
        "compoundNounCount": compound_noun_count,
        "candidateCount": candidate_count,
        "stopwordCount": stopword_count,
        "versions": {
            "compoundNounDict": int(versions.get("compound_noun_dict", 0)),
            "stopwordDict": int(versions.get("stopword_dict", 0)),
        },
    }


def list_compound_nouns_paged(*, page: int = 1, limit: int = 50, q: str = "", domain: str = "") -> dict[str, Any]:
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    domain_clause = ""
    if domain and domain != "all":
        domain_clause = "AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM compound_noun_dict WHERE word ILIKE %s {domain_clause}",
                params,
            )
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, source, created_at
                FROM compound_noun_dict
                WHERE word ILIKE %s {domain_clause}
                ORDER BY created_at DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = list(cursor.fetchall())
    return {"items": items, "total": total, "page": page, "limit": limit}


def list_stopwords_paged(*, page: int = 1, limit: int = 50, q: str = "", domain: str = "") -> dict[str, Any]:
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    domain_clause = ""
    if domain and domain != "all":
        domain_clause = "AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM stopword_dict WHERE word ILIKE %s {domain_clause}",
                params,
            )
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, language, created_at
                FROM stopword_dict
                WHERE word ILIKE %s {domain_clause}
                ORDER BY created_at DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = list(cursor.fetchall())
    return {"items": items, "total": total, "page": page, "limit": limit}


def list_candidates_paged(*, page: int = 1, limit: int = 50, q: str = "", status: str = "", domain: str = "") -> dict[str, Any]:
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    extra_clauses = ""
    if status and status != "all":
        extra_clauses += " AND status = %s"
        params.append(status)
    if domain and domain != "all":
        extra_clauses += " AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM compound_noun_candidates WHERE word ILIKE %s{extra_clauses}",
                params,
            )
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, frequency, doc_count, first_seen_at, last_seen_at, status, reviewed_at, reviewed_by
                FROM compound_noun_candidates
                WHERE word ILIKE %s{extra_clauses}
                ORDER BY status ASC, frequency DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = list(cursor.fetchall())
    return {"items": items, "total": total, "page": page, "limit": limit}


def get_query_keyword_admin_overview() -> dict[str, Any]:
    return {
        "domains": fetch_domain_catalog(),
        "queryKeywords": fetch_all_query_keywords(provider="naver"),
        "auditLogs": fetch_query_keyword_audit_logs(limit=100),
        "collectionMetrics": fetch_collection_metrics_summary(hours=24, provider="naver"),
    }


def get_collection_metrics_overview(hours: int = 24) -> dict[str, Any]:
    return {"items": fetch_collection_metrics_summary(hours=hours, provider="naver")}


def create_compound_noun(word: str, source: str, actor: str = "dashboard-admin", domain: str = "all") -> None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO compound_noun_dict (word, domain, source)
                VALUES (%s, %s, %s)
                ON CONFLICT (word, domain) DO UPDATE SET source = EXCLUDED.source
                RETURNING id, word, domain, source, created_at
                """,
                (word, domain, source),
            )
            after = cursor.fetchone()
    log_dictionary_audit(
        entity_type="compound_noun",
        entity_id=int(after["id"]) if after else None,
        action="upsert",
        before=None,
        after=after,
        actor=actor,
    )


def delete_compound_noun(item_id: int, actor: str = "dashboard-admin") -> None:
    before = fetch_compound_noun_item(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM compound_noun_dict WHERE id = %s", (item_id,))
    log_dictionary_audit(
        entity_type="compound_noun",
        entity_id=item_id,
        action="delete",
        before=before,
        after=None,
        actor=actor,
    )


def review_compound_candidate(candidate_id: int, action: str, reviewed_by: str) -> None:
    before = fetch_compound_candidate_item(candidate_id)
    reviewed_at = _now_utc()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE compound_noun_candidates
                SET status = %s, reviewed_at = %s, reviewed_by = %s
                WHERE id = %s
                RETURNING id, word, frequency, doc_count, first_seen_at, last_seen_at, status, reviewed_at, reviewed_by
                """,
                (action, reviewed_at, reviewed_by, candidate_id),
            )
            row = cursor.fetchone()
            if row and action == "approved":
                cursor.execute(
                    """
                    INSERT INTO compound_noun_dict (word, domain, source)
                    VALUES (%s, %s, 'candidate-approved')
                    ON CONFLICT (word, domain) DO NOTHING
                    """,
                    (row["word"], row.get("domain", "all")),
                )
    log_dictionary_audit(
        entity_type="compound_candidate",
        entity_id=candidate_id,
        action=action,
        before=before,
        after=row,
        actor=reviewed_by,
    )


def create_stopword(word: str, language: str, actor: str = "dashboard-admin", domain: str = "all") -> None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO stopword_dict (word, domain, language)
                VALUES (%s, %s, %s)
                ON CONFLICT (word, domain, language) DO UPDATE SET language = EXCLUDED.language
                RETURNING id, word, domain, language, created_at
                """,
                (word, domain, language),
            )
            after = cursor.fetchone()
    log_dictionary_audit(
        entity_type="stopword",
        entity_id=int(after["id"]) if after else None,
        action="upsert",
        before=None,
        after=after,
        actor=actor,
    )


def update_compound_noun_domain(item_id: int, domain: str, actor: str = "dashboard-admin") -> None:
    before = fetch_compound_noun_item(item_id)
    after = db_update_compound_noun_domain(item_id=item_id, domain=domain)
    log_dictionary_audit(
        entity_type="compound_noun",
        entity_id=item_id,
        action="update_domain",
        before=before,
        after=after,
        actor=actor,
    )


def update_stopword_domain(item_id: int, domain: str, actor: str = "dashboard-admin") -> None:
    before = fetch_stopword_item(item_id)
    after = db_update_stopword_domain(item_id=item_id, domain=domain)
    log_dictionary_audit(
        entity_type="stopword",
        entity_id=item_id,
        action="update_domain",
        before=before,
        after=after,
        actor=actor,
    )


def delete_stopword(item_id: int, actor: str = "dashboard-admin") -> None:
    before = fetch_stopword_item(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM stopword_dict WHERE id = %s", (item_id,))
    log_dictionary_audit(
        entity_type="stopword",
        entity_id=item_id,
        action="delete",
        before=before,
        after=None,
        actor=actor,
    )


def list_stopword_candidates_paged(*, page: int = 1, limit: int = 50, q: str = "", status: str = "", domain: str = "") -> dict[str, Any]:
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    extra_clauses = ""
    if status and status != "all":
        extra_clauses += " AND status = %s"
        params.append(status)
    if domain and domain != "all":
        extra_clauses += " AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM stopword_candidates WHERE word ILIKE %s{extra_clauses}",
                params,
            )
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, language, score, domain_breadth, repetition_rate,
                       trend_stability, cooccurrence_breadth, short_word, frequency,
                       status, first_seen_at, last_seen_at, reviewed_at, reviewed_by
                FROM stopword_candidates
                WHERE word ILIKE %s{extra_clauses}
                ORDER BY score DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = list(cursor.fetchall())
    return {"items": items, "total": total, "page": page, "limit": limit}


def approve_stopword_candidate(candidate_id: int, reviewed_by: str) -> None:
    before = fetch_stopword_candidate_item(candidate_id)
    after = db_review_stopword_candidate(candidate_id, "approved", reviewed_by)
    log_dictionary_audit(
        entity_type="stopword_candidate",
        entity_id=candidate_id,
        action="approved",
        before=before,
        after=after,
        actor=reviewed_by,
    )


def reject_stopword_candidate(candidate_id: int, reviewed_by: str) -> None:
    before = fetch_stopword_candidate_item(candidate_id)
    after = db_review_stopword_candidate(candidate_id, "rejected", reviewed_by)
    log_dictionary_audit(
        entity_type="stopword_candidate",
        entity_id=candidate_id,
        action="rejected",
        before=before,
        after=after,
        actor=reviewed_by,
    )


def trigger_compound_auto_approve() -> dict[str, int]:
    from analytics.compound_auto_approver import run_compound_auto_approve
    return run_compound_auto_approve()


def trigger_stopword_recommender() -> dict[str, int]:
    from analytics.stopword_recommender import run_stopword_recommender
    return run_stopword_recommender()


def create_query_keyword(domain_id: str, query: str, sort_order: int, actor: str) -> dict[str, Any]:
    return db_create_query_keyword(
        provider="naver",
        domain_id=domain_id,
        query=query,
        sort_order=sort_order,
        actor=actor,
    )


def update_query_keyword(item_id: int, domain_id: str, query: str, sort_order: int, is_active: bool, actor: str) -> dict[str, Any]:
    return db_update_query_keyword(
        item_id=item_id,
        domain_id=domain_id,
        query=query,
        sort_order=sort_order,
        is_active=is_active,
        actor=actor,
    )


def delete_query_keyword(item_id: int, actor: str) -> None:
    db_delete_query_keyword(item_id=item_id, actor=actor)
