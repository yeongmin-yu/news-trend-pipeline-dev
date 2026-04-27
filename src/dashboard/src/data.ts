export type SourceId = "all" | "naver" | "global";
export type RangeId = "10m" | "30m" | "1h" | "6h" | "12h" | "1d";
export type TrendBucketId = "5m" | "15m" | "30m" | "1h" | "4h" | "1d";

type RawRecord = Record<string, unknown>;
export type OverviewRawPayload = {
  data: DashboardOverviewResponse;
  identity: string;
  contextKey: string;
};
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
  sourceShareNaver?: number;
  sourceShareGlobal?: number;
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
  range: RangeOption | { id: string; label: string; bucketMin: number; buckets: number };
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
  topKeywords?: string[];
  events: SpikeEvent[];
  range: RangeOption | { id: string; label: string; bucketMin: number; buckets: number };
}

export interface OverviewArticleBucket {
  bucket: number;
  timestamp: string;
  articleCount: number;
  lastUpdateAt: string | null;
}

export interface OverviewKeywordBucket {
  keyword: string;
  bucket: number;
  timestamp: string;
  mentions: number;
  articleCount: number;
}

export interface OverviewCachePayload {
  requestedStartAt: string;
  requestedEndAt: string;
  fetchStartAt: string;
  fetchEndAt: string;
  dataStartAt: string;
  dataEndAt: string;
  bucket: TrendBucketId;
  bucketMin: number;
  buckets: number;
  candidateKeywords: string[];
  articleBuckets: OverviewArticleBucket[];
  keywordBuckets: OverviewKeywordBucket[];
  range: RangeOption | { id: string; label: string; bucketMin: number; buckets: number };
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
  domain: string;
  source: string;
  createdAt: string;
}

export interface CompoundCandidateAutoEvidenceSummary {
  frequencyPerDoc?: number | null;
  naverTotal?: number | null;
  hasExactCompactMatch?: boolean | null;
  matchedField?: string | null;
  matchedTitle?: string | null;
  matchedLink?: string | null;
}

export interface CompoundCandidateItem {
  id: number;
  word: string;
  domain: string;
  frequency: number;
  docCount: number;
  firstSeenAt: string;
  lastSeenAt: string;
  status: string;
  reviewedAt: string | null;
  reviewedBy: string | null;
  autoScore?: number | null;
  autoDecision?: string | null;
  autoCheckedAt?: string | null;
  autoEvidence?: Record<string, unknown> | null;
  autoEvidenceSummary?: CompoundCandidateAutoEvidenceSummary | null;
}

export interface StopwordItem {
  id: number;
  word: string;
  domain: string;
  language: string;
  createdAt: string;
}

export interface StopwordCandidateItem {
  id: number;
  word: string;
  domain: string;
  language: string;
  score: number;
  domainBreadth: number;
  repetitionRate: number;
  trendStability: number;
  cooccurrenceBreadth: number;
  shortWord: boolean;
  frequency: number;
  status: string;
  firstSeenAt: string;
  lastSeenAt: string;
  reviewedAt: string | null;
  reviewedBy: string | null;
}

