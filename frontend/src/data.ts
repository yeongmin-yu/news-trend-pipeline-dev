export type SourceId = "all" | "naver" | "global";
export type RangeId = "10m" | "30m" | "1h" | "6h" | "12h" | "1d";

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
  sourceShareNaver: number;
  sourceShareGlobal: number;
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

export interface ArticleItem {
  id: string;
  title: string;
  summary: string;
  publisher: string;
  source: string;
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
  versions: {
    compoundNounDict: number;
    stopwordDict: number;
  };
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
  kpis: (source: SourceId, range: RangeId) =>
    request<KpiSummary>(`/dashboard/kpis?source=${source}&range=${range}`),
  keywords: (source: SourceId, range: RangeId, search: string, limit: number) =>
    request<KeywordSummary[]>(
      `/dashboard/keywords?source=${source}&range=${range}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ""}`,
    ),
  trend: (source: SourceId, range: RangeId, keyword: string) =>
    request<TrendResponse>(`/dashboard/trend?source=${source}&range=${range}&keyword=${encodeURIComponent(keyword)}`),
  spikes: (source: SourceId, range: RangeId) =>
    request<SpikeResponse>(`/dashboard/spikes?source=${source}&range=${range}`),
  related: (source: SourceId, range: RangeId, keyword: string) =>
    request<RelatedKeyword[]>(
      `/dashboard/related?source=${source}&range=${range}&keyword=${encodeURIComponent(keyword)}`,
    ),
  articles: (source: SourceId, range: RangeId, keyword: string, sort: "latest" | "relevance") =>
    request<ArticleItem[]>(
      `/dashboard/articles?source=${source}&range=${range}&keyword=${encodeURIComponent(keyword)}&sort=${sort}`,
    ),
  system: () => request<SystemStatusResponse>("/dashboard/system"),
  dictionary: () => request<DictionaryOverview>("/dictionary"),
  createCompound: (word: string) =>
    request("/dictionary/compound-nouns", {
      method: "POST",
      body: JSON.stringify({ word, source: "manual" }),
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
      body: JSON.stringify({ word, language: "ko" }),
    }),
  deleteStopword: (id: number) =>
    request(`/dictionary/stopwords/${id}`, { method: "DELETE" }),
};
