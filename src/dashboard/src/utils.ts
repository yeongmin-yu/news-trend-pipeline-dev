import type {
  DashboardOverviewResponse,
  KeywordSummary,
  OverviewCachePayload,
  SourceId,
  TrendBucketId,
} from "./data";
import {
  DOMAIN_COLORS,
  MIN_TREND_WINDOW_MS,
  MAX_TREND_WINDOW_MS,
  TREND_BUCKET_OPTIONS,
  TREND_FETCH_OVERSCAN_BUCKETS,
} from "./constants";
import { fmtAgo } from "./ui";

export function fmtKST(ms: number, withSeconds = false): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const kst = new Date(ms + 9 * 3600_000);
  const date = `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())}`;
  const time = withSeconds
    ? `${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}:${pad(kst.getUTCSeconds())}`
    : `${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}`;
  return `${date} ${time} KST`;
}

export function getDomainColor(domainId: string, available: boolean): string {
  if (!available) return "var(--text-4)";
  return DOMAIN_COLORS[domainId] ?? "var(--accent)";
}

export function getTopKeywordBarColor(domainId: string): string {
  return DOMAIN_COLORS[domainId] ?? DOMAIN_COLORS.all;
}

export function rankKeywords(items: KeywordSummary[], sortBy: "mentions" | "growth"): KeywordSummary[] {
  const ranked = [...items];
  if (sortBy === "growth") ranked.sort((a, b) => (b.growth ?? 0) - (a.growth ?? 0));
  else ranked.sort((a, b) => b.mentions - a.mentions);
  return ranked;
}

export function isSpikeKeyword(
  item: Pick<KeywordSummary, "mentions" | "growth">,
  minMentions: number,
  minGrowth: number,
): boolean {
  return item.mentions >= minMentions && item.growth >= minGrowth;
}

export function pickAutoTrendBucket(durationMs: number): TrendBucketId {
  if (durationMs <= 6 * 60 * 60 * 1000) return "5m";
  if (durationMs <= 2 * 24 * 60 * 60 * 1000) return "15m";
  if (durationMs <= 7 * 24 * 60 * 60 * 1000) return "1h";
  return "4h";
}

export function getTrendbucketMinutes(bucketId: TrendBucketId): number {
  return TREND_BUCKET_OPTIONS.find((item) => item.id === bucketId)?.minutes ?? 15;
}

export function clampTrendWindow(startMs: number, endMs: number, nowMs: number): [number, number] {
  let start = startMs;
  let end = endMs;
  const duration = Math.min(MAX_TREND_WINDOW_MS, Math.max(MIN_TREND_WINDOW_MS, end - start));
  if (end > nowMs) {
    end = nowMs;
    start = end - duration;
  }
  if (end - start < duration) {
    start = end - duration;
  }
  return [start, end];
}

export function expandTrendFetchWindow(
  startMs: number,
  endMs: number,
  bucketId: TrendBucketId,
  nowMs: number,
) {
  const bucketMs = getTrendbucketMinutes(bucketId) * 60_000;
  const visibleBuckets = Math.max(1, Math.ceil((endMs - startMs) / bucketMs));
  const overscanBuckets = Math.max(
    TREND_FETCH_OVERSCAN_BUCKETS,
    Math.min(18, Math.ceil(visibleBuckets * 0.35)),
  );
  const overscanMs = bucketMs * overscanBuckets;
  return {
    startMs: Math.max(0, startMs - overscanMs),
    endMs: Math.min(nowMs, endMs + overscanMs),
  };
}

export function expandOverviewFetchWindow(startMs: number, endMs: number, nowMs: number) {
  const duration = Math.max(MIN_TREND_WINDOW_MS, endMs - startMs);
  const overscanMs = Math.max(15 * 60_000, Math.min(duration, Math.floor(duration * 0.75)));
  return {
    startMs: Math.max(0, startMs - overscanMs),
    endMs: Math.min(nowMs, endMs + overscanMs),
  };
}

export function pickOverviewBucket(fetchWindowMs: number): TrendBucketId {
  if (fetchWindowMs <= 3 * 60 * 60 * 1000) return "5m";
  if (fetchWindowMs <= 12 * 60 * 60 * 1000) return "15m";
  if (fetchWindowMs <= 3 * 24 * 60 * 60 * 1000) return "30m";
  if (fetchWindowMs <= 7 * 24 * 60 * 60 * 1000) return "1h";
  return "4h";
}

