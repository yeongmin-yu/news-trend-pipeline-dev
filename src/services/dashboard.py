from __future__ import annotations

import socket
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

import requests
from psycopg2.extras import RealDictCursor

from storage.db import fetch_domain_catalog, get_connection
from services._utils import (
    PALETTE,
    RANGES,
    SOURCES,
    THEME_COLORS,
    TREND_BUCKETS,
    _bucket_index,
    _domain_filter,
    _format_relative,
    _now_utc,
    _normalize_utc,
    _pick_auto_bucket_for_window,
    _provider_filter,
    _publisher_source_options,
    _range_bounds,
    _safe_growth,
    _score_keyword,
    _window_bounds,
    _window_range_payload,
)


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

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


def _fetch_overview_cache_rows(
    *,
    source: str,
    domain: str,
    data_start: datetime,
    data_end: datetime,
    bucket_id: str,
    keywords: list[str],
) -> dict[str, Any]:
    """기사 수·키워드 언급 수를 bucket 단위로 집계한 캐시 데이터를 조회한다."""
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
                  AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
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
                idx = _bucket_index(bucket_start, data_start, bucket_delta)
                if 0 <= idx < total_buckets:
                    article_buckets[idx] = {
                        "bucket": idx,
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
                      AND (cardinality(%(domain)s::text[]) = 0 OR n.domain = ANY(%(domain)s::text[]))
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
                    idx = _bucket_index(bucket_start, data_start, bucket_delta)
                    if 0 <= idx < total_buckets:
                        keyword_buckets.append(
                            {
                                "keyword": row["keyword"],
                                "bucket": idx,
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
    """캐시 데이터에서 KPI·키워드를 계산해 개요 payload를 도출한다."""
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
        lambda: {"mentions": [0] * len(article_rows), "articleCounts": [0] * len(article_rows)}
    )
    for row in keyword_rows:
        keyword = str(row["keyword"])
        bucket_index = int(row["bucket"])
        if 0 <= bucket_index < len(article_rows):
            keyword_map[keyword]["mentions"][bucket_index] = int(row["mentions"] or 0)
            keyword_map[keyword]["articleCounts"][bucket_index] = int(row["articleCount"] or 0)

    current_indices = [
        idx for idx, row in enumerate(article_rows)
        if start_at <= _normalize_utc(datetime.fromisoformat(row["timestamp"])) < end_at
    ]
    prev_indices = [
        idx for idx, row in enumerate(article_rows)
        if prev_start <= _normalize_utc(datetime.fromisoformat(row["timestamp"])) < start_at
    ]

    current_articles = sum(article_counts[idx] for idx in current_indices)
    prev_articles = sum(article_counts[idx] for idx in prev_indices)
    last_update = max(
        (last_updates[idx] for idx in current_indices if last_updates[idx] is not None),
        default=None,
    )
    article_growth = _safe_growth(current_articles, prev_articles)
    keywords: list[dict[str, Any]] = []

    for keyword, series in keyword_map.items():
        current_mentions = sum(series["mentions"][idx] for idx in current_indices)
        prev_mentions = sum(series["mentions"][idx] for idx in prev_indices)
        if current_mentions <= 0:
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
                "articleCount": sum(series["articleCounts"][idx] for idx in current_indices),
            }
        )

    keywords.sort(key=lambda item: (-int(item["mentions"]), item["keyword"]))

    return {
        "kpis": {
            "totalArticles": current_articles,
            "uniqueKeywords": sum(1 for item in keywords if int(item["mentions"]) > 0),
            "spikeCount": sum(1 for item in keywords if item["spike"]),
            "growth": article_growth,
            "lastUpdateRelative": _format_relative(last_update),
            "lastUpdateAbsolute": last_update.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if last_update else "데이터 없음",
        },
        "keywords": keywords[:limit],
    }


# ── 공개 서비스 함수 ──────────────────────────────────────────────────────────

