from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    ReviewCandidateRequest,
    UpdateDomainRequest,
    UpsertCompoundNounRequest,
    UpsertQueryKeywordRequest,
    UpsertStopwordRequest,
)
from api.service import (
    approve_stopword_candidate,
    create_query_keyword,
    create_compound_noun,
    create_stopword,
    delete_query_keyword,
    delete_compound_noun,
    delete_stopword,
    get_articles,
    get_dashboard_overview,
    get_collection_metrics_overview,
    get_dictionary_overview,
    list_compound_nouns_paged,
    list_stopword_candidates_paged,
    list_stopwords_paged,
    list_candidates_paged,
    get_filters,
    get_kpis,
    get_query_keyword_admin_overview,
    get_related_keywords,
    get_spike_events,
    get_system_status,
    get_theme_distribution,
    get_top_keywords,
    get_trend_series,
    get_trend_window_series,
    reject_stopword_candidate,
    review_compound_candidate,
    trigger_compound_auto_approve,
    trigger_stopword_recommender,
    update_compound_noun_domain,
    update_stopword_domain,
    update_query_keyword,
)
from storage.db import safe_initialize_database


app = FastAPI(title="News Trend Pipeline API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    safe_initialize_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/meta/filters")
def filters() -> dict:
    return get_filters()


@app.get("/api/v1/dashboard/kpis")
def dashboard_kpis(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> dict:
    return get_kpis(source=source, domain=domain, range_id=range_id, start_at=start_at, end_at=end_at)


@app.get("/api/v1/dashboard/keywords")
def dashboard_keywords(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=30, ge=1, le=100),
    search: str | None = Query(default=None),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> list[dict]:
    return get_top_keywords(
        source=source,
        domain=domain,
        range_id=range_id,
        limit=limit,
        search=search,
        start_at=start_at,
        end_at=end_at,
    )


@app.get("/api/v1/dashboard/overview-window")
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


@app.get("/api/v1/dashboard/trend")
def dashboard_trend(
    keyword: str | None = Query(default=None),
    keywords: str | None = Query(default=None),
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    compare_limit: int = Query(default=4, ge=1, le=5, alias="compareLimit"),
) -> dict:
    selected_keywords = [item.strip() for item in (keywords or "").split(",") if item.strip()]
    return get_trend_series(
        source=source,
        domain=domain,
        range_id=range_id,
        keyword=keyword,
        keywords=selected_keywords,
        compare_limit=compare_limit,
    )


@app.get("/api/v1/dashboard/trend-window")
def dashboard_trend_window(
    keywords: str,
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    start_at: datetime = Query(alias="startAt"),
    end_at: datetime = Query(alias="endAt"),
    bucket: str = Query(default="15m"),
) -> dict:
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


@app.get("/api/v1/dashboard/spikes")
def dashboard_spikes(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=32, ge=1, le=100),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
    bucket: str | None = Query(default=None),
) -> dict:
    return get_spike_events(
        source=source,
        domain=domain,
        range_id=range_id,
        limit=limit,
        start_at=start_at,
        end_at=end_at,
        bucket_id=bucket,
    )


@app.get("/api/v1/dashboard/related")
def dashboard_related(
    keyword: str,
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=10, ge=1, le=50),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> list[dict]:
    return get_related_keywords(
        source=source,
        domain=domain,
        range_id=range_id,
        keyword=keyword,
        limit=limit,
        start_at=start_at,
        end_at=end_at,
    )


@app.get("/api/v1/dashboard/theme-distribution")
def dashboard_theme_distribution(
    keyword: str,
    source: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
) -> dict:
    return get_theme_distribution(source=source, range_id=range_id, keyword=keyword, start_at=start_at, end_at=end_at)


@app.get("/api/v1/dashboard/articles")
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


@app.get("/api/v1/dashboard/system")
def dashboard_system() -> dict:
    return get_system_status()


@app.get("/api/v1/dictionary")
def dictionary_overview() -> dict:
    return get_dictionary_overview()


