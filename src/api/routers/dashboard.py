from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from api.service import (
    get_articles,
    get_dashboard_overview,
    get_kpis,
    get_related_keywords,
    get_spike_events,
    get_system_status,
    get_theme_distribution,
    get_top_keywords,
    get_trend_series,
    get_trend_window_series,
)

router = APIRouter(prefix="/api/v1/dashboard")


@router.get("/kpis")
def dashboard_kpis(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> dict:
    """대시보드 KPI 요약 반환 — 기간 내 총 기사 수·고유 키워드 수·급상승 수·성장률 등을 제공한다."""
    return get_kpis(source=source, domain=domain, range_id=range_id, start_at=start_at, end_at=end_at)


@router.get("/keywords")
def dashboard_keywords(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=30, ge=1, le=100),
    search: str | None = Query(default=None),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> list[dict]:
    """상위 키워드 목록 반환 — 언급 횟수·성장률·스파이크 여부 등으로 정렬된 키워드 리스트를 제공한다."""
    return get_top_keywords(
        source=source,
        domain=domain,
        range_id=range_id,
        limit=limit,
        search=search,
        start_at=start_at,
        end_at=end_at,
    )


@router.get("/overview-window")
def dashboard_overview_window(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    start_at: datetime = Query(alias="startAt"),
    end_at: datetime = Query(alias="endAt"),
    fetch_start_at: datetime | None = Query(default=None, alias="fetchStartAt"),
    fetch_end_at: datetime | None = Query(default=None, alias="fetchEndAt"),
    bucket: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict:
    """윈도우 기반 대시보드 개요 반환 — 지정한 시간 범위의 키워드 트렌드·스파이크·기사 목록을 한 번에 조회한다."""
    return get_dashboard_overview(
        source=source,
        domain=domain,
        range_id=range_id,
        start_at=start_at,
        end_at=end_at,
        fetch_start_at=fetch_start_at,
        fetch_end_at=fetch_end_at,
        bucket_id=bucket,
        search=search,
        limit=limit,
    )


@router.get("/trend")
def dashboard_trend(
    keyword: str | None = Query(default=None),
    keywords: str | None = Query(default=None),
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    compare_limit: int = Query(default=4, ge=1, le=5, alias="compareLimit"),
) -> dict:
    """키워드 트렌드 시계열 반환 — 단일 키워드 또는 비교 키워드(최대 5개)의 시간대별 언급 추이를 제공한다."""
    selected_keywords = [item.strip() for item in (keywords or "").split(",") if item.strip()]
    return get_trend_series(
        source=source,
        domain=domain,
        range_id=range_id,
        keyword=keyword,
        keywords=selected_keywords,
        compare_limit=compare_limit,
    )


@router.get("/trend-window")
def dashboard_trend_window(
    keywords: str,
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    start_at: datetime = Query(alias="startAt"),
    end_at: datetime = Query(alias="endAt"),
    bucket: str = Query(default="15m"),
) -> dict:
    """커스텀 기간 키워드 트렌드 시계열 반환 — startAt~endAt 범위와 bucket 단위로 시계열 데이터를 조회한다."""
    selected_keywords = [item.strip() for item in keywords.split(",") if item.strip()]
    try:
        return get_trend_window_series(
            source=source,
            domain=domain,
            start_at=start_at,
            end_at=end_at,
            bucket_id=bucket,
            keywords=selected_keywords,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/spikes")
def dashboard_spikes(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=32, ge=1, le=100),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
    bucket: str | None = Query(default=None),
) -> dict:
    """스파이크 이벤트 목록 반환 — 급격히 언급량이 증가한 키워드 이벤트를 강도·점수 순으로 제공한다."""
    return get_spike_events(
        source=source,
        domain=domain,
        range_id=range_id,
        limit=limit,
        start_at=start_at,
        end_at=end_at,
        bucket_id=bucket,
    )


@router.get("/related")
def dashboard_related(
    keyword: str,
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=10, ge=1, le=50),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> list[dict]:
    """연관 키워드 목록 반환 — 특정 키워드와 함께 자주 등장하는 연관 키워드를 가중치 순으로 제공한다."""
    return get_related_keywords(
        source=source,
        domain=domain,
        range_id=range_id,
        keyword=keyword,
        limit=limit,
        start_at=start_at,
        end_at=end_at,
    )


@router.get("/theme-distribution")
def dashboard_theme_distribution(
    keyword: str,
    source: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> dict:
    """테마 분포 반환 — 특정 키워드가 어떤 테마(도메인 그룹) 비율로 등장하는지 분석 결과를 제공한다."""
    return get_theme_distribution(source=source, range_id=range_id, keyword=keyword, start_at=start_at, end_at=end_at)


@router.get("/articles")
def dashboard_articles(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    sort: str = Query(default="latest"),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> list[dict]:
    """기사 목록 반환 — 필터 조건에 맞는 뉴스 기사를 최신순 또는 관련도 순으로 제공한다."""
    return get_articles(
        source=source,
        domain=domain,
        range_id=range_id,
        keyword=keyword,
        limit=limit,
        sort=sort,
        start_at=start_at,
        end_at=end_at,
    )


@router.get("/system")
def dashboard_system() -> dict:
    """시스템 상태 반환 — 수집기·분석기·DB 등 각 서비스 컴포넌트의 헬스 상태를 제공한다."""
    return get_system_status()
