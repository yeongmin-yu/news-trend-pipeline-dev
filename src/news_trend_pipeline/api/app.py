from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from news_trend_pipeline.api.schemas import ReviewCandidateRequest, UpsertCompoundNounRequest, UpsertStopwordRequest
from news_trend_pipeline.api.service import (
    create_compound_noun,
    create_stopword,
    delete_compound_noun,
    delete_stopword,
    get_articles,
    get_dictionary_overview,
    get_filters,
    get_kpis,
    get_related_keywords,
    get_spike_events,
    get_system_status,
    get_top_keywords,
    get_trend_series,
    review_compound_candidate,
)
from news_trend_pipeline.storage.db import safe_initialize_database


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
) -> dict:
    return get_kpis(source=source, domain=domain, range_id=range_id)


@app.get("/api/v1/dashboard/keywords")
def dashboard_keywords(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=30, ge=1, le=100),
    search: str | None = Query(default=None),
) -> list[dict]:
    return get_top_keywords(source=source, domain=domain, range_id=range_id, limit=limit, search=search)


@app.get("/api/v1/dashboard/trend")
def dashboard_trend(
    keyword: str,
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    compare_limit: int = Query(default=4, ge=1, le=5, alias="compareLimit"),
) -> dict:
    return get_trend_series(source=source, domain=domain, range_id=range_id, keyword=keyword, compare_limit=compare_limit)


@app.get("/api/v1/dashboard/spikes")
def dashboard_spikes(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=32, ge=1, le=100),
) -> dict:
    return get_spike_events(source=source, domain=domain, range_id=range_id, limit=limit)


@app.get("/api/v1/dashboard/related")
def dashboard_related(
    keyword: str,
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    return get_related_keywords(source=source, domain=domain, range_id=range_id, keyword=keyword, limit=limit)


@app.get("/api/v1/dashboard/articles")
def dashboard_articles(
    source: str = Query(default="all"),
    domain: str = Query(default="all"),
    range_id: str = Query(default="1h", alias="range"),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    sort: str = Query(default="latest"),
) -> list[dict]:
    return get_articles(source=source, domain=domain, range_id=range_id, keyword=keyword, limit=limit, sort=sort)


@app.get("/api/v1/dashboard/system")
def dashboard_system() -> dict:
    return get_system_status()


@app.get("/api/v1/dictionary")
def dictionary_overview() -> dict:
    return get_dictionary_overview()


@app.post("/api/v1/dictionary/compound-nouns", status_code=201)
def dictionary_create_compound_noun(payload: UpsertCompoundNounRequest) -> dict[str, str]:
    create_compound_noun(word=payload.word.strip(), source=payload.source.strip() or "manual")
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
    create_stopword(word=payload.word.strip(), language=payload.language.strip() or "ko")
    return {"status": "ok"}


@app.delete("/api/v1/dictionary/stopwords/{item_id}")
def dictionary_delete_stopword(item_id: int) -> dict[str, str]:
    delete_stopword(item_id)
    return {"status": "ok"}