export function fmtAbsoluteKst(value: string | null): string {
  if (!value) return "데이터 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "데이터 없음";
  const kst = new Date(date.getTime() + 9 * 3600_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())} ${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}:${pad(kst.getUTCSeconds())} KST`;
}

export function deriveOverviewFromCache(
  source: SourceId,
  cache: OverviewCachePayload | undefined,
  startMs: number,
  endMs: number,
  limit: number,
  nowMs: number,
): DashboardOverviewResponse | null {
  if (!cache) return null;
  const articleBuckets = cache.articleBuckets ?? [];
  const keywordBuckets = cache.keywordBuckets ?? [];
  const durationMs = endMs - startMs;
  const prevStartMs = startMs - durationMs;
  const currentRows = articleBuckets.filter((row) => {
    const ts = new Date(row.timestamp).getTime();
    return ts >= startMs && ts < endMs;
  });
  const prevRows = articleBuckets.filter((row) => {
    const ts = new Date(row.timestamp).getTime();
    return ts >= prevStartMs && ts < startMs;
  });
  const currentBucketSet = new Set(currentRows.map((row) => row.bucket));
  const currentArticles = currentRows.reduce((sum, row) => sum + row.articleCount, 0);
  const prevArticles = prevRows.reduce((sum, row) => sum + row.articleCount, 0);
  const lastUpdateCandidates = currentRows
    .map((row) => row.lastUpdateAt)
    .filter((value): value is string => Boolean(value))
    .sort();
  const lastUpdateAt = lastUpdateCandidates.length
    ? lastUpdateCandidates[lastUpdateCandidates.length - 1]
    : null;

  const keywordMap = new Map<string, { mentions: Map<number, number>; articles: Map<number, number> }>();
  for (const row of keywordBuckets) {
    const current = keywordMap.get(row.keyword) ?? {
      mentions: new Map<number, number>(),
      articles: new Map<number, number>(),
    };
    current.mentions.set(row.bucket, row.mentions);
    current.articles.set(row.bucket, row.articleCount);
    keywordMap.set(row.keyword, current);
  }

  const derivedKeywords: KeywordSummary[] = [];
  const spikeEvents: DashboardOverviewResponse["spikes"]["events"] = [];
  const spikeKeywordSet = new Set<string>();
  const defaultEventSource = source === "global" ? "global" : "naver";
  const bucketCount = Math.max(1, Math.ceil(durationMs / (cache.bucketMin * 60_000)));

  for (const keyword of cache.candidateKeywords) {
    const series = keywordMap.get(keyword);
    if (!series) continue;
    let currentMentions = 0;
    let prevMentions = 0;
    let articleCount = 0;
    for (const row of currentRows) {
      currentMentions += series.mentions.get(row.bucket) ?? 0;
      articleCount += series.articles.get(row.bucket) ?? 0;
    }
    for (const row of prevRows) {
      prevMentions += series.mentions.get(row.bucket) ?? 0;
    }
    if (currentMentions <= 0 && prevMentions <= 0) continue;
    const growth =
      prevMentions <= 0
        ? currentMentions > 0
          ? 1
          : 0
        : (currentMentions - prevMentions) / prevMentions;
    const spike = currentMentions >= 5 && growth >= 0.4;
    const eventScore = Math.max(
      0,
      Math.min(100, Math.round(growth * 45 + Math.sqrt(currentMentions) * 6 + (spike ? 20 : 0))),
    );
    derivedKeywords.push({
      keyword,
      mentions: currentMentions,
      prevMentions,
      growth,
      delta: currentMentions - prevMentions,
      spike,
      eventScore,
      articleCount,
    });

    const orderedBuckets = Array.from(series.mentions.entries()).sort((a, b) => a[0] - b[0]);
    let previousBucketMentions = 0;
    for (const [bucket, mentions] of orderedBuckets) {
      if (mentions <= 0) continue;
      const bucketGrowth =
        previousBucketMentions <= 0
          ? mentions > 0
            ? 1
            : 0
          : (mentions - previousBucketMentions) / previousBucketMentions;
      if (currentBucketSet.has(bucket) && bucketGrowth >= 0.35 && mentions >= 3) {
        spikeKeywordSet.add(keyword);
        spikeEvents.push({
          bucket: Math.floor(
            (new Date(articleBuckets[bucket]?.timestamp ?? 0).getTime() - startMs) /
              (cache.bucketMin * 60_000),
          ),
          keyword,
          intensity: Math.min(1, Math.max(0.12, bucketGrowth)),
          source: defaultEventSource,
          currentMentions: mentions,
          prevMentions: previousBucketMentions,
          growth: bucketGrowth,
          score: eventScore,
        });
      }
      previousBucketMentions = mentions;
    }
  }

  derivedKeywords.sort((a, b) => b.mentions - a.mentions || a.keyword.localeCompare(b.keyword));
  const visibleEvents = spikeEvents
    .filter((item) => item.bucket >= 0 && item.bucket < bucketCount)
    .sort((a, b) => b.score - a.score || b.growth - a.growth);
  const growth =
    prevArticles <= 0
      ? currentArticles > 0
        ? 1
        : 0
      : (currentArticles - prevArticles) / prevArticles;
  const spikeTopKeywords = derivedKeywords
    .filter((item) => item.spike)
    .slice(0, 8)
    .map((item) => item.keyword);
  const lastUpdateMinutesAgo = lastUpdateAt
    ? Math.max(0, Math.floor((nowMs - new Date(lastUpdateAt).getTime()) / 60_000))
    : null;

  return {
    kpis: {
      totalArticles: currentArticles,
      uniqueKeywords: derivedKeywords.filter((item) => item.mentions > 0).length,
      spikeCount: spikeKeywordSet.size,
      growth,
      lastUpdateRelative: fmtAgo(lastUpdateMinutesAgo),
      lastUpdateAbsolute: fmtAbsoluteKst(lastUpdateAt),
    },
    keywords: derivedKeywords.slice(0, limit),
    spikes: {
      topKeywords: spikeTopKeywords.length
        ? spikeTopKeywords
        : derivedKeywords.slice(0, 8).map((item) => item.keyword),
      events: visibleEvents.slice(0, Math.max(limit, 32)),
      range: {
        id: "custom",
        label: `${cache.bucket} custom`,
        bucketMin: cache.bucketMin,
        buckets: bucketCount,
      },
    },
    cache,
  };
}

export function toDateTimeLocalInput(ms: number): string {
  const local = new Date(ms + 9 * 3600_000);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}T${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}`;
}

export function fromDateTimeLocalInput(value: string): number | null {
  if (!value) return null;
  const parsed = new Date(`${value}:00+09:00`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.getTime();
}