export interface DictionaryMeta {
  compoundNounCount: number;
  candidateCount: number;
  stopwordCount: number;
  versions: {
    compoundNounDict: number;
    stopwordDict: number;
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
  compoundNouns: CompoundNounItem[];
  compoundCandidates: CompoundCandidateItem[];
  stopwords: StopwordItem[];
}

export interface QueryKeywordItem {
  id: number;
  provider: string;
  domainId: string;
  domainLabel: string;
  query: string;
  sortOrder: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface QueryKeywordAuditLog {
  id: number;
  queryKeywordId: number | null;
  action: string;
  beforeJson: Record<string, unknown> | null;
  afterJson: Record<string, unknown> | null;
  actor: string;
  actedAt: string;
}

export interface CollectionMetricItem {
  provider: string;
  domain: string;
  query: string;
  requestCount: number;
  successCount: number;
  articleCount: number;
  duplicateCount: number;
  publishCount: number;
  errorCount: number;
  lastSeenAt: string;
}

export interface QueryKeywordAdminOverview {
  domains: DomainOption[];
  queryKeywords: QueryKeywordItem[];
  auditLogs: QueryKeywordAuditLog[];
  collectionMetrics: CollectionMetricItem[];
}

const API_BASE = "/api/v1";

function pick<T>(row: RawRecord | null | undefined, camel: string, snake: string, fallback: T): T {
  if (!row) return fallback;
  const value = row[camel] ?? row[snake];
  return (value ?? fallback) as T;
}

function normalizeRange(row: RawRecord): RangeOption | { id: string; label: string; bucketMin: number; buckets: number } {
  return {
    id: String(row.id ?? "custom") as RangeId,
    label: String(row.label ?? row.id ?? "custom"),
    bucketMin: Number(row.bucketMin ?? row.bucket_min ?? 5),
    buckets: Number(row.buckets ?? 12),
  };
}

function normalizeKeyword(row: RawRecord): KeywordSummary {
  return {
    keyword: String(row.keyword ?? ""),
    mentions: Number(row.mentions ?? 0),
    prevMentions: Number(row.prevMentions ?? row.prev_mentions ?? 0),
    growth: Number(row.growth ?? 0),
    delta: Number(row.delta ?? 0),
    spike: Boolean(row.spike),
    eventScore: Number(row.eventScore ?? row.event_score ?? 0),
    articleCount: Number(row.articleCount ?? row.article_count ?? 0),
    sourceShareNaver: row.sourceShareNaver != null || row.source_share_naver != null ? Number(row.sourceShareNaver ?? row.source_share_naver) : undefined,
    sourceShareGlobal: row.sourceShareGlobal != null || row.source_share_global != null ? Number(row.sourceShareGlobal ?? row.source_share_global) : undefined,
  };
}

function normalizeKpis(row: RawRecord): KpiSummary {
  return {
    totalArticles: Number(row.totalArticles ?? row.total_articles ?? 0),
    uniqueKeywords: Number(row.uniqueKeywords ?? row.unique_keywords ?? 0),
    spikeCount: Number(row.spikeCount ?? row.spike_count ?? 0),
    growth: Number(row.growth ?? 0),
    lastUpdateRelative: String(row.lastUpdateRelative ?? row.last_update_relative ?? "데이터 없음"),
    lastUpdateAbsolute: String(row.lastUpdateAbsolute ?? row.last_update_absolute ?? "데이터 없음"),
  };
}

function normalizeSpikeEvent(row: RawRecord): SpikeEvent {
  return {
    bucket: Number(row.bucket ?? 0),
    keyword: String(row.keyword ?? ""),
    intensity: Number(row.intensity ?? 0),
    source: (row.source === "global" ? "global" : "naver"),
    currentMentions: Number(row.currentMentions ?? row.current_mentions ?? 0),
    prevMentions: Number(row.prevMentions ?? row.prev_mentions ?? 0),
    growth: Number(row.growth ?? 0),
    score: Number(row.score ?? 0),
  };
}

function normalizeSpikeResponse(row: RawRecord): SpikeResponse {
  return {
    topKeywords: ((row.topKeywords ?? row.top_keywords) as string[] | undefined) ?? [],
    events: (((row.events as RawRecord[] | undefined) ?? [])).map(normalizeSpikeEvent),
    range: normalizeRange((row.range as RawRecord | undefined) ?? {}),
  };
}

function normalizeArticleBucket(row: RawRecord): OverviewArticleBucket {
  return {
    bucket: Number(row.bucket ?? 0),
    timestamp: String(row.timestamp ?? ""),
    articleCount: Number(row.articleCount ?? row.article_count ?? 0),
    lastUpdateAt: (row.lastUpdateAt ?? row.last_update_at ?? null) as string | null,
  };
}

function normalizeKeywordBucket(row: RawRecord): OverviewKeywordBucket {
  return {
    keyword: String(row.keyword ?? ""),
    bucket: Number(row.bucket ?? 0),
    timestamp: String(row.timestamp ?? ""),
    mentions: Number(row.mentions ?? 0),
    articleCount: Number(row.articleCount ?? row.article_count ?? 0),
  };
}

function normalizeOverviewCache(row: RawRecord | undefined): OverviewCachePayload | undefined {
  if (!row) return undefined;
  return {
    requestedStartAt: String(row.requestedStartAt ?? row.requested_start_at ?? ""),
    requestedEndAt: String(row.requestedEndAt ?? row.requested_end_at ?? ""),
    fetchStartAt: String(row.fetchStartAt ?? row.fetch_start_at ?? ""),
    fetchEndAt: String(row.fetchEndAt ?? row.fetch_end_at ?? ""),
    dataStartAt: String(row.dataStartAt ?? row.data_start_at ?? ""),
    dataEndAt: String(row.dataEndAt ?? row.data_end_at ?? ""),
    bucket: String(row.bucket ?? "15m") as TrendBucketId,
    bucketMin: Number(row.bucketMin ?? row.bucket_min ?? 15),
    buckets: Number(row.buckets ?? 0),
    candidateKeywords: ((row.candidateKeywords ?? row.candidate_keywords) as string[] | undefined) ?? [],
    articleBuckets: (((row.articleBuckets ?? row.article_buckets) as RawRecord[] | undefined) ?? []).map(normalizeArticleBucket),
    keywordBuckets: (((row.keywordBuckets ?? row.keyword_buckets) as RawRecord[] | undefined) ?? []).map(normalizeKeywordBucket),
    range: normalizeRange((row.range as RawRecord | undefined) ?? {}),
  };
}

function normalizeOverview(row: RawRecord): DashboardOverviewResponse {
  return {
    kpis: normalizeKpis((row.kpis as RawRecord | undefined) ?? {}),
    keywords: (((row.keywords as RawRecord[] | undefined) ?? [])).map(normalizeKeyword),
    spikes: normalizeSpikeResponse((row.spikes as RawRecord | undefined) ?? {}),
    cache: normalizeOverviewCache(row.cache as RawRecord | undefined),
  };
}

function normalizeTrend(row: RawRecord): TrendResponse {
  return {
    series: ((row.series as TrendSeries[] | undefined) ?? []),
    range: normalizeRange((row.range as RawRecord | undefined) ?? {}),
  };
}

function normalizeArticle(row: RawRecord): ArticleItem {
  return {
    id: String(row.id ?? ""),
    title: String(row.title ?? ""),
    summary: String(row.summary ?? ""),
    publisher: String(row.publisher ?? ""),
    source: String(row.source ?? ""),
    domain: row.domain as string | undefined,
    publishedAt: (row.publishedAt ?? row.published_at ?? null) as string | null,
    minutesAgo: row.minutesAgo != null || row.minutes_ago != null ? Number(row.minutesAgo ?? row.minutes_ago) : null,
    keywords: (row.keywords as string[] | undefined) ?? [],
    primaryKeyword: (row.primaryKeyword ?? row.primary_keyword ?? null) as string | null,
    duplicates: Number(row.duplicates ?? 0),
    url: String(row.url ?? ""),
  };
}

function normalizeSystem(row: RawRecord): SystemStatusResponse {
  return {
    services: (((row.services as RawRecord[] | undefined) ?? [])).map((service) => ({
      key: String(service.key ?? ""),
      label: String(service.label ?? ""),
      status: (service.status as ServiceStatus["status"]) ?? "unknown",
      detail: String(service.detail ?? ""),
      statusCode: service.statusCode != null || service.status_code != null ? Number(service.statusCode ?? service.status_code) : null,
    })),
  };
}

function normalizeDictionaryMeta(row: RawRecord): DictionaryMeta {
  const versions = (row.versions as RawRecord | undefined) ?? {};
  return {
    compoundNounCount: Number(row.compoundNounCount ?? row.compound_noun_count ?? 0),
    candidateCount: Number(row.candidateCount ?? row.candidate_count ?? 0),
    stopwordCount: Number(row.stopwordCount ?? row.stopword_count ?? 0),
    versions: {
      compoundNounDict: Number(versions.compoundNounDict ?? versions.compound_noun_dict ?? 0),
      stopwordDict: Number(versions.stopwordDict ?? versions.stopword_dict ?? 0),
    },
  };
}

function normalizeCompound(row: RawRecord): CompoundNounItem {
  return {
    id: Number(row.id ?? 0),
    word: String(row.word ?? ""),
    domain: String(row.domain ?? "all"),
    source: String(row.source ?? ""),
    createdAt: String(row.createdAt ?? row.created_at ?? ""),
  };
}

function normalizeEvidenceSummary(row: RawRecord | null | undefined): CompoundCandidateAutoEvidenceSummary | null {
  if (!row) return null;
  return {
    frequencyPerDoc: row.frequencyPerDoc != null || row.frequency_per_doc != null ? Number(row.frequencyPerDoc ?? row.frequency_per_doc) : null,
    naverTotal: row.naverTotal != null || row.naver_total != null ? Number(row.naverTotal ?? row.naver_total) : null,
    hasExactCompactMatch: (row.hasExactCompactMatch ?? row.has_exact_compact_match ?? null) as boolean | null,
    matchedField: (row.matchedField ?? row.matched_field ?? null) as string | null,
    matchedTitle: (row.matchedTitle ?? row.matched_title ?? null) as string | null,
    matchedLink: (row.matchedLink ?? row.matched_link ?? null) as string | null,
  };
}

function normalizeCandidate(row: RawRecord): CompoundCandidateItem {
  return {
    id: Number(row.id ?? 0),
    word: String(row.word ?? ""),
    domain: String(row.domain ?? "all"),
    frequency: Number(row.frequency ?? 0),
    docCount: Number(row.docCount ?? row.doc_count ?? 0),
    firstSeenAt: String(row.firstSeenAt ?? row.first_seen_at ?? ""),
    lastSeenAt: String(row.lastSeenAt ?? row.last_seen_at ?? ""),
    status: String(row.status ?? "needs_review"),
    reviewedAt: (row.reviewedAt ?? row.reviewed_at ?? null) as string | null,
    reviewedBy: (row.reviewedBy ?? row.reviewed_by ?? null) as string | null,
    autoScore: row.autoScore != null || row.auto_score != null ? Number(row.autoScore ?? row.auto_score) : null,
    autoDecision: (row.autoDecision ?? row.auto_decision ?? null) as string | null,
    autoCheckedAt: (row.autoCheckedAt ?? row.auto_checked_at ?? null) as string | null,
    autoEvidence: (row.autoEvidence ?? row.auto_evidence ?? null) as Record<string, unknown> | null,
    autoEvidenceSummary: normalizeEvidenceSummary((row.autoEvidenceSummary ?? row.auto_evidence_summary) as RawRecord | null | undefined),
  };
}

function normalizeStopword(row: RawRecord): StopwordItem {
  return {
    id: Number(row.id ?? 0),
    word: String(row.word ?? ""),
    domain: String(row.domain ?? "all"),
    language: String(row.language ?? "ko"),
    createdAt: String(row.createdAt ?? row.created_at ?? ""),
  };
}

function normalizeStopwordCandidate(row: RawRecord): StopwordCandidateItem {
  return {
    id: Number(row.id ?? 0),
    word: String(row.word ?? ""),
    domain: String(row.domain ?? "all"),
    language: String(row.language ?? "ko"),
    score: Number(row.score ?? 0),
    domainBreadth: Number(row.domainBreadth ?? row.domain_breadth ?? 0),
    repetitionRate: Number(row.repetitionRate ?? row.repetition_rate ?? 0),
    trendStability: Number(row.trendStability ?? row.trend_stability ?? 0),
    cooccurrenceBreadth: Number(row.cooccurrenceBreadth ?? row.cooccurrence_breadth ?? 0),
    shortWord: Boolean(row.shortWord ?? row.short_word),
    frequency: Number(row.frequency ?? 0),
    status: String(row.status ?? "needs_review"),
    firstSeenAt: String(row.firstSeenAt ?? row.first_seen_at ?? ""),
    lastSeenAt: String(row.lastSeenAt ?? row.last_seen_at ?? ""),
    reviewedAt: (row.reviewedAt ?? row.reviewed_at ?? null) as string | null,
    reviewedBy: (row.reviewedBy ?? row.reviewed_by ?? null) as string | null,
  };
}

function normalizePage<T>(row: RawRecord, normalizeItem: (row: RawRecord) => T): DictionaryPage<T> {
  return {
    items: (((row.items as RawRecord[] | undefined) ?? [])).map(normalizeItem),
    total: Number(row.total ?? 0),
    page: Number(row.page ?? 1),
    limit: Number(row.limit ?? 50),
  };
}

async function requestRaw(path: string, init?: RequestInit): Promise<unknown> {
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
    return undefined;
  }
  return await response.json();
}

async function request<T>(path: string, init?: RequestInit, normalize?: (row: RawRecord) => T): Promise<T> {
  const data = await requestRaw(path, init);
  return normalize ? normalize((data ?? {}) as RawRecord) : data as T;
}

export const api = {
  filters: () => request<FiltersResponse>("/meta/filters", undefined, (row) => ({
    domains: (row.domains as DomainOption[] | undefined) ?? [],
    sources: (row.sources as SourceOption[] | undefined) ?? [],
    ranges: (((row.ranges as RawRecord[] | undefined) ?? [])).map(normalizeRange) as RangeOption[],
  })),
  kpis: (source: SourceId, domain: string, range: RangeId, startAt?: string, endAt?: string) =>
    request<KpiSummary>(
      `/dashboard/kpis?source=${source}&domain=${domain}&range=${range}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
      undefined,
      normalizeKpis,
    ),
  keywords: (source: SourceId, domain: string, range: RangeId, search: string, limit: number, startAt?: string, endAt?: string) =>
    request<KeywordSummary[]>(
      `/dashboard/keywords?source=${source}&domain=${domain}&range=${range}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ""}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
      undefined,
      (row) => (Array.isArray(row) ? row as RawRecord[] : []).map(normalizeKeyword),
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
      undefined,
      normalizeOverview,
    ),
  trend: (source: SourceId, domain: string, range: RangeId, keyword: string, keywords?: string[]) =>
    request<TrendResponse>(
      `/dashboard/trend?source=${source}&domain=${domain}&range=${range}&keyword=${encodeURIComponent(keyword)}${
        keywords?.length ? `&keywords=${encodeURIComponent(keywords.join(","))}` : ""
      }`,
      undefined,
      normalizeTrend,
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
      undefined,
      normalizeTrend,
    ),
  spikes: (source: SourceId, domain: string, range: RangeId, startAt?: string, endAt?: string, bucket?: TrendBucketId) =>
    request<SpikeResponse>(
      `/dashboard/spikes?source=${source}&domain=${domain}&range=${range}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }${bucket ? `&bucket=${bucket}` : ""}`,
      undefined,
      normalizeSpikeResponse,
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
      undefined,
      (row) => ({
        keyword: String(row.keyword ?? ""),
        totalMentions: Number(row.totalMentions ?? row.total_mentions ?? 0),
        items: (row.items as ThemeDistributionItem[] | undefined) ?? [],
      }),
    ),
  articles: (source: SourceId, domain: string, range: RangeId, keyword: string, sort: "latest" | "relevance", startAt?: string, endAt?: string) =>
    request<ArticleItem[]>(
      `/dashboard/articles?source=${source}&domain=${domain}&range=${range}&keyword=${encodeURIComponent(keyword)}&sort=${sort}${
        startAt && endAt ? `&startAt=${encodeURIComponent(startAt)}&endAt=${encodeURIComponent(endAt)}` : ""
      }`,
      undefined,
      (row) => (Array.isArray(row) ? row as RawRecord[] : []).map(normalizeArticle),
    ),
  system: () => request<SystemStatusResponse>("/dashboard/system", undefined, normalizeSystem),
  dictionaryMeta: () => request<DictionaryMeta>("/dictionary", undefined, normalizeDictionaryMeta),
  dictionaryCompoundNouns: (page: number, limit: number, q: string, domain?: string) =>
    request<DictionaryPage<CompoundNounItem>>(
      `/dictionary/compound-nouns?page=${page}&limit=${limit}&q=${encodeURIComponent(q)}${domain && domain !== "all" ? `&domain=${encodeURIComponent(domain)}` : ""}`,
      undefined,
      (row) => normalizePage(row, normalizeCompound),
    ),
  dictionaryStopwords: (page: number, limit: number, q: string, domain?: string) =>
    request<DictionaryPage<StopwordItem>>(
      `/dictionary/stopwords?page=${page}&limit=${limit}&q=${encodeURIComponent(q)}${domain && domain !== "all" ? `&domain=${encodeURIComponent(domain)}` : ""}`,
      undefined,
      (row) => normalizePage(row, normalizeStopword),
    ),
  dictionaryCandidates: (page: number, limit: number, q: string, status: string, domain?: string) =>
    request<DictionaryPage<CompoundCandidateItem>>(
      `/dictionary/candidates?page=${page}&limit=${limit}&q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}${domain && domain !== "all" ? `&domain=${encodeURIComponent(domain)}` : ""}`,
      undefined,
      (row) => normalizePage(row, normalizeCandidate),
    ),
  /** @deprecated */
  dictionary: () => request<DictionaryOverview>("/dictionary", undefined, (row) => normalizeDictionaryMeta(row) as DictionaryOverview),
  queryKeywordAdmin: () => request<QueryKeywordAdminOverview>("/admin/query-keywords", undefined, (row) => ({
    domains: (row.domains as DomainOption[] | undefined) ?? [],
    queryKeywords: (((row.queryKeywords ?? row.query_keywords) as RawRecord[] | undefined) ?? []).map((item) => ({
      id: Number(item.id ?? 0),
      provider: String(item.provider ?? ""),
      domainId: String(item.domainId ?? item.domain_id ?? ""),
      domainLabel: String(item.domainLabel ?? item.domain_label ?? ""),
      query: String(item.query ?? ""),
      sortOrder: Number(item.sortOrder ?? item.sort_order ?? 0),
      isActive: Boolean(item.isActive ?? item.is_active),
      createdAt: String(item.createdAt ?? item.created_at ?? ""),
      updatedAt: String(item.updatedAt ?? item.updated_at ?? ""),
    })),
    auditLogs: (((row.auditLogs ?? row.audit_logs) as RawRecord[] | undefined) ?? []).map((item) => ({
      id: Number(item.id ?? 0),
      queryKeywordId: (item.queryKeywordId ?? item.query_keyword_id ?? null) as number | null,
      action: String(item.action ?? ""),
      beforeJson: (item.beforeJson ?? item.before_json ?? null) as Record<string, unknown> | null,
      afterJson: (item.afterJson ?? item.after_json ?? null) as Record<string, unknown> | null,
      actor: String(item.actor ?? ""),
      actedAt: String(item.actedAt ?? item.acted_at ?? ""),
    })),
    collectionMetrics: (((row.collectionMetrics ?? row.collection_metrics) as RawRecord[] | undefined) ?? []).map((item) => ({
      provider: String(item.provider ?? ""),
      domain: String(item.domain ?? ""),
      query: String(item.query ?? ""),
      requestCount: Number(item.requestCount ?? item.request_count ?? 0),
      successCount: Number(item.successCount ?? item.success_count ?? 0),
      articleCount: Number(item.articleCount ?? item.article_count ?? 0),
      duplicateCount: Number(item.duplicateCount ?? item.duplicate_count ?? 0),
      publishCount: Number(item.publishCount ?? item.publish_count ?? 0),
      errorCount: Number(item.errorCount ?? item.error_count ?? 0),
      lastSeenAt: String(item.lastSeenAt ?? item.last_seen_at ?? ""),
    })),
  })),
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
      undefined,
      (row) => normalizePage(row, normalizeStopwordCandidate),
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
  createQueryKeyword: (payload: { domainId: string; query: string; sortOrder: number; isActive?: boolean }) =>
    request<QueryKeywordItem>("/admin/query-keywords", {
      method: "POST",
      body: JSON.stringify({
        domain_id: payload.domainId,
        query: payload.query,
        sort_order: payload.sortOrder,
        is_active: payload.isActive ?? true,
        actor: "dashboard-admin",
      }),
    }),
  updateQueryKeyword: (id: number, payload: { domainId: string; query: string; sortOrder: number; isActive: boolean }) =>
    request<QueryKeywordItem>(`/admin/query-keywords/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        domain_id: payload.domainId,
        query: payload.query,
        sort_order: payload.sortOrder,
        is_active: payload.isActive,
        actor: "dashboard-admin",
      }),
    }),
  deleteQueryKeyword: (id: number) =>
    request(`/admin/query-keywords/${id}?actor=dashboard-admin`, { method: "DELETE" }),
};
