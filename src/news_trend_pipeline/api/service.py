from __future__ import annotations

import socket
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from psycopg2.extras import RealDictCursor

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.domains import DOMAIN_DEFINITIONS, DOMAIN_LABELS
from news_trend_pipeline.storage.db import (
    create_query_keyword as db_create_query_keyword,
    delete_query_keyword as db_delete_query_keyword,
    fetch_all_query_keywords,
    fetch_collection_metrics_summary,
    fetch_compound_candidate_item,
    fetch_compound_noun_item,
    fetch_dictionary_audit_logs,
    fetch_dictionary_versions,
    fetch_domain_catalog,
    fetch_keyword_event_rows,
    fetch_query_keyword_audit_logs,
    fetch_stopword_item,
    get_connection,
    log_dictionary_audit,
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

PALETTE = ["#5eead4", "#f472b6", "#fbbf24", "#60a5fa", "#a78bfa"]
THEME_COLORS = ["#5eead4", "#f472b6", "#fbbf24", "#60a5fa"]


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


def get_kpis(source: str, domain: str, range_id: str) -> dict[str, Any]:
    _, start_at, end_at, prev_start_at = _range_bounds(range_id)
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
            keywords = get_top_keywords(source=source, domain=domain, range_id=range_id, limit=100, search=None)
    spike_count = sum(1 for item in keywords if item["spike"])
    growth = _safe_growth(article_row.get("current_articles") or 0, article_row.get("prev_articles") or 0)
    last_update = article_row.get("last_update")
    return {
        "totalArticles": int(article_row.get("current_articles") or 0),
        "uniqueKeywords": int(unique_row.get("unique_keywords") or 0),
        "spikeCount": spike_count,
        "growth": growth,
        "lastUpdateRelative": _format_relative(last_update),
        "lastUpdateAbsolute": last_update.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if last_update else "데이터 없음",
    }


def get_top_keywords(
    source: str,
    domain: str,
    range_id: str,
    limit: int = 30,
    search: str | None = None,
) -> list[dict[str, Any]]:
    _, start_at, end_at, prev_start_at = _range_bounds(range_id)
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
                ),
                source_counts AS (
                    SELECT k.keyword, k.article_provider AS provider_name, SUM(k.keyword_count) AS provider_mentions
                    FROM keywords k
                    JOIN news_raw n
                      ON n.url = k.article_url
                     AND n.provider = k.article_provider
                     AND n.domain = k.article_domain
                    WHERE COALESCE(n.published_at, n.ingested_at) >= %(start_at)s
                      AND COALESCE(n.published_at, n.ingested_at) < %(end_at)s
                      AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                      AND (%(domain)s IS NULL OR n.domain = %(domain)s)
                    GROUP BY k.keyword, k.article_provider
                )
                SELECT
                    c.keyword,
                    c.mentions,
                    COALESCE(p.mentions, 0) AS prev_mentions,
                    COALESCE(a.article_count, 0) AS article_count,
                    COALESCE(SUM(CASE WHEN s.provider_name = 'naver' THEN s.provider_mentions END), 0) AS naver_mentions,
                    COALESCE(SUM(CASE WHEN s.provider_name = 'global' THEN s.provider_mentions END), 0) AS global_mentions
                FROM current_counts c
                LEFT JOIN prev_counts p ON p.keyword = c.keyword
                LEFT JOIN article_counts a ON a.keyword = c.keyword
                LEFT JOIN source_counts s ON s.keyword = c.keyword
                WHERE (%(search)s IS NULL OR c.keyword ILIKE %(search)s)
                GROUP BY c.keyword, c.mentions, p.mentions, a.article_count
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
        total = int(row["naver_mentions"] or 0) + int(row["global_mentions"] or 0)
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
                "sourceShareNaver": (int(row["naver_mentions"] or 0) / total) if total else 0.0,
                "sourceShareGlobal": (int(row["global_mentions"] or 0) / total) if total else 0.0,
            }
        )
    return result


def get_trend_series(source: str, domain: str, range_id: str, keyword: str, compare_limit: int = 4) -> dict[str, Any]:
    spec, start_at, end_at, _ = _range_bounds(range_id)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    top_keywords = get_top_keywords(source=source, domain=domain, range_id=range_id, limit=max(compare_limit * 2, 20))
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