@app.get("/api/v1/dictionary/history")
def dictionary_history(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    from storage.db import fetch_dictionary_audit_logs
    return {"items": fetch_dictionary_audit_logs(limit=limit)}


@app.get("/api/v1/dictionary/compound-nouns")
def dict_list_compound_nouns(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    return list_compound_nouns_paged(page=page, limit=limit, q=q, domain=domain)


@app.get("/api/v1/dictionary/stopwords")
def dict_list_stopwords(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    return list_stopwords_paged(page=page, limit=limit, q=q, domain=domain)


@app.get("/api/v1/dictionary/candidates")
def dict_list_candidates(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    status: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    return list_candidates_paged(page=page, limit=limit, q=q, status=status, domain=domain)


@app.post("/api/v1/dictionary/compound-nouns", status_code=201)
def dictionary_create_compound_noun(payload: UpsertCompoundNounRequest) -> dict[str, str]:
    create_compound_noun(
        word=payload.word.strip(),
        source=payload.source.strip() or "manual",
        actor=payload.actor.strip() or "dashboard-admin",
        domain=payload.domain.strip() or "all",
    )
    return {"status": "ok"}


@app.patch("/api/v1/dictionary/compound-nouns/{item_id}/domain")
def dictionary_update_compound_noun_domain(item_id: int, payload: UpdateDomainRequest) -> dict[str, str]:
    update_compound_noun_domain(item_id, domain=payload.domain.strip() or "all", actor=payload.actor.strip() or "dashboard-admin")
    return {"status": "ok"}


@app.delete("/api/v1/dictionary/compound-nouns/{item_id}")
def dictionary_delete_compound_noun(item_id: int) -> dict[str, str]:
    delete_compound_noun(item_id)
    return {"status": "ok"}

@app.post("/api/v1/dictionary/compound-candidates/{candidate_id}/approve")
def dictionary_approve_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    review_compound_candidate(candidate_id, "approved", payload.reviewed_by)
    return {"status": "ok"}

@app.post("/api/v1/dictionary/compound-candidates/{candidate_id}/reject")
def dictionary_reject_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    review_compound_candidate(candidate_id, "rejected", payload.reviewed_by)
    return {"status": "ok"}


@app.post("/api/v1/dictionary/stopwords", status_code=201)
def dictionary_create_stopword(payload: UpsertStopwordRequest) -> dict[str, str]:
    create_stopword(
        word=payload.word.strip(),
        language=payload.language.strip() or "ko",
        actor=payload.actor.strip() or "dashboard-admin",
        domain=payload.domain.strip() or "all",
    )
    return {"status": "ok"}


@app.patch("/api/v1/dictionary/stopwords/{item_id}/domain")
def dictionary_update_stopword_domain(item_id: int, payload: UpdateDomainRequest) -> dict[str, str]:
    update_stopword_domain(item_id, domain=payload.domain.strip() or "all", actor=payload.actor.strip() or "dashboard-admin")
    return {"status": "ok"}


@app.delete("/api/v1/dictionary/stopwords/{item_id}")
def dictionary_delete_stopword(item_id: int) -> dict[str, str]:
    delete_stopword(item_id)
    return {"status": "ok"}


@app.get("/api/v1/dictionary/stopword-candidates")
def dict_list_stopword_candidates(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str = Query(default=""),
    status: str = Query(default=""),
    domain: str = Query(default=""),
) -> dict:
    return list_stopword_candidates_paged(page=page, limit=limit, q=q, status=status, domain=domain)


@app.post("/api/v1/dictionary/stopword-candidates/{candidate_id}/approve")
def dictionary_approve_stopword_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    approve_stopword_candidate(candidate_id, payload.reviewed_by)
    return {"status": "ok"}


@app.post("/api/v1/dictionary/stopword-candidates/{candidate_id}/reject")
def dictionary_reject_stopword_candidate(candidate_id: int, payload: ReviewCandidateRequest) -> dict[str, str]:
    reject_stopword_candidate(candidate_id, payload.reviewed_by)
    return {"status": "ok"}


@app.post("/api/v1/admin/run-compound-auto-approve")
def admin_run_compound_auto_approve() -> dict:
    return trigger_compound_auto_approve()


@app.post("/api/v1/admin/run-stopword-recommender")
def admin_run_stopword_recommender() -> dict:
    return trigger_stopword_recommender()


@app.get("/api/v1/admin/query-keywords")
def admin_query_keywords() -> dict:
    return get_query_keyword_admin_overview()


@app.get("/api/v1/admin/collection-metrics")
def admin_collection_metrics(hours: int = Query(default=24, ge=1, le=168)) -> dict:
    return get_collection_metrics_overview(hours=hours)


@app.post("/api/v1/admin/query-keywords", status_code=201)
def admin_create_query_keyword(payload: UpsertQueryKeywordRequest) -> dict:
    return create_query_keyword(
        domain_id=payload.domain_id,
        query=payload.query.strip(),
        sort_order=payload.sort_order,
        actor=payload.actor.strip() or "dashboard-admin",
    )


@app.patch("/api/v1/admin/query-keywords/{item_id}")
def admin_update_query_keyword(item_id: int, payload: UpsertQueryKeywordRequest) -> dict:
    return update_query_keyword(
        item_id=item_id,
        domain_id=payload.domain_id,
        query=payload.query.strip(),
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        actor=payload.actor.strip() or "dashboard-admin",
    )


@app.delete("/api/v1/admin/query-keywords/{item_id}")
def admin_delete_query_keyword(item_id: int, actor: str = Query(default="dashboard-admin")) -> dict[str, str]:
    delete_query_keyword(item_id, actor=actor)
    return {"status": "ok"}
