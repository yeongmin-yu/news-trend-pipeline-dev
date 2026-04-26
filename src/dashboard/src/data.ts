export type SourceId = "all" | "naver" | "global";
export type RangeId = "10m" | "30m" | "1h" | "6h" | "12h" | "1d";
export type TrendBucketId = "5m" | "15m" | "30m" | "1h" | "4h" | "1d";

export interface DomainOption {
  id: string;
  label: string;
  available: boolean;
}

export interface SourceOption {
  id: SourceId;
  label: string;
  color: string;
}

export interface RangeOption {
  id: RangeId;
  label: string;
  bucket_min: number;
  buckets: number;
}

export interface FiltersResponse {
  domains: DomainOption[];
  sources: SourceOption[];
  ranges: RangeOption[];
}

export interface KeywordSummary {
  keyword: string;
  mentions: number;
  prev_mentions: number;
  growth: number;
  delta: number;
  spike: boolean;
  event_score: number;
  article_count: number;
  source_share_naver?: number;
  source_share_global?: number;
}

export interface KpiSummary {
  total_articles: number;
  unique_keywords: number;
  spike_count: number;
  growth: number;
  last_update_relative: string;
  last_update_absolute: string;
}

export interface SeriesPoint {
  bucket: number;
  timestamp: string;
  value: number;
}

export interface TrendSeries {
  name: string;
  color: string;
  spike: boolean;
  points: SeriesPoint[];
}

export interface TrendResponse {
  series: TrendSeries[];
  range: RangeOption | { id: string; label: string; bucket_min: number; buckets: number };
}

export interface SpikeEvent {
  bucket: number;
  keyword: string;
  intensity: number;
  source: "naver" | "global";
  current_mentions: number;
  prev_mentions: number;
  growth: number;
  score: number;
}

export interface SpikeResponse {
  top_keywords?: string[];
  events: SpikeEvent[];
  range: RangeOption | { id: string; label: string; bucket_min: number; buckets: number };
}

export interface OverviewArticleBucket {
  bucket: number;
  timestamp: string;
  article_count: number;
  last_update_at: string | null;
}

export interface OverviewKeywordBucket {
  keyword: string;
  bucket: number;
  timestamp: string;
  mentions: number;
  article_count: number;
}

export interface OverviewCachePayload {
  requested_start_at: string;
  requested_end_at: string;
  fetch_start_at: string;
  fetch_end_at: string;
  data_start_at: string;
  data_end_at: string;
  bucket: TrendBucketId;
  bucket_min: number;
  buckets: number;
  candidate_keywords: string[];
  article_buckets: OverviewArticleBucket[];
  keyword_buckets: OverviewKeywordBucket[];
  range: RangeOption | { id: string; label: string; bucket_min: number; buckets: number };
}

export interface DashboardOverviewResponse {
  kpis: KpiSummary;
  keywords: KeywordSummary[];
  spikes: SpikeResponse;
  cache?: OverviewCachePayload;
}

export interface RelatedKeyword {
  keyword: string;
  weight: number;
}

export interface ThemeDistributionItem {
  id: string;
  label: string;
  mentions: number;
  share: number;
  color?: string;
}

export interface ThemeDistributionResponse {
  keyword: string;
  total_mentions: number;
  items: ThemeDistributionItem[];
}

export interface ArticleItem {
  id: string;
  title: string;
  summary: string;
  publisher: string;
  source: string;
  domain?: string;
  published_at: string | null;
  minutes_ago: number | null;
  keywords: string[];
  primary_keyword: string | null;
  duplicates: number;
  url: string;
}

export interface ServiceStatus {
  key: string;
  label: string;
  status: "ok" | "warn" | "down" | "unknown";
  detail: string;
  status_code?: number | null;
}

export interface SystemStatusResponse {
  services: ServiceStatus[];
}

export interface CompoundNounItem {
  id: number;
  word: string;
  domain: string;
  source: string;
  created_at: string;
}

