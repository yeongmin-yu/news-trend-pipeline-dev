from __future__ import annotations

from fastapi import APIRouter

from api.service import get_filters

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """서비스 헬스체크 — 서버가 정상 동작 중인지 확인한다."""
    return {"status": "ok"}


@router.get("/api/v1/meta/filters")
def filters() -> dict:
    """대시보드 필터 메타데이터 반환 — 도메인·소스·범위(range) 선택지를 제공한다."""
    return get_filters()
