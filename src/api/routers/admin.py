from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas import UpsertQueryKeywordRequest, CompoundBackfillRequest
from api.service import (
    AirflowTriggerError,
    create_query_keyword,
    delete_query_keyword,
    get_collection_metrics_overview,
    get_query_keyword_admin_overview,
    trigger_compound_auto_approve,
    trigger_compound_keyword_backfill_dag,
    trigger_stopword_recommender,
    update_query_keyword,
)

router = APIRouter(prefix="/api/v1/admin")


# ── 자동 처리 트리거 ──────────────────────────────────────────────────────────

@router.post("/run-compound-auto-approve")
def admin_run_compound_auto_approve() -> dict:
    """복합명사 후보 자동 승인 실행 — 승인 기준을 통과한 후보를 일괄 승인하여 사전에 등록한다."""
    return trigger_compound_auto_approve()


@router.post("/run-stopword-recommender")
def admin_run_stopword_recommender() -> dict:
    """불용어 추천 DAG 실행 — 최신 키워드 데이터를 분석하여 불용어 후보를 새로 생성한다."""
    return trigger_stopword_recommender()


@router.post("/compound-keyword-backfill", status_code=202)
def admin_trigger_compound_keyword_backfill(payload: CompoundBackfillRequest) -> dict:
    """복합명사 키워드 백필 DAG 트리거 — 특정 복합명사에 대해 과거 기간의 키워드 집계를 재처리한다."""
    try:
        return trigger_compound_keyword_backfill_dag(
            word=payload.word,
            domain=payload.domain,
            since=payload.since,
            until=payload.until,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AirflowTriggerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── 쿼리 키워드 관리 ──────────────────────────────────────────────────────────

@router.get("/query-keywords")
def admin_query_keywords() -> dict:
    """쿼리 키워드 관리 목록 반환 — 도메인별 뉴스 수집에 사용되는 검색 쿼리 키워드 전체 현황을 제공한다."""
    return get_query_keyword_admin_overview()


@router.post("/query-keywords", status_code=201)
def admin_create_query_keyword(payload: UpsertQueryKeywordRequest) -> dict:
    """쿼리 키워드 등록 — 특정 도메인에 새 뉴스 수집용 검색 키워드를 추가한다."""
    return create_query_keyword(
        domain_id=payload.domain_id,
        query=payload.query.strip(),
        sort_order=payload.sort_order,
        actor=payload.actor.strip() or "dashboard-admin",
    )


@router.patch("/query-keywords/{item_id}")
def admin_update_query_keyword(item_id: int, payload: UpsertQueryKeywordRequest) -> dict:
    """쿼리 키워드 수정 — 기존 쿼리 키워드의 내용·도메인·정렬 순서·활성화 여부를 변경한다."""
    return update_query_keyword(
        item_id=item_id,
        domain_id=payload.domain_id,
        query=payload.query.strip(),
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        actor=payload.actor.strip() or "dashboard-admin",
    )


@router.delete("/query-keywords/{item_id}")
def admin_delete_query_keyword(item_id: int, actor: str = Query(default="dashboard-admin")) -> dict[str, str]:
    """쿼리 키워드 삭제 — 뉴스 수집 대상에서 해당 검색 키워드를 제거한다."""
    delete_query_keyword(item_id, actor=actor)
    return {"status": "ok"}


# ── 수집 메트릭 ───────────────────────────────────────────────────────────────

@router.get("/collection-metrics")
def admin_collection_metrics(hours: int = Query(default=24, ge=1, le=168)) -> dict:
    """뉴스 수집 메트릭 반환 — 최근 N시간 동안의 소스별 기사 수집량·중복률·지연 현황을 제공한다."""
    return get_collection_metrics_overview(hours=hours)