export interface CompoundCandidateItem {
  id: number;
  word: string;
  domain: string;
  frequency: number;
  doc_count: number;
  first_seen_at: string;
  last_seen_at: string;
  status: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export interface StopwordItem {
  id: number;
  word: string;
  domain: string;
  language: string;
  created_at: string;
}

export interface StopwordCandidateItem {
  id: number;
  word: string;
  domain: string;
  language: string;
  score: number;
  domain_breadth: number;
  repetition_rate: number;
  trend_stability: number;
  cooccurrence_breadth: number;
  short_word: boolean;
  frequency: number;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export interface DictionaryMeta {
  compound_noun_count: number;
  candidate_count: number;
  stopword_count: number;
  versions: {
    compound_noun_dict: number;
    stopword_dict: number;
  };
}

export interface DictionaryPage<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

/** @deprecated 페이징 전환 전 호환용 — 신규 코드에서는 DictionaryMeta 사용 */
export interface DictionaryOverview extends DictionaryMeta {
  compound_nouns: CompoundNounItem[];
  compound_candidates: CompoundCandidateItem[];
  stopwords: StopwordItem[];
}

export interface QueryKeywordItem {
  id: number;
  provider: string;
  domain_id: string;
  domain_label: string;
  query: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface QueryKeywordAuditLog {
  id: number;
  query_keyword_id: number | null;
  action: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  actor: string;
  acted_at: string;
}

export interface CollectionMetricItem {
  provider: string;
  domain: string;
  query: string;
  request_count: number;
  success_count: number;
  article_count: number;
  duplicate_count: number;
  publish_count: number;
  error_count: number;
  last_seen_at: string;
}

export interface QueryKeywordAdminOverview {
  domains: DomainOption[];
  query_keywords: QueryKeywordItem[];
  audit_logs: QueryKeywordAuditLog[];
  collection_metrics: CollectionMetricItem[];
}

const API_BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  filters: () => request<FiltersResponse>("/meta/filters"),
  kpis: (source: SourceId, domain: string, range: RangeId, startAt?: string, endAt?: string) =>
    request<KpiSummary>(
      `/dashboard/kpis?source=${source}&domain=${domain}&range=${range}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
    ),
  keywords: (source: SourceId, domain: string, range: RangeId, search: string, limit: number, startAt?: string, endAt?: string) =>
    request<KeywordSummary[]>(
      `/dashboard/keywords?source=${source}&domain=${domain}&range=${range}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ""}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
    ),
  overviewWindow: (
    source: SourceId,
    domain: string,
    range: RangeId,
    startAt: string,
    endAt: string,
    bucket: TrendBucketId,
    search: string,
    limit: number,
    fetchStartAt?: string,
    fetchEndAt?: string,
  ) =>
    request<DashboardOverviewResponse>(
      `/dashboard/overview-window?source=${source}&domain=${domain}&range=${range}&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}&bucket=${bucket}&limit=${limit}${
        fetchStartAt && fetchEndAt
          ? `&fetchStartAt=${encodeURIComponent(fetchStartAt)}&fetchEndAt=${encodeURIComponent(fetchEndAt)}`
          : ""
      }${
        search ? `&search=${encodeURIComponent(search)}` : ""
      }`,
    ),
  trend: (source: SourceId, domain: string, range: RangeId, keyword: string, keywords?: string[]) =>
    request<TrendResponse>(
      `/dashboard/trend?source=${source}&domain=${domain}&range=${range}&keyword=${encodeURIComponent(keyword)}${
        keywords?.length ? `&keywords=${encodeURIComponent(keywords.join(","))}` : ""
      }`,
    ),
  trendWindow: (
    source: SourceId,
    domain: string,
    startAt: string,
    endAt: string,
    bucket: TrendBucketId,
    keywords: string[],
  ) =>
    request<TrendResponse>(
      `/dashboard/trend-window?source=${source}&domain=${domain}&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}&bucket=${bucket}&keywords=${encodeURIComponent(keywords.join(","))}`,
    ),
  spikes: (source: SourceId, domain: string, range: RangeId, startAt?: string, endAt?: string, bucket?: TrendBucketId) =>
    request<SpikeResponse>(
      `/dashboard/spikes?source=${source}&domain=${domain}&range=${range}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }${bucket ? `&bucket=${bucket}` : ""}`,
    ),
  related: (source: SourceId, domain: string, range: RangeId, keyword: string, startAt?: string, endAt?: string) =>
    request<RelatedKeyword[]>(
      `/dashboard/related?source=${source}&domain=${domain}&range=${range}&keyword=${encodeURIComponent(keyword)}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
    ),
  themeDistribution: (source: SourceId, range: RangeId, keyword: string, startAt?: string, endAt?: string) =>
    request<ThemeDistributionResponse>(
      `/dashboard/theme-distribution?source=${source}&range=${range}&keyword=${encodeURIComponent(keyword)}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
    ),
  articles: (source: SourceId, domain: string, range: RangeId, keyword: string, sort: "latest" | "relevance", startAt?: string, endAt?: string) =>
    request<ArticleItem[]>(
      `/dashboard/articles?source=${source}&domain=${domain}&range=${range}&keyword=${encodeURIComponent(keyword)}&sort=${sort}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
    ),
  system: () => request<SystemStatusResponse>("/dashboard/system"),
  dictionaryMeta: () => request<DictionaryMeta>("/dictionary"),
  dictionaryCompoundNouns: (page: number, limit: number, q: string, domain?: string) =>
    request<DictionaryPage<CompoundNounItem>>(
      `/dictionary/compound-nouns?page=${page}&limit=${limit}&q=${encodeURIComponent(q)}${domain && domain !== "all" ? `&domain=${encodeURIComponent(domain)}` : ""}`,
    ),
  dictionaryStopwords: (page: number, limit: number, q: string, domain?: string) =>
    request<DictionaryPage<StopwordItem>>(
      `/dictionary/stopwords?page=${page}&limit=${limit}&q=${encodeURIComponent(q)}${domain && domain !== "all" ? `&domain=${encodeURIComponent(domain)}` : ""}`,
    ),
  dictionaryCandidates: (page: number, limit: number, q: string, status: string, domain?: string) =>
    request<DictionaryPage<CompoundCandidateItem>>(
      `/dictionary/candidates?page=${page}&limit=${limit}&q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}${domain && domain !== "all" ? `&domain=${encodeURIComponent(domain)}` : ""}`,
    ),
  /** @deprecated */
  dictionary: () => request<DictionaryOverview>("/dictionary"),
  queryKeywordAdmin: () => request<QueryKeywordAdminOverview>("/admin/query-keywords"),
  createCompound: (word: string, domain = "all") =>
    request("/dictionary/compound-nouns", {
      method: "POST",
      body: JSON.stringify({ word, domain, source: "manual", actor: "dashboard-admin" }),
    }),
  updateCompoundDomain: (id: number, domain: string) =>
    request(`/dictionary/compound-nouns/${id}/domain`, {
      method: "PATCH",
      body: JSON.stringify({ domain, actor: "dashboard-admin" }),
    }),
  deleteCompound: (id: number) =>
    request(`/dictionary/compound-nouns/${id}`, { method: "DELETE" }),
  approveCandidate: (id: number) =>
    request(`/dictionary/compound-candidates/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ reviewed_by: "dashboard-admin" }),
    }),
  rejectCandidate: (id: number) =>
    request(`/dictionary/compound-candidates/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewed_by: "dashboard-admin" }),
    }),
  createStopword: (word: string, domain = "all") =>
    request("/dictionary/stopwords", {
      method: "POST",
      body: JSON.stringify({ word, domain, language: "ko", actor: "dashboard-admin" }),
    }),
  updateStopwordDomain: (id: number, domain: string) =>
    request(`/dictionary/stopwords/${id}/domain`, {
      method: "PATCH",
      body: JSON.stringify({ domain, actor: "dashboard-admin" }),
    }),
  deleteStopword: (id: number) =>
    request(`/dictionary/stopwords/${id}`, { method: "DELETE" }),
  dictionaryStopwordCandidates: (page: number, limit: number, q: string, status: string, domain?: string) =>
    request<DictionaryPage<StopwordCandidateItem>>(
      `/dictionary/stopword-candidates?page=${page}&limit=${limit}&q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}${domain && domain !== "all" ? `&domain=${encodeURIComponent(domain)}` : ""}`,
    ),
  approveStopwordCandidate: (id: number) =>
    request(`/dictionary/stopword-candidates/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ reviewed_by: "dashboard-admin" }),
    }),
  rejectStopwordCandidate: (id: number) =>
    request(`/dictionary/stopword-candidates/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewed_by: "dashboard-admin" }),
    }),
  runCompoundAutoApprove: () =>
    request<Record<string, number>>("/admin/run-compound-auto-approve", { method: "POST" }),
  runStopwordRecommender: () =>
    request<Record<string, number>>("/admin/run-stopword-recommender", { method: "POST" }),
  createQueryKeyword: (payload: { domain_id: string; query: string; sort_order: number; is_active?: boolean }) =>
    request<QueryKeywordItem>("/admin/query-keywords", {
      method: "POST",
      body: JSON.stringify({
        domain_id: payload.domain_id,
        query: payload.query,
        sort_order: payload.sort_order,
        is_active: payload.is_active ?? true,
        actor: "dashboard-admin",
      }),
    }),
  updateQueryKeyword: (id: number, payload: { domain_id: string; query: string; sort_order: number; is_active: boolean }) =>
    request<QueryKeywordItem>(`/admin/query-keywords/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        domain_id: payload.domain_id,
        query: payload.query,
        sort_order: payload.sort_order,
        is_active: payload.is_active,
        actor: "dashboard-admin",
      }),
    }),
  deleteQueryKeyword: (id: number) =>
    request(`/admin/query-keywords/${id}?actor=dashboard-admin`, { method: "DELETE" }),
};
