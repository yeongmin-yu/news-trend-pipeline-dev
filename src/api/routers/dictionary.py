from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    ReviewCandidateRequest,
    UpdateDomainRequest,
    UpsertCompoundNounRequest,
    UpsertStopwordRequest,
)
from api.service import (
    DictionaryDomainConflictError,
    DictionaryItemNotFoundError,
    approve_stopword_candidate,
    create_compound_noun,
    create_stopword,
    delete_compound_noun,
    delete_stopword,
    get_dictionary_overview,
    list_compound_nouns_paged,
    list_stopword_candidates_paged,
    list_stopwords_paged,
    list_candidates_paged,
    reject_stopword_candidate,
    review_compound_candidate,
    update_compound_noun_domain,
    update_stopword_domain,
)

router = APIRouter(prefix="/api/v1/dictionary")


# ── 개요 ─────────────────────────────────────────────────────────────────────

@router.get("")
def dictionary_overview() -> dict:
    """사전 전체 개요 반환 — 복합명사·불용어·후보 항목 전체를 한 번에 조회한다."""
    return get_dictionary_overview()


@router.get("/history")
def dictionary_history(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    """사전 변경 이력 반환 — 복합명사·불용어의 추가·삭제·도메인 수정 감사 로그를 최신순으로 제공한다."""
    from storage.db import fetch_dictionary_audit_logs
    return {"items": fetch_dictionary_audit_logs(limit=limit)}


# ── 복합명사 ──────────────────────────────────────────────────────────────────

@router.get("/compound-nouns")
def dict_list_compound_nouns(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    """복합명사 목록 페이지네이션 조회 — 키워드 분석에 사용할 복합명사 사전을 검색·필터링해 반환한다."""
    return list_compound_nouns_paged(page=page, limit=limit, q=q, domain=domain)


@router.post("/compound-nouns", status_code=201)
def dictionary_create_compound_noun(payload: UpsertCompoundNounRequest) -> dict[str, str]:
    """복합명사 등록 — 새 복합명사를 사전에 추가하고 형태소 분석에 즉시 반영한다."""
    create_compound_noun(
        word=payload.word.strip(),
        source=payload.source.strip() or "manual",
        actor=payload.actor.strip() or "dashboard-admin",
        domain=payload.domain.strip() or "all",
    )
    return {"status": "ok"}


@router.patch("/compound-nouns/{item_id}/domain")
def dictionary_update_compound_noun_domain(item_id: int, payload: UpdateDomainRequest) -> dict[str, str]:
    """복합명사 도메인 수정 — 기존 복합명사 항목의 적용 도메인을 변경한다."""
    try:
        update_compound_noun_domain(item_id, domain=payload.domain.strip() or "all", actor=payload.actor.strip() or "dashboard-admin")
    except DictionaryItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DictionaryDomainConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok"}


@router.delete("/compound-nouns/{item_id}")
def dictionary_delete_compound_noun(item_id: int) -> dict[str, str]:
    """복합명사 삭제 — 사전에서 해당 복합명사를 제거한다."""
    delete_compound_noun(item_id)
    return {"status": "ok"}


# ── 복합명사 후보 ──────────────────────────────────────────────────────────────

@router.get("/candidates")
def dict_list_candidates(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    status: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    """복합명사 후보 목록 조회 — 자동 추출된 복합명사 후보를 상태(pending/approved/rejected)별로 필터링해 반환한다."""
    return list_candidates_paged(page=page, limit=limit, q=q, status=status, domain=domain)


@router.post("/compound-candidates/{candidate_id}/approve")
def dictionary_approve_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    """복합명사 후보 승인 — 후보 항목을 승인하여 복합명사 사전에 등록한다."""
    review_compound_candidate(candidate_id, "approved", payload.reviewed_by)
    return {"status": "ok"}


@router.post("/compound-candidates/{candidate_id}/reject")
def dictionary_reject_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    """복합명사 후보 반려 — 후보 항목을 반려 처리하여 사전 등록을 차단한다."""
    review_compound_candidate(candidate_id, "rejected", payload.reviewed_by)
    return {"status": "ok"}


# ── 불용어 ────────────────────────────────────────────────────────────────────

@router.get("/stopwords")
def dict_list_stopwords(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    """불용어 목록 페이지네이션 조회 — 키워드 추출에서 제외할 불용어 사전을 검색·필터링해 반환한다."""
    return list_stopwords_paged(page=page, limit=limit, q=q, domain=domain)


@router.post("/stopwords", status_code=201)
def dictionary_create_stopword(payload: UpsertStopwordRequest) -> dict[str, object]:
    """불용어 등록 — 새 불용어를 사전에 추가하고 기존 키워드 데이터에서 해당 단어를 정리한다."""
    cleanup = create_stopword(
        word=payload.word.strip(),
        language=payload.language.strip() or "ko",
        actor=payload.actor.strip() or "dashboard-admin",
        domain=payload.domain.strip() or "all",
    )
    return {"status": "ok", "cleanup": cleanup}


@router.patch("/stopwords/{item_id}/domain")
def dictionary_update_stopword_domain(item_id: int, payload: UpdateDomainRequest) -> dict[str, str]:
    """불용어 도메인 수정 — 기존 불용어 항목의 적용 도메인을 변경한다."""
    try:
        update_stopword_domain(item_id, domain=payload.domain.strip() or "all", actor=payload.actor.strip() or "dashboard-admin")
    except DictionaryItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DictionaryDomainConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok"}


@router.delete("/stopwords/{item_id}")
def dictionary_delete_stopword(item_id: int) -> dict[str, str]:
    """불용어 삭제 — 사전에서 해당 불용어를 제거한다."""
    delete_stopword(item_id)
    return {"status": "ok"}


# ── 불용어 후보 ───────────────────────────────────────────────────────────────

@router.get("/stopword-candidates")
def dict_list_stopword_candidates(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    status: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    """불용어 후보 목록 조회 — 스코어링 모델이 추천한 불용어 후보를 상태별로 필터링해 반환한다."""
    return list_stopword_candidates_paged(page=page, limit=limit, q=q, status=status, domain=domain)


@router.post("/stopword-candidates/{candidate_id}/approve")
def dictionary_approve_stopword_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    """불용어 후보 승인 — 후보 항목을 승인하여 불용어 사전에 등록하고 기존 데이터에서 정리한다."""
    approve_stopword_candidate(candidate_id, payload.reviewed_by)
    return {"status": "ok"}


@router.post("/stopword-candidates/{candidate_id}/reject")
def dictionary_reject_stopword_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    """불용어 후보 반려 — 후보 항목을 반려 처리하여 불용어 사전 등록을 차단한다."""
    reject_stopword_candidate(candidate_id, payload.reviewed_by)
    return {"status": "ok"}
