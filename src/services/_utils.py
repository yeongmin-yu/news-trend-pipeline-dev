from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

from core.config import settings
from storage.db import fetch_domain_catalog, get_connection


# ── 타입·상수 ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RangeSpec:
    id: str
    label: str
    bucket_min: int
    buckets: int

    @property
    def duration(self) -> timedelta:
        return timedelta(minutes=self.bucket_min * self.buckets)


class DictionaryItemNotFoundError(ValueError):
    pass


class DictionaryDomainConflictError(ValueError):
    pass


class AirflowTriggerError(RuntimeError):
    pass


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
    {"id": "naver", "label": "NaverNews", "color": "#34d399"},
]

PALETTE = ["#8b5cf6", "#0ea5e9", "#22c55e", "#f59e0b", "#64748b"]
THEME_COLORS = ["#5eead4", "#f472b6", "#fbbf24", "#60a5fa"]

TREND_BUCKETS: dict[str, tuple[str, int]] = {
    "5m": ("5 minutes", 5),
    "15m": ("15 minutes", 15),
    "30m": ("30 minutes", 30),
    "1h": ("1 hour", 60),
    "4h": ("4 hours", 240),
    "1d": ("1 day", 1440),
}


# ── 소스·도메인 필터 ───────────────────────────────────────────────────────────

def _provider_filter(source: str) -> str | None:
    if source == "global":
        return None
    return None if source == "all" else source


def _publisher_source_options() -> list[dict[str, str]]:
    """DB에서 naver 외 퍼블리셔 목록을 조회해 소스 선택지로 반환한다."""
    try:
        from psycopg2.extras import RealDictCursor
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT provider
                    FROM news_raw
                    WHERE provider IS NOT NULL
                      AND provider <> 'naver'
                    ORDER BY provider
                """)
                rows = cursor.fetchall()
    except Exception:
        return []

    existing_ids = {item["id"] for item in SOURCES}
    palette = [
        "#f59e0b", "#60a5fa", "#f472b6", "#22c55e",
        "#c084fc", "#38bdf8", "#fb7185", "#94a3b8",
    ]
    options = []
    for i, row in enumerate(rows):
        provider = str(row[0]).strip()
        if not provider or provider in existing_ids:
            continue
        options.append({"id": provider, "label": provider, "color": palette[i % len(palette)]})
    return options


def _domain_filter(domain: str) -> list[str]:
    """도메인 문자열을 도메인 ID 리스트로 변환한다. 그룹 ID이면 하위 도메인을 모두 포함."""
    normalized = (domain or "all").strip() or "all"
    if normalized == "all":
        return []
    catalog = fetch_domain_catalog()
    domain_ids = {str(item["id"]) for item in catalog}
    if normalized in domain_ids:
        return [normalized]
    group_domains = [
        str(item["id"])
        for item in catalog
        if str(item.get("group_id") or item.get("groupId") or "") == normalized
    ]
    return group_domains or [normalized]


# ── 시간 범위 계산 ─────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _range_bounds(range_id: str) -> tuple[RangeSpec, datetime, datetime, datetime]:
    spec = RANGES[range_id]
    end_at = _now_utc()
    start_at = end_at - spec.duration
    prev_start_at = start_at - spec.duration
    return spec, start_at, end_at, prev_start_at


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
        max_window = timedelta(days=settings.api_max_query_window_days)
        if duration > max_window:
            raise ValueError(
                f"Query window must be {settings.api_max_query_window_days} days or less "
                f"(got {duration.days}d {duration.seconds // 3600}h)."
            )
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


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

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
