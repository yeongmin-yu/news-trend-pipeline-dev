from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


SourceId = Literal["all", "naver", "global"]
RangeId = Literal["10m", "30m", "1h", "6h", "12h", "1d"]


class DomainOption(BaseModel):
    id: str
    label: str
    available: bool = True


class SourceOption(BaseModel):
    id: SourceId
    label: str
    color: str


class RangeOption(BaseModel):
    id: RangeId
    label: str
    bucket_min: int
    buckets: int


class FiltersResponse(BaseModel):
    domains: list[DomainOption]
    sources: list[SourceOption]
    ranges: list[RangeOption]


class KeywordSummary(BaseModel):
    keyword: str
    mentions: int
    prev_mentions: int
    growth: float
    delta: int
    spike: bool
    event_score: int
    article_count: int
    source_share_naver: float
    source_share_global: float


class KpiSummary(BaseModel):
    total_articles: int
    unique_keywords: int
    spike_count: int
    growth: float
    last_update_relative: str
    last_update_absolute: str


class SeriesPoint(BaseModel):
    bucket: int
    timestamp: datetime
    value: int


class TrendSeries(BaseModel):
    name: str
    color: str
    spike: bool
    points: list[SeriesPoint]


class SpikeEvent(BaseModel):
    bucket: int
    keyword: str
    intensity: float
    source: Literal["naver", "global"]
    growth: float
    score: int


class RelatedKeyword(BaseModel):
    keyword: str
    weight: float


class ArticleItem(BaseModel):
    id: str
    title: str
    summary: str
    publisher: str
    source: str
    published_at: datetime | None
    minutes_ago: int | None
    keywords: list[str]
    primary_keyword: str | None
    duplicates: int = 0
    url: str


class ServiceStatus(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "down", "unknown"]
    detail: str


class SystemStatusResponse(BaseModel):
    services: list[ServiceStatus]


class CompoundNounItem(BaseModel):
    id: int
    word: str
    domain: str = "all"
    source: str
    created_at: datetime


class CompoundCandidateItem(BaseModel):
    id: int
    word: str
    domain: str = "all"
    frequency: int
    doc_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    status: str
    reviewed_at: datetime | None
    reviewed_by: str | None


class StopwordItem(BaseModel):
    id: int
    word: str
    domain: str = "all"
    language: str
    created_at: datetime


class StopwordCandidateItem(BaseModel):
    id: int
    word: str
    domain: str = "all"
    language: str = "ko"
    score: float
    domain_breadth: float
    repetition_rate: float
    trend_stability: float
    cooccurrence_breadth: float
    short_word: bool
    frequency: int
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    reviewed_at: datetime | None
    reviewed_by: str | None


class DictionaryVersions(BaseModel):
    compound_noun_dict: int
    stopword_dict: int


class DictionaryOverviewResponse(BaseModel):
    compound_nouns: list[CompoundNounItem]
    compound_candidates: list[CompoundCandidateItem]
    stopwords: list[StopwordItem]
    versions: DictionaryVersions


class UpsertCompoundNounRequest(BaseModel):
    word: str
    domain: str = "all"
    source: str = "manual"
    actor: str = "dashboard-admin"


class UpdateDomainRequest(BaseModel):
    domain: str
    actor: str = "dashboard-admin"


class UpsertStopwordRequest(BaseModel):
    word: str
    domain: str = "all"
    language: str = "ko"
    actor: str = "dashboard-admin"


class ReviewCandidateRequest(BaseModel):
    reviewed_by: str = "admin"


class UpsertQueryKeywordRequest(BaseModel):
    domain_id: str
    query: str
    sort_order: int = 1
    is_active: bool = True
    actor: str = "dashboard-admin"
