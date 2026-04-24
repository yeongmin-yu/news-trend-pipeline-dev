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
  bucketMin: number;
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
  prevMentions: number;
  growth: number;
  delta: number;
  spike: boolean;
  eventScore: number;
  articleCount: number;
}

export interface KpiSummary {
  totalArticles: number;
  uniqueKeywords: number;
  spikeCount: number;
  growth: number;
  lastUpdateRelative: string;
  lastUpdateAbsolute: string;
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
  range: RangeOption;
}

export interface SpikeEvent {
  bucket: number;
  keyword: string;
  intensity: number;
  source: "naver" | "global";
  currentMentions: number;
  prevMentions: number;
  growth: number;
  score: number;
}

export interface SpikeResponse {
  topKeywords: string[];
  events: SpikeEvent[];
  range: RangeOption;
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
  totalMentions: number;
  items: ThemeDistributionItem[];
}

export interface ArticleItem {
  id: string;
  title: string;
  summary: string;
  publisher: string;
  source: string;
  domain?: string;
  publishedAt: string | null;
  minutesAgo: number | null;
  keywords: string[];
  primaryKeyword: string | null;
  duplicates: number;
  url: string;
}

export interface ServiceStatus {
  key: string;
  label: string;
  status: "ok" | "warn" | "down" | "unknown";
  detail: string;
  statusCode?: number | null;
}

export interface SystemStatusResponse {
  services: ServiceStatus[];
}

export interface CompoundNounItem {
  id: number;
  word: string;
  source: string;
  createdAt: string;
}

export interface CompoundCandidateItem {
  id: number;
  word: string;
  frequency: number;
  docCount: number;
  firstSeenAt: string;
  lastSeenAt: string;
  status: string;
  reviewedAt: string | null;
  reviewedBy: string | null;
}

export interface StopwordItem {
  id: number;
  word: string;
  language: string;
  createdAt: string;
}

export interface DictionaryOverview {
  compoundNouns: CompoundNounItem[];
  compoundCandidates: CompoundCandidateItem[];
  stopwords: StopwordItem[];
  auditLogs?: Array<{
    id: number;
    entity_type: string;
    entity_id: number | null;
    action: string;
    before_json: Record<string, unknown> | null;
    after_json: Record<string, unknown> | null;
    actor: string;
    acted_at: string;
  }>;
  versions: {
    compoundNounDict: number;
    stopwordDict: number;
  };
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
  queryKeywords: QueryKeywordItem[];
  auditLogs: QueryKeywordAuditLog[];
  collectionMetrics: CollectionMetricItem[];
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
  kpis: (source: SourceId, domain: string, range: RangeId) =>
    request<KpiSummary>(`/dashboard/kpis?source=${source}&domain=${domain}&range=${range}`),
  keywords: (source: SourceId, domain: string, range: RangeId, search: string, limit: number) =>
    request<KeywordSummary[]>(
      `/dashboard/keywords?source=${source}&domain=${domain}&range=${range}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ""}`,
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
  spikes: (source: SourceId, domain: string, range: RangeId) =>
    request<SpikeResponse>(`/dashboard/spikes?source=${source}&domain=${domain}&range=${range}`),
  related: (source: SourceId, domain: string, range: RangeId, keyword: string) =>
    request<RelatedKeyword[]>(
      `/dashboard/related?source=${source}&domain=${domain}&range=${range}&keyword=${encodeURIComponent(keyword)}`,
    ),
  themeDistribution: (source: SourceId, range: RangeId, keyword: string) =>
    request<ThemeDistributionResponse>(
      `/dashboard/theme-distribution?source=${source}&range=${range}&keyword=${encodeURIComponent(keyword)}`,
    ),
  articles: (source: SourceId, domain: string, range: RangeId, keyword: string, sort: "latest" | "relevance") =>
    request<ArticleItem[]>(
      `/dashboard/articles?source=${source}&domain=${domain}&range=${range}&keyword=${encodeURIComponent(keyword)}&sort=${sort}`,
    ),
  system: () => request<SystemStatusResponse>("/dashboard/system"),
  dictionary: () => request<DictionaryOverview>("/dictionary"),
  queryKeywordAdmin: () => request<QueryKeywordAdminOverview>("/admin/query-keywords"),
  createCompound: (word: string) =>
    request("/dictionary/compound-nouns", {
      method: "POST",
      body: JSON.stringify({ word, source: "manual", actor: "dashboard-admin" }),
    }),
  deleteCompound: (id: number) =>
    request(`/dictionary/compound-nouns/${id}`, { method: "DELETE" }),
  approveCandidate: (id: number) =>
    request(`/dictionary/compound-candidates/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ reviewedBy: "dashboard-admin" }),
    }),
  rejectCandidate: (id: number) =>
    request(`/dictionary/compound-candidates/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reviewedBy: "dashboard-admin" }),
    }),
  createStopword: (word: string) =>
    request("/dictionary/stopwords", {
      method: "POST",
      body: JSON.stringify({ word, language: "ko", actor: "dashboard-admin" }),
    }),
  deleteStopword: (id: number) =>
    request(`/dictionary/stopwords/${id}`, { method: "DELETE" }),
  createQueryKeyword: (payload: { domainId: string; query: string; sortOrder: number; isActive?: boolean }) =>
    request<QueryKeywordItem>("/admin/query-keywords", {
      method: "POST",
      body: JSON.stringify({
        domainId: payload.domainId,
        query: payload.query,
        sortOrder: payload.sortOrder,
        isActive: payload.isActive ?? true,
        actor: "dashboard-admin",
      }),
    }),
  updateQueryKeyword: (id: number, payload: { domainId: string; query: string; sortOrder: number; isActive: boolean }) =>
    request<QueryKeywordItem>(`/admin/query-keywords/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        domainId: payload.domainId,
        query: payload.query,
        sortOrder: payload.sortOrder,
        isActive: payload.isActive,
        actor: "dashboard-admin",
      }),
    }),
  deleteQueryKeyword: (id: number) =>
    request(`/admin/query-keywords/${id}?actor=dashboard-admin`, { method: "DELETE" }),
};