def get_spike_events(source: str, domain: str, range_id: str, limit: int = 32) -> dict[str, Any]:
    spec, start_at, end_at, _ = _range_bounds(range_id)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    top_keywords = get_top_keywords(source=source, domain=domain, range_id=range_id, limit=limit)
    selected_keyword = top_keywords[0]["keyword"] if top_keywords else ""
    trend = get_trend_series(source=source, domain=domain, range_id=range_id, keyword=selected_keyword, compare_limit=1) if selected_keyword else {"series": []}
    event_rows = fetch_keyword_event_rows(
        start_at=start_at,
        end_at=end_at,
        provider=provider,
        domain=domain_filter,
    )
    top_lookup = {item["keyword"]: item for item in top_keywords}
    events: list[dict[str, Any]] = []
    if event_rows:
        for row in event_rows:
            bucket_index = int((row["window_start"] - start_at).total_seconds() // (spec.bucket_min * 60))
            if 0 <= bucket_index < spec.buckets:
                summary = top_lookup.get(row["keyword"])
                naver_share = float(summary["sourceShareNaver"]) if summary else 0.5
                events.append(
                    {
                        "bucket": bucket_index,
                        "keyword": row["keyword"],
                        "intensity": min(1.0, max(0.12, float(row["growth"] or 0.0))),
                        "source": "naver" if naver_share >= 0.5 else "global",
                        "growth": float(row["growth"] or 0.0),
                        "score": int(row["event_score"] or 0),
                    }
                )
    else:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT keyword, window_start, SUM(keyword_count) AS keyword_count
                    FROM keyword_trends
                    WHERE window_start >= %(start_at)s
                      AND window_start < %(end_at)s
                      AND (%(provider)s IS NULL OR provider = %(provider)s)
                      AND (%(domain)s IS NULL OR domain = %(domain)s)
                    GROUP BY keyword, window_start
                    ORDER BY keyword ASC, window_start ASC
                    """,
                    {
                        "start_at": start_at,
                        "end_at": end_at,
                        "provider": provider,
                        "domain": domain_filter,
                    },
                )
                rows = list(cursor.fetchall())
        per_keyword: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for row in rows:
            bucket_index = int((row["window_start"] - start_at).total_seconds() // (spec.bucket_min * 60))
            if 0 <= bucket_index < spec.buckets:
                per_keyword[row["keyword"]].append((bucket_index, int(row["keyword_count"] or 0)))
        for keyword_name, values in per_keyword.items():
            values.sort(key=lambda item: item[0])
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
                            "growth": growth,
                            "score": int(summary["eventScore"]) if summary else 0,
                        }
                    )
                previous = count
    events.sort(key=lambda item: (item["score"], item["growth"]), reverse=True)
    return {
        "topKeywords": [item["keyword"] for item in top_keywords if item["spike"]][:8] or [item["keyword"] for item in top_keywords[:8]],
        "events": events[:limit],
        "range": {
            "id": spec.id,
            "label": spec.label,
            "bucketMin": spec.bucket_min,
            "buckets": spec.buckets,
        },
        "sampleSeries": trend["series"],
    }


def get_related_keywords(source: str, domain: str, range_id: str, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
    _, start_at, end_at, _ = _range_bounds(range_id)
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


def get_theme_distribution(source: str, range_id: str, keyword: str) -> dict[str, Any]:
    _, start_at, end_at, _ = _range_bounds(range_id)
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
    range_id: str,
    keyword: str | None = None,
    limit: int = 30,
    sort: str = "latest",
) -> list[dict[str, Any]]:
    _, start_at, end_at, _ = _range_bounds(range_id)
    provider = _provider_filter(source)
    domain_filter = _domain_filter(domain)
    order_clause = "article_time DESC" if sort == "latest" else "keyword_match DESC, article_time DESC"
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"""
                WITH article_keywords AS (
                    SELECT
                        k.article_provider,
                        k.article_domain,
                        k.article_url,
                        ARRAY_AGG(k.keyword ORDER BY k.keyword_count DESC, k.keyword ASC) AS keywords
                    FROM keywords k
                    GROUP BY k.article_provider, k.article_domain, k.article_url
                )
                SELECT
                    CONCAT(n.provider, ':', n.domain, ':', n.url) AS id,
                    n.title,
                    COALESCE(n.summary, '') AS summary,
                    COALESCE(NULLIF(n.source, ''), n.provider) AS publisher,
                    n.provider AS source,
                    n.domain,
                    COALESCE(n.published_at, n.ingested_at) AS article_time,
                    ak.keywords,
                    CASE WHEN %(keyword)s IS NOT NULL AND ak.keywords IS NOT NULL AND %(keyword)s = ANY(ak.keywords) THEN 1 ELSE 0 END AS keyword_match,
                    n.url
                FROM news_raw n
                LEFT JOIN article_keywords ak
                  ON ak.article_provider = n.provider
                 AND ak.article_domain = n.domain
                 AND ak.article_url = n.url
                WHERE COALESCE(n.published_at, n.ingested_at) >= %(start_at)s
                  AND COALESCE(n.published_at, n.ingested_at) < %(end_at)s
                  AND (%(provider)s IS NULL OR n.provider = %(provider)s)
                  AND (%(domain)s IS NULL OR n.domain = %(domain)s)
                  AND (%(keyword)s IS NULL OR (%(keyword)s = ANY(COALESCE(ak.keywords, ARRAY[]::varchar[]))))
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


def _probe_http(url: str, timeout: float = 1.5) -> tuple[str, str]:
    try:
        response = requests.get(url, timeout=timeout)
        if response.ok:
            return "ok", f"{response.status_code}"
        return "warn", f"{response.status_code}"
    except requests.RequestException:
        return "down", "unreachable"


def _probe_tcp(host: str, port: int, timeout: float = 1.0) -> tuple[str, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok", f"{host}:{port}"
    except OSError:
        return "down", f"{host}:{port}"


def get_system_status() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    kafka_status, kafka_detail = _probe_tcp("kafka", 29092)
    spark_status, spark_detail = _probe_http("http://spark-master:8080")
    airflow_status, airflow_detail = _probe_http("http://airflow-apiserver:8080/api/v2/version")
    parsed = urlparse("http://localhost")
    return {
        "services": [
            {"key": "kafka", "label": "Kafka ingest", "status": kafka_status, "detail": kafka_detail},
            {"key": "spark", "label": "Spark", "status": spark_status, "detail": spark_detail},
            {"key": "airflow", "label": "Airflow", "status": airflow_status, "detail": airflow_detail},
            {"key": "api", "label": "API", "status": "ok", "detail": parsed.hostname or "self"},
            {"key": "db", "label": "PostgreSQL", "status": "ok", "detail": settings.postgres_host},
        ]
    }


def get_dictionary_overview() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, word, source, created_at
                FROM compound_noun_dict
                ORDER BY created_at DESC, word ASC
                """
            )
            compound_nouns = list(cursor.fetchall())
            cursor.execute(
                """
                SELECT id, word, frequency, doc_count, first_seen_at, last_seen_at, status, reviewed_at, reviewed_by
                FROM compound_noun_candidates
                ORDER BY status ASC, frequency DESC, word ASC
                """
            )
            compound_candidates = list(cursor.fetchall())
            cursor.execute(
                """
                SELECT id, word, language, created_at
                FROM stopword_dict
                ORDER BY created_at DESC, word ASC
                """
            )
            stopwords = list(cursor.fetchall())
    versions = fetch_dictionary_versions()
    return {
        "compoundNouns": compound_nouns,
        "compoundCandidates": compound_candidates,
        "stopwords": stopwords,
        "auditLogs": fetch_dictionary_audit_logs(limit=100),
        "versions": {
            "compoundNounDict": int(versions.get("compound_noun_dict", 0)),
            "stopwordDict": int(versions.get("stopword_dict", 0)),
        },
    }


def get_query_keyword_admin_overview() -> dict[str, Any]:
    return {
        "domains": fetch_domain_catalog(),
        "queryKeywords": fetch_all_query_keywords(provider="naver"),
        "auditLogs": fetch_query_keyword_audit_logs(limit=100),
        "collectionMetrics": fetch_collection_metrics_summary(hours=24, provider="naver"),
    }


def get_collection_metrics_overview(hours: int = 24) -> dict[str, Any]:
    return {"items": fetch_collection_metrics_summary(hours=hours, provider="naver")}


def create_compound_noun(word: str, source: str, actor: str = "dashboard-admin") -> None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO compound_noun_dict (word, source)
                VALUES (%s, %s)
                ON CONFLICT (word) DO UPDATE SET source = EXCLUDED.source
                RETURNING id, word, source, created_at
                """,
                (word, source),
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
                    INSERT INTO compound_noun_dict (word, source)
                    VALUES (%s, 'candidate-approved')
                    ON CONFLICT (word) DO NOTHING
                    """,
                    (row["word"],),
                )
    log_dictionary_audit(
        entity_type="compound_candidate",
        entity_id=candidate_id,
        action=action,
        before=before,
        after=row,
        actor=reviewed_by,
    )


def create_stopword(word: str, language: str, actor: str = "dashboard-admin") -> None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO stopword_dict (word, language)
                VALUES (%s, %s)
                ON CONFLICT (word, language) DO UPDATE SET language = EXCLUDED.language
                RETURNING id, word, language, created_at
                """,
                (word, language),
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
