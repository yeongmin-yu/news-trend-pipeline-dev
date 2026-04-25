from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    bucket_min: int = Field(serialization_alias="bucketMin")
    buckets: int


class FiltersResponse(BaseModel):
    domains: list[DomainOption]
    sources: list[SourceOption]
    ranges: list[RangeOption]


class KeywordSummary(BaseModel):
    keyword: str
    mentions: int
    prev_mentions: int = Field(serialization_alias="prevMentions")
    growth: float
    delta: int
    spike: bool
    event_score: int = Field(serialization_alias="eventScore")
    article_count: int = Field(serialization_alias="articleCount")
    source_share_naver: float = Field(serialization_alias="sourceShareNaver")
    source_share_global: float = Field(serialization_alias="sourceShareGlobal")


class KpiSummary(BaseModel):
    total_articles: int = Field(serialization_alias="totalArticles")
    unique_keywords: int = Field(serialization_alias="uniqueKeywords")
    spike_count: int = Field(serialization_alias="spikeCount")
    growth: float
    last_update_relative: str = Field(serialization_alias="lastUpdateRelative")
    last_update_absolute: str = Field(serialization_alias="lastUpdateAbsolute")


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
    published_at: datetime | None = Field(serialization_alias="publishedAt")
    minutes_ago: int | None = Field(serialization_alias="minutesAgo")
    keywords: list[str]
    primary_keyword: str | None = Field(serialization_alias="primaryKeyword")
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
    created_at: datetime = Field(serialization_alias="createdAt")


class CompoundCandidateItem(BaseModel):
    id: int
    word: str
    domain: str = "all"
    frequency: int
    doc_count: int = Field(serialization_alias="docCount")
    first_seen_at: datetime = Field(serialization_alias="firstSeenAt")
    last_seen_at: datetime = Field(serialization_alias="lastSeenAt")
    status: str
    reviewed_at: datetime | None = Field(serialization_alias="reviewedAt")
    reviewed_by: str | None = Field(serialization_alias="reviewedBy")


class StopwordItem(BaseModel):
    id: int
    word: str
    domain: str = "all"
    language: str
    created_at: datetime = Field(serialization_alias="createdAt")


class StopwordCandidateItem(BaseModel):
    id: int
    word: str
    domain: str = "all"
    language: str = "ko"
    score: float
    domain_breadth: float = Field(serialization_alias="domainBreadth")
    repetition_rate: float = Field(serialization_alias="repetitionRate")
    trend_stability: float = Field(serialization_alias="trendStability")
    cooccurrence_breadth: float = Field(serialization_alias="cooccurrenceBreadth")
    short_word: bool = Field(serialization_alias="shortWord")
    frequency: int
    status: str
    first_seen_at: datetime = Field(serialization_alias="firstSeenAt")
    last_seen_at: datetime = Field(serialization_alias="lastSeenAt")
    reviewed_at: datetime | None = Field(serialization_alias="reviewedAt")
    reviewed_by: str | None = Field(serialization_alias="reviewedBy")


class DictionaryVersions(BaseModel):
    compound_noun_dict: int = Field(serialization_alias="compoundNounDict")
    stopword_dict: int = Field(serialization_alias="stopwordDict")


class DictionaryOverviewResponse(BaseModel):
    compound_nouns: list[CompoundNounItem] = Field(serialization_alias="compoundNouns")
    compound_candidates: list[CompoundCandidateItem] = Field(serialization_alias="compoundCandidates")
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
    reviewed_by: str = Field(default="admin", alias="reviewedBy")


class UpsertQueryKeywordRequest(BaseModel):
    domain_id: str = Field(alias="domainId")
    query: str
    sort_order: int = Field(default=1, alias="sortOrder")
    is_active: bool = Field(default=True, alias="isActive")
    actor: str = "dashboard-admin"