def get_filters() -> dict[str, Any]:
    """대시보드 필터 선택지 (도메인·소스·range) 반환."""
    domains = [{"id": "all", "label": "전체", "available": True}]
    domains.extend(fetch_domain_catalog())
    return {
        "domains": domains,
        "sources": [*SOURCES, *_publisher_source_options()],
        "ranges": [
            {"id": spec.id, "label": spec.label, "bucketMin": spec.bucket_min, "buckets": spec.buckets}
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
    """기간 내 KPI (총 기사·고유 키워드·스파이크 수·성장률) 반환."""
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
                  AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                """,
                {"start_at": start_at, "end_at": end_at, "prev_start_at": prev_start_at, "provider": provider, "domain": domain_filter},
            )
            article_row = cursor.fetchone() or {}
            cursor.execute(
                """
                SELECT COUNT(DISTINCT keyword) AS unique_keywords
                FROM keyword_trends
                WHERE window_start >= %(start_at)s
                  AND window_start < %(end_at)s
                  AND (%(provider)s IS NULL OR provider = %(provider)s)
                  AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                """,
                {"start_at": start_at, "end_at": end_at, "provider": provider, "domain": domain_filter},
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
                  AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                """,
                {"start_at": start_at, "end_at": end_at, "provider": provider, "domain": domain_filter},
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
    """언급 횟수 기준 상위 키워드 목록 반환."""
    _, start_at, end_at, prev_start_at = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    params = {
        "start_at": start_at, "end_at": end_at, "prev_start_at": prev_start_at,
        "provider": provider, "domain": domain_filter,
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
                    WHERE window_start >= %(start_at)s AND window_start < %(end_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                    GROUP BY keyword
                ),
                prev_counts AS (
                    SELECT keyword, SUM(keyword_count) AS mentions
                    FROM keyword_trends
                    WHERE window_start >= %(prev_start_at)s AND window_start < %(start_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                    GROUP BY keyword
                ),
                article_counts AS (
                    SELECT k.keyword, COUNT(DISTINCT k.article_url) AS article_count
                    FROM keywords k
                    JOIN news_raw n ON n.url = k.article_url AND n.provider = k.article_provider AND n.domain = k.article_domain
                    WHERE COALESCE(n.published_at, n.ingested_at) >= %(start_at)s
                      AND COALESCE(n.published_at, n.ingested_at) < %(end_at)s
                      AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                      AND (cardinality(%(domain)s::text[]) = 0 OR n.domain = ANY(%(domain)s::text[]))
                    GROUP BY k.keyword
                )
                SELECT c.keyword, c.mentions, COALESCE(p.mentions, 0) AS prev_mentions, COALESCE(a.article_count, 0) AS article_count
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
            source_share_naver, source_share_rss = 1.0, 0.0
        elif source != "all":
            source_share_naver, source_share_rss = 0.0, 1.0
        else:
            source_share_naver, source_share_rss = 0.5, 0.5
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
                "sourceShareRss": source_share_rss,
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
    """비교 키워드(최대 5개)의 시간대별 언급 추이 시계열 반환."""
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
    bucket_edges = [start_at + timedelta(minutes=spec.bucket_min * i) for i in range(spec.buckets + 1)]
    bucket_map = {i: bucket_edges[i] for i in range(spec.buckets)}
    series_lookup = {
        name: [{"bucket": i, "timestamp": bucket_map[i], "value": 0} for i in range(spec.buckets)]
        for name in compare_keywords
    }
    if compare_keywords:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT keyword, window_start, SUM(keyword_count) AS keyword_count
                    FROM keyword_trends
                    WHERE window_start >= %(start_at)s AND window_start < %(end_at)s
                      AND keyword = ANY(%(keywords)s)
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                    GROUP BY keyword, window_start
                    ORDER BY window_start ASC
                    """,
                    {"start_at": start_at, "end_at": end_at, "keywords": compare_keywords, "provider": provider, "domain": domain_filter},
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
                "color": PALETTE[i % len(PALETTE)],
                "spike": bool(summary_lookup.get(name, {}).get("spike", False)),
                "points": points,
            }
            for i, (name, points) in enumerate(series_lookup.items())
        ],
        "range": {"id": spec.id, "label": spec.label, "bucketMin": spec.bucket_min, "buckets": spec.buckets},
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
    """지정 시간 범위의 KPI·키워드·스파이크·기사를 한 번에 집계해 반환한다."""
    _, resolved_start, resolved_end, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    fetch_range_spec, resolved_fetch_start, resolved_fetch_end, _ = _window_bounds(
        range_id=range_id,
        start_at=fetch_start_at or resolved_start,
        end_at=fetch_end_at or resolved_end,
    )
    effective_bucket_id = bucket_id or _pick_auto_bucket_for_window(resolved_end - resolved_start)
    raw_data_start = resolved_fetch_start - (resolved_fetch_end - resolved_fetch_start)
    cache_keywords = get_top_keywords(
        source=source, domain=domain, range_id=None, limit=max(limit * 4, 80),
        search=search, start_at=resolved_fetch_start, end_at=resolved_fetch_end,
    )
    overview_cache = _fetch_overview_cache_rows(
        source=source, domain=domain, data_start=raw_data_start, data_end=resolved_fetch_end,
        bucket_id=effective_bucket_id, keywords=[item["keyword"] for item in cache_keywords],
    )
    derived = _derive_overview_from_cache(
        source=source, cache=overview_cache, start_at=resolved_start, end_at=resolved_end, limit=limit,
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
                range_spec=fetch_range_spec, start_at=resolved_fetch_start,
                end_at=resolved_fetch_end, bucket_id=effective_bucket_id,
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
    """특정 키워드와 함께 자주 등장하는 연관 키워드를 가중치 순으로 반환한다."""
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
                    WHERE keyword_a = %(keyword)s AND window_start >= %(start_at)s AND window_start < %(end_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                    GROUP BY keyword_b
                    UNION ALL
                    SELECT keyword_a AS related_keyword, SUM(cooccurrence_count) AS weight
                    FROM keyword_relations
                    WHERE keyword_b = %(keyword)s AND window_start >= %(start_at)s AND window_start < %(end_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (cardinality(%(domain)s::text[]) = 0 OR domain = ANY(%(domain)s::text[]))
                    GROUP BY keyword_a
                )
                SELECT related_keyword, SUM(weight) AS weight
                FROM combined
                GROUP BY related_keyword
                ORDER BY SUM(weight) DESC, related_keyword ASC
                LIMIT %(limit)s
                """,
                {"keyword": keyword, "start_at": start_at, "end_at": end_at, "provider": provider, "domain": domain_filter, "limit": limit},
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
    """특정 키워드의 도메인별 언급 비율 분포를 반환한다."""
    _, start_at, end_at, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_catalog = fetch_domain_catalog()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT domain, SUM(keyword_count) AS mentions
                FROM keyword_trends
                WHERE keyword = %(keyword)s AND window_start >= %(start_at)s AND window_start < %(end_at)s
                  AND (%(provider)s IS NULL OR provider = %(provider)s)
                GROUP BY domain
                """,
                {"keyword": keyword, "start_at": start_at, "end_at": end_at, "provider": provider},
            )
            rows = list(cursor.fetchall())
    mentions_by_domain = {str(row["domain"]): int(row["mentions"] or 0) for row in rows if row.get("domain")}
    total_mentions = sum(mentions_by_domain.values())
    items: list[dict[str, Any]] = []
    for i, domain in enumerate(domain_catalog):
        domain_id = str(domain["id"])
        mentions = mentions_by_domain.get(domain_id, 0)
        items.append(
            {
                "id": domain_id,
                "label": str(domain.get("label") or domain_id),
                "mentions": mentions,
                "share": (mentions / total_mentions) if total_mentions else 0.0,
                "color": THEME_COLORS[i % len(THEME_COLORS)],
            }
        )
    items.sort(key=lambda item: (-item["mentions"], item["label"]))
    return {"keyword": keyword, "totalMentions": total_mentions, "items": items}


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
    """조건에 맞는 뉴스 기사 목록을 정렬 기준에 따라 반환한다."""
    _, start_at, end_at, _ = _window_bounds(range_id=range_id, start_at=start_at, end_at=end_at)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    order_clause = "article_time DESC" if sort == "latest" else "keyword_match DESC, article_time DESC"
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"""
                WITH filtered_articles AS (
                    SELECT n.provider, n.domain, n.url, n.title,
                           COALESCE(n.summary, '') AS summary,
                           COALESCE(NULLIF(n.source, ''), n.provider) AS publisher,
                           COALESCE(n.published_at, n.ingested_at) AS article_time
                    FROM news_raw n
                    WHERE COALESCE(n.published_at, n.ingested_at) >= %(start_at)s
                      AND COALESCE(n.published_at, n.ingested_at) < %(end_at)s
                      AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                      AND (cardinality(%(domain)s::text[]) = 0 OR n.domain = ANY(%(domain)s::text[]))
                      AND (
                        %(keyword)s IS NULL
                        OR EXISTS (
                            SELECT 1 FROM keywords kf
                            WHERE kf.article_provider = n.provider AND kf.article_domain = n.domain
                              AND kf.article_url = n.url AND kf.keyword = %(keyword)s
                        )
                      )
                ),
                article_keywords AS (
                    SELECT k.article_provider, k.article_domain, k.article_url,
                           ARRAY_AGG(k.keyword ORDER BY k.keyword_count DESC, k.keyword ASC) AS keywords
                    FROM keywords k
                    JOIN filtered_articles fa ON fa.provider = k.article_provider AND fa.domain = k.article_domain AND fa.url = k.article_url
                    GROUP BY k.article_provider, k.article_domain, k.article_url
                )
                SELECT
                    CONCAT(fa.provider, ':', fa.domain, ':', fa.url) AS id,
                    fa.title, fa.summary, fa.publisher, fa.provider AS source, fa.domain, fa.article_time,
                    ak.keywords,
                    CASE WHEN %(keyword)s IS NOT NULL AND ak.keywords IS NOT NULL AND %(keyword)s = ANY(ak.keywords) THEN 1 ELSE 0 END AS keyword_match,
                    fa.url
                FROM filtered_articles fa
                LEFT JOIN article_keywords ak ON ak.article_provider = fa.provider AND ak.article_domain = fa.domain AND ak.article_url = fa.url
                ORDER BY {order_clause}
                LIMIT %(limit)s
                """,
                {"start_at": start_at, "end_at": end_at, "provider": provider, "domain": domain_filter, "keyword": keyword, "limit": limit},
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


def get_system_status() -> dict[str, Any]:
    """Kafka·Spark·Airflow·DB 등 각 서비스 컴포넌트의 헬스 상태를 반환한다."""
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
    """커스텀 기간·bucket 단위로 키워드 시계열 데이터를 반환한다."""
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
    start_utc = _normalize_utc(start_at)
    end_utc = _normalize_utc(end_at)
    total_buckets = max(1, ceil((end_utc - start_utc).total_seconds() / bucket_delta.total_seconds()))
    if total_buckets > 720:
        raise ValueError("Requested range is too wide for the selected bucket")

    bucket_edges = [start_utc + (bucket_delta * i) for i in range(total_buckets + 1)]
    series_lookup = {
        name: [{"bucket": i, "timestamp": bucket_edges[i], "value": 0} for i in range(total_buckets)]
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
                JOIN news_raw n ON n.provider = k.article_provider AND n.domain = k.article_domain AND n.url = k.article_url
                WHERE k.keyword = ANY(%(keywords)s)
                  AND n.published_at >= %(start_at)s AND n.published_at < %(end_at)s
                  AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                  AND (cardinality(%(domain)s::text[]) = 0 OR n.domain = ANY(%(domain)s::text[]))
                GROUP BY k.keyword, bucket_start
                ORDER BY bucket_start ASC
                """,
                {
                    "start_at": start_utc, "end_at": end_utc, "provider": provider, "domain": domain_filter,
                    "bucket_interval": bucket_interval, "origin": start_utc, "keywords": keywords,
                },
            )
            for row in cursor.fetchall():
                bucket_index = int((row["bucket_start"] - start_utc).total_seconds() // bucket_delta.total_seconds())
                if 0 <= bucket_index < total_buckets and row["keyword"] in series_lookup:
                    series_lookup[row["keyword"]][bucket_index]["value"] = int(row["keyword_count"] or 0)

    return {
        "series": [
            {"name": name, "color": PALETTE[i % len(PALETTE)], "spike": False, "points": points}
            for i, (name, points) in enumerate(series_lookup.items())
        ],
        "range": {"id": bucket_id, "label": bucket_id, "bucketMin": bucket_min, "buckets": total_buckets},
    }
