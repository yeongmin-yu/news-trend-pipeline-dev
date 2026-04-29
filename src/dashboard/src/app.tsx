import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type ArticleItem,
  type DashboardOverviewResponse,
  type FiltersResponse,
  type RelatedKeyword,
  type RangeId,
  type SourceId,
  type ThemeDistributionResponse,
  type TrendBucketId,
  type TrendResponse,
  type OverviewRawPayload,
  type TrendRawPayload
} from "./data";
import { SpikeHeatmap, TopKeywords, TrendLine } from "./charts";
import { DictionaryApiModal } from "./dictionary-modal";
import { QueryKeywordModal } from "./query-keyword-modal";
import { EmptyState, fmtNum, fmtPct, Icon, LoadingState } from "./ui";
import { useAsyncData, type AsyncState } from "./hooks";
import {
  AUTO_REFRESH_INTERVAL_MS,
  DASHBOARD_WINDOW_COMMIT_DELAY_MS,
  DEFAULT_FILTERS,
  EMPTY_KEYWORD_LIST,
  EMPTY_THEME_DISTRIBUTION,
  MAX_POINTS_PER_QUERY,
  MAX_TREND_WINDOW_MS,
  MIN_TREND_WINDOW_MS,
  TREND_BUCKET_OPTIONS,
} from "./constants";
import {
  clampTrendWindow,
  deriveOverviewFromCache,
  expandOverviewFetchWindow,
  expandTrendFetchWindow,
  fromDateTimeLocalInput,
  fmtKST,
  getTopKeywordBarColor,
  getTrendbucketMinutes,
  isSpikeKeyword,
  pickAutoTrendBucket,
  pickOverviewBucket,
  rankKeywords,
} from "./utils";
import { KpiCard } from "./KpiCard";
import { DashboardHeader } from "./DashboardHeader";
import { DashboardSubbar } from "./DashboardSubbar";
import { DashboardSidebar } from "./DashboardSidebar";
import { DashboardRightRail } from "./DashboardRightRail";

const ENABLE_TREND_PREFETCH = false;
const MAX_TREND_CELLS_PER_REQUEST = 12000;
const MAX_TREND_BUCKETS_PER_REQUEST = 720;

function getTrendRequestStats(
  startMs: number,
  endMs: number,
  bucketId: TrendBucketId,
  nowMs: number,
  keywordCount: number,
) {
  const bucketMs = getTrendbucketMinutes(bucketId) * 60_000;
  const fetchWindow = expandTrendFetchWindow(startMs, endMs, bucketId, nowMs);
  const visiblePoints = Math.max(1, Math.ceil((endMs - startMs) / bucketMs));
  const fetchBuckets = Math.max(1, Math.ceil((fetchWindow.endMs - fetchWindow.startMs) / bucketMs));
  return {
    visiblePoints,
    fetchBuckets,
    estimatedCells: fetchBuckets * Math.max(1, keywordCount),
  };
}

export default function App() {

  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [source, setSource] = useState<SourceId>("all");
  const [rangePreset, setRangePreset] = useState<RangeId | null>("1h");
  const [domain, setDomain] = useState("ai_tech");
  const [search, setSearch] = useState("");
  const [searchFocus, setSearchFocus] = useState(false);
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null);
  const [checkedTrendKeywords, setCheckedTrendKeywords] = useState<string[]>([]);
  const [selectedBucket, setSelectedBucket] = useState<number | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<string | null>(null);
  const [articleSort, setArticleSort] = useState<"latest" | "relevance">("latest");
  const [spikeSort, setSpikeSort] = useState<"score" | "growth">("score");
  const [relatedView, setRelatedView] = useState<"network" | "bar">("network");
  const [topSort, setTopSort] = useState<"mentions" | "growth">("mentions");
  const [topLimit, setTopLimit] = useState(20);
  const [trendFetchLimit, setTrendFetchLimit] = useState(20);
  const [trendBucketMode, setTrendBucketMode] = useState<"auto" | TrendBucketId>("auto");
  const [trendWindow, setTrendWindow] = useState(() => {
    const end = Date.now();
    return { startMs: end - 60 * 60 * 1000, endMs: end };
  });
  const [spikeMinMentions, setSpikeMinMentions] = useState(5);
  const [spikeMinGrowth, setSpikeMinGrowth] = useState(0.4);
  const [hiddenSeries, setHiddenSeries] = useState<string[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [dataRefreshNonce, setDataRefreshNonce] = useState(0);
  const [stopwordMessage, setStopwordMessage] = useState<string | null>(null);
  const [dictionaryOpen, setDictionaryOpen] = useState(false);
  const [queryKeywordOpen, setQueryKeywordOpen] = useState(false);
  const [watchlist, setWatchlist] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("ntp_watchlist") ?? "[]");
    } catch {
      return [];
    }
  });
  const searchRef = useRef<HTMLDivElement>(null);
  const lastWheelZoomAtRef = useRef(0);
  const trendWindowChangeReasonRef = useRef<
  "init" | "wheel" | "pan" | "date-input" | "preset" | "bucket" | "auto-refresh"
>("init");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("ntp_watchlist", JSON.stringify(watchlist));
  }, [watchlist]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!stopwordMessage) return;
    const id = window.setTimeout(() => setStopwordMessage(null), 3200);
    return () => window.clearTimeout(id);
  }, [stopwordMessage]);

  const filters = useAsyncData(() => api.filters(), []);
  const activeFilters = filters.data ?? DEFAULT_FILTERS;
  const activeRange = useMemo(
    () => activeFilters.ranges.find((r) => r.id === (rangePreset ?? "1h")) ?? DEFAULT_FILTERS.ranges[2],
    [activeFilters.ranges, rangePreset],
  );

  const [committedWindow, setCommittedWindow] = useState(trendWindow);
  const rangeParam = rangePreset ?? "1h";
  const trendDurationMs = trendWindow.endMs - trendWindow.startMs;
  const activeWindowLabel = rangePreset ? activeRange.label : "사용자 기간";
  const effectiveTrendBucket = useMemo<TrendBucketId>(() => {
    const preferred = trendBucketMode === "auto" ? pickAutoTrendBucket(trendDurationMs) : trendBucketMode;
    const preferredOption = TREND_BUCKET_OPTIONS.find((item) => item.id === preferred) ?? TREND_BUCKET_OPTIONS[1];
    const safeOption =
      TREND_BUCKET_OPTIONS.find((item) => {
        if (item.minutes < preferredOption.minutes) return false;
        const stats = getTrendRequestStats(
          trendWindow.startMs,
          trendWindow.endMs,
          item.id,
          Math.min(now, trendWindow.endMs),
          trendFetchLimit,
        );
        return (
          stats.visiblePoints <= MAX_POINTS_PER_QUERY &&
          stats.fetchBuckets <= MAX_TREND_BUCKETS_PER_REQUEST &&
          stats.estimatedCells <= MAX_TREND_CELLS_PER_REQUEST
        );
      }) ?? TREND_BUCKET_OPTIONS[TREND_BUCKET_OPTIONS.length - 1];
    return safeOption.id;
  }, [trendBucketMode, trendDurationMs, trendWindow.startMs, trendWindow.endMs, now, trendFetchLimit]);
  const committedStartIso = useMemo(() => new Date(committedWindow.startMs).toISOString(), [committedWindow.startMs]);
  const committedEndIso = useMemo(() => new Date(committedWindow.endMs).toISOString(), [committedWindow.endMs]);
  const autoRefreshTick = Math.floor(now / AUTO_REFRESH_INTERVAL_MS);
  const trendFetchClockMs = useMemo(() => {
    if (!autoRefresh) return trendWindow.endMs;
    const bucketMs = getTrendbucketMinutes(effectiveTrendBucket) * 60_000;
    return Math.min(now, Math.floor(now / bucketMs) * bucketMs);
  }, [autoRefresh, trendWindow.endMs, effectiveTrendBucket, now]);
  const overviewFetchClockMs = useMemo(
    () => (autoRefresh ? Math.min(now, autoRefreshTick * AUTO_REFRESH_INTERVAL_MS) : trendWindow.endMs),
    [autoRefresh, now, autoRefreshTick, trendWindow.endMs],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCommittedWindow((prev) =>
        prev.startMs === trendWindow.startMs && prev.endMs === trendWindow.endMs ? prev : trendWindow,
      );
    }, DASHBOARD_WINDOW_COMMIT_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [trendWindow.startMs, trendWindow.endMs, effectiveTrendBucket]);

  const [overviewFetchWindow, setOverviewFetchWindow] = useState(() =>
    expandOverviewFetchWindow(trendWindow.startMs, trendWindow.endMs, trendWindow.endMs),
  );

  const overviewFetchStartIso = useMemo(
    () => new Date(overviewFetchWindow.startMs).toISOString(),
    [overviewFetchWindow.startMs],
  );
  const overviewFetchEndIso = useMemo(
    () => new Date(overviewFetchWindow.endMs).toISOString(),
    [overviewFetchWindow.endMs],
  );
  const overviewBucket = useMemo(
    () => pickOverviewBucket(overviewFetchWindow.endMs - overviewFetchWindow.startMs),
    [overviewFetchWindow.startMs, overviewFetchWindow.endMs],
  );
  const overviewRequestKey = useMemo(
    () =>
      [source, domain, rangeParam, overviewBucket, search, overviewFetchWindow.startMs, overviewFetchWindow.endMs, dataRefreshNonce].join("::"),
    [source, domain, rangeParam, overviewBucket, search, overviewFetchWindow.startMs, overviewFetchWindow.endMs, dataRefreshNonce],
  );
const overviewContextKey = useMemo(
  () => [source, domain, rangeParam, search].join("::"),
  [source, domain, rangeParam, search],
);

/* FetchWindow Effect*/ 
  useEffect(() => {
    const durationMs = Math.max(MIN_TREND_WINDOW_MS, trendWindow.endMs - trendWindow.startMs);

    // 실제 cache 밖으로 나갔다고 볼 허용치
    const outsideSlackMs = Math.max(60_000, Math.floor(durationMs * 0.02));

    // cache 안쪽에서 이 정도만 남으면 미리 확장
    const prefetchEdgeSlackMs = Math.max(5 * 60_000, Math.floor(durationMs * 0.12));

    setOverviewFetchWindow((prev) => {
      const leftOverflowMs = prev.startMs - trendWindow.startMs;
      const rightOverflowMs = trendWindow.endMs - prev.endMs;

      const outsideCache =
        leftOverflowMs > outsideSlackMs ||
        rightOverflowMs > outsideSlackMs;

      const strictlyInsideCache =
        leftOverflowMs <= 0 &&
        rightOverflowMs <= 0;

      const leftBufferMs = trendWindow.startMs - prev.startMs;
      const rightBufferMs = prev.endMs - trendWindow.endMs;

      const nearCacheEdge =
        strictlyInsideCache &&
        (leftBufferMs <= prefetchEdgeSlackMs || rightBufferMs <= prefetchEdgeSlackMs);

       console.debug("[overview] fetch-window decision", {
          durationMs,
          prefetchEdgeSlackMs,
          outsideSlackMs,
          leftOverflowMs,
          rightOverflowMs,
          leftBufferMs,
          rightBufferMs,
          strictlyInsideCache,
          outsideCache,
          nearCacheEdge,
        });

      if (!outsideCache && !nearCacheEdge) return prev;

      const expanded = expandOverviewFetchWindow(
        trendWindow.startMs,
        trendWindow.endMs,
        overviewFetchClockMs,
      );

      return {
        startMs: Math.min(prev.startMs, expanded.startMs),
        endMs: Math.max(prev.endMs, expanded.endMs),
      };
    });
  }, [trendWindow.startMs, trendWindow.endMs, overviewFetchClockMs]);


  const overviewIdentityKey = overviewRequestKey;
  const overviewCacheRef = useRef<
    Map<string, { data: DashboardOverviewResponse; identity: string; fetchStartMs: number; fetchEndMs: number }>
  >(new Map());
const overviewInFlightRef = useRef<Map<string, Promise<OverviewRawPayload>>>(new Map());

const [overviewRaw, setOverviewRaw] = useState<AsyncState<OverviewRawPayload>>({
  data: null,
  loading: true,
  error: null,
});

  useEffect(() => {
    let alive = true;

    const exact = overviewCacheRef.current.get(overviewRequestKey);
    if (exact) {
       console.debug("[overview] exact cache hit", {
      overviewRequestKey,
      overviewBucket,
      fetchWindow: overviewFetchWindow,
    });
     setOverviewRaw({
        data: {
          data: exact.data,
          identity: overviewRequestKey,
          contextKey: overviewContextKey,
        },
        loading: false,
        error: null,
      });
      return () => { alive = false; };
    }

    const keyPrefix = [source, domain, rangeParam, overviewBucket, search].join("::");
    for (const [key, entry] of overviewCacheRef.current) {
      if (
        key.startsWith(keyPrefix + "::") &&
        entry.fetchStartMs <= overviewFetchWindow.startMs &&
        entry.fetchEndMs >= overviewFetchWindow.endMs
      ) {
        console.debug("[overview] coverage cache hit", {
      overviewRequestKey,
      coveredBy: key,
      overviewBucket,
      requestedWindow: overviewFetchWindow,
      cachedWindow: {
        startMs: entry.fetchStartMs,
        endMs: entry.fetchEndMs,
      },
    });
        overviewCacheRef.current.set(overviewRequestKey, { ...entry, identity: overviewRequestKey });
       setOverviewRaw({
  data: {
    data: entry.data,
    identity: overviewRequestKey,
    contextKey: overviewContextKey,
  },
  loading: false,
  error: null,
});
        return () => { alive = false; };
      }
    }

    setOverviewRaw((prev) => ({
      data: prev.data,
      loading: prev.data == null,
      error: null,
    }));

    const existingRequest = overviewInFlightRef.current.get(overviewRequestKey);
    if (existingRequest) {
      console.debug("[overview] regular in-flight hit", {
      overviewRequestKey,
      overviewBucket,
      fetchWindow: overviewFetchWindow,
    });
      existingRequest
        .then((data) => {
          if (!alive) return;
          setOverviewRaw({ data, loading: false, error: null });
        })
        .catch((error: unknown) => {
          if (!alive) return;
          setOverviewRaw((prev) => ({
            data: prev.data,
            loading: false,
            error: error instanceof Error ? error.message : "알 수 없는 오류",
          }));
        });

      return () => {
        alive = false;
      };
    }

    const request = api
      .overviewWindow(
        source, domain, rangeParam,
        overviewFetchStartIso, overviewFetchEndIso,
        overviewBucket, search, 30,
        overviewFetchStartIso, overviewFetchEndIso,
        
      )
      .then((data) => {
        console.debug("[overview] regular fetch", {
    overviewRequestKey,
    overviewBucket,
    fetchWindow: overviewFetchWindow,
    fetchStartIso: overviewFetchStartIso,
    fetchEndIso: overviewFetchEndIso,
    trendWindow,
  });
        overviewCacheRef.current.set(overviewRequestKey, {
          data,
          identity: overviewRequestKey,
          fetchStartMs: overviewFetchWindow.startMs,
          fetchEndMs: overviewFetchWindow.endMs,
        });
       return { data, identity: overviewRequestKey, contextKey: overviewContextKey };
      })
      .finally(() => {
        overviewInFlightRef.current.delete(overviewRequestKey);
      });

    overviewInFlightRef.current.set(overviewRequestKey, request);

    request
      .then((data) => {
        if (!alive) return;
        setOverviewRaw({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setOverviewRaw((prev) => ({
          data: prev.data,
          loading: false,
          error: error instanceof Error ? error.message : "알 수 없는 오류",
        }));
      });

    return () => { alive = false; };
  }, [
    source, domain, rangeParam, overviewBucket, search,
    overviewFetchWindow.startMs, overviewFetchWindow.endMs,
    overviewRequestKey,
  ]);

  const overviewHasDifferentContext =
  overviewRaw.data != null &&
  overviewRaw.data.contextKey !== overviewContextKey;

  const overviewHasDifferentRequest =
    overviewRaw.data != null &&
    overviewRaw.data.identity !== overviewIdentityKey;

  const overview: AsyncState<DashboardOverviewResponse> = {
    // 도메인/source/search/bucket 등 컨텍스트가 바뀐 경우만 이전 데이터 숨김
    // chart zoom/pan으로 requestKey만 바뀐 경우는 이전 데이터를 유지
    data: overviewHasDifferentContext ? null : (overviewRaw.data?.data ?? null),
    loading: overviewRaw.loading || overviewHasDifferentRequest,
    error: overviewRaw.error,
  };
  const derivedOverview = useMemo(
    () => deriveOverviewFromCache(source, overview.data?.cache, committedWindow.startMs, committedWindow.endMs, 30, now),
    [source, overview.data?.cache, committedWindow.startMs, committedWindow.endMs, now],
  );
  const activeOverview = derivedOverview ?? overview.data;
  const system = useAsyncData(() => api.system(), []);
  const kpis: AsyncState<DashboardOverviewResponse["kpis"]> = {
    data: activeOverview?.kpis ?? null,
    loading: overview.loading,
    error: overview.error,
  };
  const keywords: AsyncState<DashboardOverviewResponse["keywords"]> = {
    data: activeOverview?.keywords ?? null,
    loading: overview.loading,
    error: overview.error,
  };
  const spikes: AsyncState<DashboardOverviewResponse["spikes"]> = {
    data: activeOverview?.spikes ?? null,
    loading: overview.loading,
    error: overview.error,
  };
  const rawKeywords = useMemo(() => activeOverview?.keywords ?? EMPTY_KEYWORD_LIST, [activeOverview]);
  const rankedKeywords = useMemo(() => rankKeywords(rawKeywords, topSort), [rawKeywords, topSort]);
  const displayKeywords = useMemo(
    () =>
      rawKeywords.map((item) => ({
        ...item,
        spike: isSpikeKeyword(item, spikeMinMentions, spikeMinGrowth),
      })),
    [rawKeywords, spikeMinMentions, spikeMinGrowth],
  );
  const displayKeywordLookup = useMemo(
    () => new Map(displayKeywords.map((item) => [item.keyword, item])),
    [displayKeywords],
  );

  useEffect(() => {
    if (!displayKeywords.length) return;
    if (!selectedKeyword) {
      setSelectedKeyword(displayKeywords[0].keyword);
      return;
    }
    if (displayKeywords.some((item) => item.keyword === selectedKeyword)) return;
    if (watchlist.includes(selectedKeyword)) return;
    setSelectedKeyword(displayKeywords[0].keyword);
  }, [selectedKeyword, displayKeywords, watchlist]);

  const keywordSelectionContextKey = useMemo(
    () => [source, domain, rangeParam, search].join("::"),
    [source, domain, rangeParam, search],
  );
  const checkedTrendInitKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!rankedKeywords.length) return;
    const contextChanged = checkedTrendInitKeyRef.current !== keywordSelectionContextKey;
    if (!contextChanged) return;
    checkedTrendInitKeyRef.current = keywordSelectionContextKey;
    setCheckedTrendKeywords(rankedKeywords.slice(0, 5).map((item) => item.keyword));
  }, [rankedKeywords, keywordSelectionContextKey]);

  useEffect(() => {
    setTrendFetchLimit(topLimit);
  }, [domain, source, rangeParam, topSort, search, topLimit]);
  useEffect(() => {
    setTrendFetchLimit((prev) => Math.max(prev, topLimit));
  }, [topLimit]);

  useEffect(() => {
    if (!autoRefresh || rangePreset == null) return;
    const selected = activeFilters.ranges.find((item) => item.id === rangePreset) ?? DEFAULT_FILTERS.ranges[2];
    const endMs = Math.min(now, autoRefreshTick * AUTO_REFRESH_INTERVAL_MS);
    const startMs = endMs - selected.bucketMin * selected.buckets * 60_000;
    setTrendWindow((prev) => {
      if (prev.startMs === startMs && prev.endMs === endMs) {
        return prev;
      }

      trendWindowChangeReasonRef.current = "auto-refresh";
      return { startMs, endMs };
    });
  }, [autoRefresh, autoRefreshTick, activeFilters.ranges, now, rangePreset]);

  const preloadedTrendKeywords = useMemo(
    () => rankedKeywords.slice(0, trendFetchLimit).map((item) => item.keyword),
    [rankedKeywords, trendFetchLimit],
  );
  const trendCacheRef = useRef<Map<string, TrendResponse>>(new Map());
  const trendInFlightRef = useRef<Map<string, Promise<TrendResponse>>>(new Map());
 

  const [trendRaw, setTrendRaw] = useState<AsyncState<TrendRawPayload>>({
    data: null,
    loading: true,
    error: null,
  });
  const [trendFetchWindow, setTrendFetchWindow] = useState(() =>
    expandTrendFetchWindow(trendWindow.startMs, trendWindow.endMs, effectiveTrendBucket, Date.now()),
  );
  const previousEffectiveTrendBucketRef = useRef(effectiveTrendBucket);

  useEffect(() => {
  const desired = expandTrendFetchWindow(
    trendWindow.startMs,
    trendWindow.endMs,
    effectiveTrendBucket,
    trendFetchClockMs,
  );

  const bucketMs = getTrendbucketMinutes(effectiveTrendBucket) * 60_000;
  const durationMs = Math.max(MIN_TREND_WINDOW_MS, trendWindow.endMs - trendWindow.startMs);
  const visibleBuckets = Math.max(1, Math.ceil(durationMs / bucketMs));
  const bucketChanged = previousEffectiveTrendBucketRef.current !== effectiveTrendBucket;
  previousEffectiveTrendBucketRef.current = effectiveTrendBucket;

  const edgeSlackMs = bucketMs * Math.max(3, Math.min(10, Math.ceil(visibleBuckets * 0.2)));
  const outsideSlackMs = Math.max(bucketMs, Math.floor(durationMs * 0.02));

  setTrendFetchWindow((prev) => {
    const prevBuckets = Math.ceil((prev.endMs - prev.startMs) / bucketMs);
    if (bucketChanged || prevBuckets > MAX_TREND_BUCKETS_PER_REQUEST) return desired;

    const leftOverflowMs = prev.startMs - trendWindow.startMs;
    const rightOverflowMs = trendWindow.endMs - prev.endMs;

    const outsideCache =
      leftOverflowMs > outsideSlackMs ||
      rightOverflowMs > outsideSlackMs;

    const strictlyInsideCache =
      leftOverflowMs <= 0 &&
      rightOverflowMs <= 0;

    const leftBufferMs = trendWindow.startMs - prev.startMs;
    const rightBufferMs = prev.endMs - trendWindow.endMs;

    const nearCacheEdge =
      strictlyInsideCache &&
      (leftBufferMs <= edgeSlackMs || rightBufferMs <= edgeSlackMs);

    if (!outsideCache && !nearCacheEdge) return prev;

    return {
      startMs: Math.min(prev.startMs, desired.startMs),
      endMs: Math.max(prev.endMs, desired.endMs),
    };
  });
}, [trendWindow.startMs, trendWindow.endMs, effectiveTrendBucket, trendFetchClockMs]);

  const preloadedTrendKeywordKey = useMemo(
    () => preloadedTrendKeywords.join("|"),
    [preloadedTrendKeywords],
  );
  const trendBucketOptionState = useMemo(
    () =>
      Object.fromEntries(
        TREND_BUCKET_OPTIONS.map((option) => {
          const stats = getTrendRequestStats(
            trendWindow.startMs,
            trendWindow.endMs,
            option.id,
            trendFetchClockMs,
            preloadedTrendKeywords.length || trendFetchLimit,
          );
          const disabled =
            stats.visiblePoints > MAX_POINTS_PER_QUERY ||
            stats.fetchBuckets > MAX_TREND_BUCKETS_PER_REQUEST ||
            stats.estimatedCells > MAX_TREND_CELLS_PER_REQUEST;

          let reason: string | null = null;
          if (stats.fetchBuckets > MAX_TREND_BUCKETS_PER_REQUEST) {
            reason = `현재 기간이 ${option.label} 최대 조회 범위를 넘습니다. 기간을 줄이거나 더 큰 봉을 선택하세요.`;
          } else if (stats.estimatedCells > MAX_TREND_CELLS_PER_REQUEST) {
            reason = `현재 비교 키워드 수에서는 ${option.label} 요청 범위가 너무 큽니다. 기간을 줄이거나 비교 대상을 줄여주세요.`;
          } else if (stats.visiblePoints > MAX_POINTS_PER_QUERY) {
            reason = `현재 기간에서는 ${option.label} 포인트 수가 너무 많습니다.`;
          }

          return [option.id, { disabled, reason }];
        }),
      ) as Record<TrendBucketId, { disabled: boolean; reason: string | null }>,
    [trendWindow.startMs, trendWindow.endMs, trendFetchClockMs, preloadedTrendKeywords.length, trendFetchLimit],
  );

  // Always-current snapshot for zoom-out prefetch (avoids stale closure in setTimeout)
  const zoomOutPrefetchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevZoomDurationForPrefetchRef = useRef(trendDurationMs);
  const overviewPrefetchInFlightRef = useRef<Set<string>>(new Set());
  const trendPrefetchInFlightRef = useRef<Set<string>>(new Set());
  const prefetchLatestRef = useRef({
    source, domain, rangeParam, search,
    effectiveTrendBucket, preloadedTrendKeywords, preloadedTrendKeywordKey,
    overviewFetchClockMs, overviewRequestKey, trendWindow,
  });
  prefetchLatestRef.current = {
    source, domain, rangeParam, search,
    effectiveTrendBucket, preloadedTrendKeywords, preloadedTrendKeywordKey,
    overviewFetchClockMs, overviewRequestKey, trendWindow,
  };

  const trendRequestKey = useMemo(
    () =>
      [source, domain, trendFetchWindow.startMs, trendFetchWindow.endMs, effectiveTrendBucket, preloadedTrendKeywordKey, dataRefreshNonce].join("::"),
    [source, domain, trendFetchWindow.startMs, trendFetchWindow.endMs, effectiveTrendBucket, preloadedTrendKeywordKey, dataRefreshNonce],
  );
  const trendContextKey = useMemo(
  () => [
    source,
    domain,
    effectiveTrendBucket,
    preloadedTrendKeywordKey,
  ].join("::"),
  [source, domain, effectiveTrendBucket, preloadedTrendKeywordKey],
);
const trendHasDifferentContext =
  trendRaw.data != null &&
  trendRaw.data.contextKey !== trendContextKey;

const trendHasDifferentRequest =
  trendRaw.data != null &&
  trendRaw.data.identity !== trendRequestKey;

const trend: AsyncState<TrendResponse> = {
  data: trendHasDifferentContext ? null : (trendRaw.data?.data ?? null),
  loading: trendRaw.loading || trendHasDifferentRequest,
  error: trendRaw.error,
};
useEffect(() => {
  if (!preloadedTrendKeywords.length) {
    setTrendRaw({
      data: {
        data: { series: [], range: DEFAULT_FILTERS.ranges[2] } as TrendResponse,
        identity: trendRequestKey,
        contextKey: trendContextKey,
      },
      loading: false,
      error: null,
    });
    return;
  }

  const cached = trendCacheRef.current.get(trendRequestKey);
  if (cached) {
    setTrendRaw({
      data: {
        data: cached,
        identity: trendRequestKey,
        contextKey: trendContextKey,
      },
      loading: false,
      error: null,
    });
    return;
  }

  const bucketMs = getTrendbucketMinutes(effectiveTrendBucket) * 60_000;
  const points = Math.ceil((trendFetchWindow.endMs - trendFetchWindow.startMs) / bucketMs);
  const estimatedCells = points * preloadedTrendKeywords.length;
  const isOversizedTrendRequest =
    points > MAX_TREND_BUCKETS_PER_REQUEST ||
    estimatedCells > MAX_TREND_CELLS_PER_REQUEST;
  const oversizedTrendMessage =
    points > MAX_TREND_BUCKETS_PER_REQUEST
      ? `선택한 기간이 ${effectiveTrendBucket} 최대 조회 범위를 넘었습니다. 기간을 줄이거나 더 큰 봉으로 바꿔주세요.`
      : `비교 키워드가 많아 ${effectiveTrendBucket} 요청 범위가 너무 큽니다. 기간을 줄이거나 비교 대상을 줄여주세요.`;

  if (isOversizedTrendRequest) {
    console.warn("[trend] skip oversized request", {
      estimatedCells,
      points,
      keywordCount: preloadedTrendKeywords.length,
      effectiveTrendBucket,
      reason: trendWindowChangeReasonRef.current,
    });

    setTrendRaw({
      data: null,
      loading: false,
      error: oversizedTrendMessage,
    });

    return;
  }

  let alive = true;

  setTrendRaw((prev) => {
    const canKeepPrevious =
      prev.data != null &&
      prev.data.contextKey === trendContextKey;

    return {
      data: canKeepPrevious ? prev.data : null,
      loading: true,
      error: null,
    };
  });

  const existingTrendRequest = trendInFlightRef.current.get(trendRequestKey);
  if (existingTrendRequest) {
    existingTrendRequest
      .then((data) => {
        if (!alive) return;
        setTrendRaw({
          data: {
            data,
            identity: trendRequestKey,
            contextKey: trendContextKey,
          },
          loading: false,
          error: null,
        });
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setTrendRaw((prev) => {
          const canKeepPrevious =
            prev.data != null &&
            prev.data.contextKey === trendContextKey;

          return {
            data: canKeepPrevious ? prev.data : null,
            loading: false,
            error: error instanceof Error ? error.message : "알 수 없는 오류",
          };
        });
      });

    return () => {
      alive = false;
    };
  }

  const request = api
    .trendWindow(
      source,
      domain,
      new Date(trendFetchWindow.startMs).toISOString(),
      new Date(trendFetchWindow.endMs).toISOString(),
      effectiveTrendBucket,
      preloadedTrendKeywords,
    )
    .then((data) => {
      trendCacheRef.current.set(trendRequestKey, data);
      return data;
    })
    .finally(() => {
      trendInFlightRef.current.delete(trendRequestKey);
    });

  trendInFlightRef.current.set(trendRequestKey, request);

  request
    .then((data) => {
      if (!alive) return;
      setTrendRaw({
        data: {
          data,
          identity: trendRequestKey,
          contextKey: trendContextKey,
        },
        loading: false,
        error: null,
      });
    })
    .catch((error: unknown) => {
      if (!alive) return;
      setTrendRaw((prev) => {
        const canKeepPrevious =
          prev.data != null &&
          prev.data.contextKey === trendContextKey;

        return {
          data: canKeepPrevious ? prev.data : null,
          loading: false,
          error: error instanceof Error ? error.message : "알 수 없는 오류",
        };
      });
    });

  return () => {
    alive = false;
  };
}, [
  source,
  domain,
  trendFetchWindow.startMs,
  trendFetchWindow.endMs,
  effectiveTrendBucket,
  preloadedTrendKeywordKey,
  trendRequestKey,
  trendContextKey,
]);

  const detailTrend = useAsyncData(
    () =>
      selectedKeyword
        ? api.trendWindow(source, domain, committedStartIso, committedEndIso, effectiveTrendBucket, [selectedKeyword])
        : Promise.resolve({ series: [], range: DEFAULT_FILTERS.ranges[2] } as TrendResponse),
    [source, domain, selectedKeyword, effectiveTrendBucket, committedStartIso, committedEndIso, dataRefreshNonce],
  );
  const related = useAsyncData(
    () =>
      selectedKeyword
        ? api.related(source, domain, rangeParam, selectedKeyword, committedStartIso, committedEndIso)
        : Promise.resolve([] as RelatedKeyword[]),
    [source, domain, rangeParam, selectedKeyword, committedStartIso, committedEndIso],
  );
  const themeDistribution = useAsyncData(
    () =>
      selectedKeyword
        ? api.themeDistribution(source, rangeParam, selectedKeyword, committedStartIso, committedEndIso)
        : Promise.resolve(EMPTY_THEME_DISTRIBUTION),
    [source, rangeParam, selectedKeyword, committedStartIso, committedEndIso],
  );
  const articles = useAsyncData(
    () =>
      selectedKeyword
        ? api.articles(source, domain, rangeParam, selectedKeyword, articleSort, committedStartIso, committedEndIso)
        : Promise.resolve([] as ArticleItem[]),
    [source, domain, rangeParam, selectedKeyword, articleSort, committedStartIso, committedEndIso],
  );

  const activeKeyword = useMemo(
    () => displayKeywords.find((k) => k.keyword === selectedKeyword) ?? displayKeywords[0] ?? null,
    [displayKeywords, selectedKeyword],
  );
  const activeKeywordSummary = useMemo(
    () => displayKeywordLookup.get(selectedKeyword ?? "") ?? activeKeyword,
    [displayKeywordLookup, selectedKeyword, activeKeyword],
  );
  const detailTrendSeries = useMemo(
    () => detailTrend.data?.series.find((s) => s.name === selectedKeyword) ?? detailTrend.data?.series[0] ?? null,
    [detailTrend.data, selectedKeyword],
  );
  const visibleTrendSeries = useMemo(
    () => (trend.data?.series ?? []).filter((s) => checkedTrendKeywords.includes(s.name)),
    [trend.data, checkedTrendKeywords],
  );
  const filteredSpikeEvents = useMemo(
    () =>
      (spikes.data?.events ?? []).filter(
        (event) => event.currentMentions >= spikeMinMentions && event.growth >= spikeMinGrowth,
      ),
    [spikes.data, spikeMinMentions, spikeMinGrowth],
  );
  const spikeHeatmapKeywords = useMemo(() => {
    const spikeKeywords = rankedKeywords
      .filter((item) => isSpikeKeyword(item, spikeMinMentions, spikeMinGrowth))
      .slice(0, 8)
      .map((item) => item.keyword);
    if (spikeKeywords.length) return spikeKeywords;
    return rankedKeywords.slice(0, 8).map((item) => item.keyword);
  }, [rankedKeywords, spikeMinMentions, spikeMinGrowth]);

  const spikeRows = useMemo(() => {
    const filteredEvents = filteredSpikeEvents.filter((e) => selectedBucket == null || e.bucket === selectedBucket);
    const eventKeywords = new Set(filteredEvents.map((e) => e.keyword));
    const rows =
      selectedBucket == null
        ? displayKeywords.filter((k) => k.spike)
        : displayKeywords.filter((k) => eventKeywords.has(k.keyword));
    return rows
      .slice()
      .sort((a, b) =>
        spikeSort === "growth" ? b.growth - a.growth : (b.eventScore ?? 0) - (a.eventScore ?? 0),
      )
      .slice(0, 12);
  }, [displayKeywords, filteredSpikeEvents, selectedBucket, spikeSort]);

  const themeBarItems = useMemo(() => {
    const items = themeDistribution.data?.items ?? [];
    if (!items.length) return [];
    const minShare = 0.02;
    const zeroCount = items.filter((item) => item.share <= 0).length;
    const reservedShare = Math.min(zeroCount * minShare, 0.24);
    const positiveItems = items.filter((item) => item.share > 0);
    const positiveTotal = positiveItems.reduce((sum, item) => sum + item.share, 0);
    if (positiveTotal <= 0) {
      const equalShare = 1 / items.length;
      return items.map((item) => ({ ...item, displayShare: equalShare }));
    }
    const scale = (1 - reservedShare) / positiveTotal;
    return items.map((item) => ({
      ...item,
      displayShare: item.share > 0 ? item.share * scale : minShare,
    }));
  }, [themeDistribution.data]);

  const typeaheadMatches = useMemo(() => {
    if (!search.trim()) return [];
    const q = search.trim().toLowerCase();
    return displayKeywords.filter((k) => k.keyword.toLowerCase().includes(q)).slice(0, 8);
  }, [search, displayKeywords]);

  function toggleSeries(name: string) {
    setHiddenSeries((h) => (h.includes(name) ? h.filter((x) => x !== name) : [...h, name]));
  }

  function toggleTrendKeyword(keyword: string) {
    setCheckedTrendKeywords((prev) => {
      if (prev.includes(keyword)) return prev.filter((item) => item !== keyword);
      if (prev.length >= 5) return prev;
      return [...prev, keyword];
    });
  }

  function setTrendWindowBound(kind: "start" | "end", value: string) {
    const parsed = fromDateTimeLocalInput(value);
    if (parsed == null) return;
      trendWindowChangeReasonRef.current = "date-input";
    setRangePreset(null);
    setTrendWindow((prev) => {
      const next =
        kind === "start" ? { startMs: parsed, endMs: prev.endMs } : { startMs: prev.startMs, endMs: parsed };
      const [startMs, endMs] = clampTrendWindow(next.startMs, next.endMs, now);
      return { startMs, endMs };
    });
  }

  function applyRangePreset(nextRange: RangeId) {
      trendWindowChangeReasonRef.current = "preset";
    setRangePreset(nextRange);
    const selected = activeFilters.ranges.find((item) => item.id === nextRange) ?? DEFAULT_FILTERS.ranges[2];
    const endMs = now;
    const startMs = endMs - selected.bucketMin * selected.buckets * 60_000;
    setTrendWindow({ startMs, endMs });
    setCommittedWindow({ startMs, endMs });
    setTrendBucketMode("auto");
    setSelectedBucket(null);
  }

  function handleTrendWheelZoom(direction: "in" | "out", anchorRatio: number) {
    const nowMs = Date.now();
    if (nowMs - lastWheelZoomAtRef.current < 120) return;
    lastWheelZoomAtRef.current = nowMs;

    trendWindowChangeReasonRef.current = "wheel";

    setRangePreset(null);
    setTrendWindow((prev) => {
      const currentDuration = prev.endMs - prev.startMs;
      const nextDuration = direction === "in" ? currentDuration * 0.8 : currentDuration * 1.25;
      const clampedDuration = Math.min(MAX_TREND_WINDOW_MS, Math.max(MIN_TREND_WINDOW_MS, nextDuration));
      const anchorTime = prev.startMs + currentDuration * anchorRatio;
      const nextStart = anchorTime - clampedDuration * anchorRatio;
      const nextEnd = anchorTime + clampedDuration * (1 - anchorRatio);
      const [startMs, endMs] = clampTrendWindow(nextStart, nextEnd, now);
      return { startMs, endMs };
    });
  }

  function handleTrendDragPan(deltaRatio: number) {
    if (!deltaRatio) return;
     trendWindowChangeReasonRef.current = "pan";
    setRangePreset(null);
    setTrendWindow((prev) => {
      const duration = prev.endMs - prev.startMs;
      const deltaMs = duration * deltaRatio;
      const [startMs, endMs] = clampTrendWindow(prev.startMs - deltaMs, prev.endMs - deltaMs, now);
      return { startMs, endMs };
    });
  }

  useEffect(() => {
    const visibleNames = new Set((trend.data?.series ?? []).map((s) => s.name));
    setHiddenSeries((prev) => prev.filter((name) => visibleNames.has(name)));
  }, [trend.data]);

  useEffect(() => {
    setSelectedBucket(null);
  }, [committedStartIso, committedEndIso, effectiveTrendBucket]);

  // Zoom-out prefetch: when the user zooms out, pre-load the next zoom level's data
  useEffect(() => {
    const previousDurationMs = prevZoomDurationForPrefetchRef.current;
  const isZoomingOut = trendDurationMs > previousDurationMs * 1.5 ;
  prevZoomDurationForPrefetchRef.current = trendDurationMs;
 console.debug("[overview] prefetch check", {
      previousDurationMs,
      trendDurationMs,
      ratio: trendDurationMs / previousDurationMs,
      isZoomingOut,
    });
    
    if (!isZoomingOut || trendDurationMs >= MAX_TREND_WINDOW_MS) return;
    if (zoomOutPrefetchTimerRef.current != null) clearTimeout(zoomOutPrefetchTimerRef.current);

    zoomOutPrefetchTimerRef.current = setTimeout(() => {
      zoomOutPrefetchTimerRef.current = null;
      const {
        source: s, domain: d, rangeParam: rp, search: q,
        effectiveTrendBucket: etb, preloadedTrendKeywords: ptk, preloadedTrendKeywordKey: ptkk,
        overviewFetchClockMs: ofcm, overviewRequestKey: currentOverviewRequestKey, trendWindow: tw,
      } = prefetchLatestRef.current;

      const duration = tw.endMs - tw.startMs;
      const nextDuration = Math.min(MAX_TREND_WINDOW_MS, duration * 1.25);
      if (nextDuration <= duration) return;

      const anchor = (tw.startMs + tw.endMs) / 2;
      const [ns, ne] = clampTrendWindow(anchor - nextDuration / 2, anchor + nextDuration / 2, ofcm);

      const ofw = expandOverviewFetchWindow(ns, ne, ofcm);
      const obucket = pickOverviewBucket(ofw.endMs - ofw.startMs);
      const okey = [s, d, rp, obucket, q, ofw.startMs, ofw.endMs].join("::");
      if (
        okey !== currentOverviewRequestKey &&
        !overviewCacheRef.current.has(okey) &&
        !overviewPrefetchInFlightRef.current.has(okey)
      ) {
         console.debug("[overview] prefetch fetch", {
    okey,
    currentOverviewRequestKey,
    obucket,
    prefetchWindow: ofw,
    nextVisibleWindow: { startMs: ns, endMs: ne },
  });
        overviewPrefetchInFlightRef.current.add(okey);
        const si = new Date(ofw.startMs).toISOString();
        const ei = new Date(ofw.endMs).toISOString();
        api.overviewWindow(s, d, rp, si, ei, obucket, q, 30, si, ei)
          .then((data) =>
            overviewCacheRef.current.set(okey, { data, identity: okey, fetchStartMs: ofw.startMs, fetchEndMs: ofw.endMs }),
          )
          .catch(() => {})
          .finally(() => {
            overviewPrefetchInFlightRef.current.delete(okey);
          });
      }
console.debug("[overview] prefetch overview decision", {
    okey,
    currentOverviewRequestKey,
    sameAsCurrent: okey === currentOverviewRequestKey,
    cacheHit: overviewCacheRef.current.has(okey),
    inFlight: overviewPrefetchInFlightRef.current.has(okey),
    obucket,
    prefetchWindow: ofw,
  });
      if (ENABLE_TREND_PREFETCH && ptk.length) {
        const tfw = expandTrendFetchWindow(ns, ne, etb, ofcm);
        const tkey = [s, d, tfw.startMs, tfw.endMs, etb, ptkk].join("::");
        if (
          !trendCacheRef.current.has(tkey) &&
          !trendPrefetchInFlightRef.current.has(tkey)
        ) {
          trendPrefetchInFlightRef.current.add(tkey);
          api.trendWindow(s, d, new Date(tfw.startMs).toISOString(), new Date(tfw.endMs).toISOString(), etb, ptk)
            .then((data) => trendCacheRef.current.set(tkey, data))
            .catch(() => {})
            .finally(() => {
              trendPrefetchInFlightRef.current.delete(tkey);
            });
        }
      }
    }, 800);

    return () => {
      if (zoomOutPrefetchTimerRef.current != null) {
        clearTimeout(zoomOutPrefetchTimerRef.current);
        zoomOutPrefetchTimerRef.current = null;
      }
    };
  }, [trendDurationMs]);

  function addToWatchlist(keyword: string) {
    if (!keyword.trim() || watchlist.includes(keyword)) return;
    setWatchlist((prev) => [keyword, ...prev]);
  }

  function removeFromWatchlist(keyword: string) {
    setWatchlist((prev) => prev.filter((k) => k !== keyword));
  }

  async function addCheckedKeywordsToStopwords() {
    await addKeywordsToStopwords(checkedTrendKeywords, { confirmBeforeRun: true });
  }

  async function addKeywordsToStopwords(keywordsToAdd: string[], { confirmBeforeRun }: { confirmBeforeRun: boolean }) {
    const normalizedKeywords = Array.from(new Set(keywordsToAdd.map((item) => item.trim()).filter(Boolean)));
    if (!normalizedKeywords.length) return;
    if (confirmBeforeRun) {
      const confirmed = window.confirm(
        `체크된 키워드 ${normalizedKeywords.length}개를 "${domain}" 도메인의 불용어로 등록할까요?\n\n${normalizedKeywords.join(", ")}`,
      );
      if (!confirmed) return;
    }
    try {
      for (const item of normalizedKeywords) {
        await api.createStopword(item, domain);
      }
      overviewCacheRef.current.clear();
      trendCacheRef.current.clear();
      overviewInFlightRef.current.clear();
      trendInFlightRef.current.clear();
      overviewPrefetchInFlightRef.current.clear();
      trendPrefetchInFlightRef.current.clear();
      setCheckedTrendKeywords((prev) => prev.filter((item) => !normalizedKeywords.includes(item)));
      setHiddenSeries((prev) => prev.filter((item) => !normalizedKeywords.includes(item)));
      setWatchlist((prev) => prev.filter((item) => !normalizedKeywords.includes(item)));
      setSelectedKeyword((prev) => (prev && normalizedKeywords.includes(prev) ? null : prev));
      setStopwordMessage(
        normalizedKeywords.length === 1
          ? `불용어 추가: ${normalizedKeywords[0]}`
          : `불용어 ${normalizedKeywords.length}개 추가 완료`,
      );
      setDataRefreshNonce((prev) => prev + 1);
    } catch (error) {
      setStopwordMessage(error instanceof Error ? error.message : "불용어 처리 실패");
    }
  }

  return (
    <div className="app" data-right-closed={selectedKeyword ? "false" : "true"}>
      <DashboardHeader
        now={now}
        autoRefresh={autoRefresh}
        setAutoRefresh={setAutoRefresh}
        theme={theme}
        setTheme={setTheme}
        setDictionaryOpen={setDictionaryOpen}
        setQueryKeywordOpen={setQueryKeywordOpen}
      />
      {stopwordMessage ? <div className="toast">{stopwordMessage}</div> : null}

      <DashboardSubbar
        activeFilters={activeFilters}
        source={source}
        setSource={setSource}
        domain={domain}
        setDomain={setDomain}
        trendWindow={trendWindow}
        setTrendWindowBound={setTrendWindowBound}
        rangePreset={rangePreset}
        applyRangePreset={applyRangePreset}
        search={search}
        setSearch={setSearch}
        searchFocus={searchFocus}
        setSearchFocus={setSearchFocus}
        typeaheadMatches={typeaheadMatches}
        setSelectedKeyword={setSelectedKeyword}
        searchRef={searchRef}
      />

      <DashboardSidebar
        activeFilters={activeFilters}
        domain={domain}
        setDomain={setDomain}
        watchlist={watchlist}
        selectedKeyword={selectedKeyword}
        setSelectedKeyword={setSelectedKeyword}
        displayKeywordLookup={displayKeywordLookup}
        addToWatchlist={addToWatchlist}
        removeFromWatchlist={removeFromWatchlist}
        spikeMinMentions={spikeMinMentions}
        setSpikeMinMentions={setSpikeMinMentions}
        spikeMinGrowth={spikeMinGrowth}
        setSpikeMinGrowth={setSpikeMinGrowth}
        system={system}
      />

      {/* Main */}
      <div className="main">
        {/* KPI row */}
        <div className="grid row-kpi">
          <KpiCard
            label="총 기사 수"
            value={fmtNum(kpis.data?.totalArticles ?? 0)}
            delta={fmtPct(kpis.data?.growth ?? 0)}
            tone={(kpis.data?.growth ?? 0) >= 0 ? "up" : "down"}
            sub="현재 선택 구간 기준"
          />
          <KpiCard
            label="고유 키워드"
            value={fmtNum(kpis.data?.uniqueKeywords ?? 0)}
            delta="중복 제거"
            tone="info"
            sub="keyword_trends 기준"
          />
          <KpiCard
            label="급상승 키워드"
            value={String(displayKeywords.filter((item) => item.spike).length)}
            delta="증가율 기반"
            tone="spike"
            sub="트렌드 델타 기반"
          />
          <KpiCard
            label="마지막 업데이트"
            value={kpis.data?.lastUpdateRelative ?? "-"}
            delta={autoRefresh ? "Auto 5m" : "Manual"}
            tone={autoRefresh ? "info" : "muted"}
            sub={kpis.data?.lastUpdateAbsolute ?? "로딩 중"}
          />
          <KpiCard
            label="데이터 지원"
            value={String(activeFilters.domains.filter((d) => d.available).length)}
            delta="스키마"
            tone="warn"
            sub="추가 도메인은 추후 지원"
          />
        </div>

        {/* Row top: keywords + trend */}
        <div className="grid row-top">
          {keywords.loading ? (
            <div className="panel">
              <LoadingState label="키워드 순위를 불러오는 중..." />
            </div>
          ) : keywords.error ? (
            <div className="panel">
              <EmptyState title="키워드 로드 실패" body={keywords.error} />
            </div>
          ) : (
            <TopKeywords
              keywords={displayKeywords}
              selected={selectedKeyword}
              onSelect={setSelectedKeyword}
              checkedKeywords={checkedTrendKeywords}
              onToggleCheck={toggleTrendKeyword}
              barColor={getTopKeywordBarColor(domain)}
              limit={topLimit}
              sortBy={topSort}
              onLimitChange={setTopLimit}
              onSortChange={setTopSort}
              onAddCheckedStopwords={addCheckedKeywordsToStopwords}
            />
          )}

          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">
                <Icon.TrendUp size={12} />
                키워드 트렌드
                <span className="tag mono">
                  {fmtKST(trendWindow.startMs)} ~ {fmtKST(trendWindow.endMs)}
                </span>
                <span className="tag mono">{effectiveTrendBucket}</span>
              </div>
              <div className="panel-tools">
                {trend.error && trend.data ? (
                  <span className="tag" style={{ color: "var(--warn)" }}>
                    갱신 실패 · 기존 데이터 표시 중
                  </span>
                ) : null}
                {selectedBucket != null && (
                  <button className="panel-tool" onClick={() => setSelectedBucket(null)}>
                    clear
                  </button>
                )}
              </div>
            </div>
            <div className="panel-body">
              <div className="trend-toolbar">
                <div className="seg">
                  <button
                    className={trendBucketMode === "auto" ? "is-active" : ""}
                    onClick={() => {
                      trendWindowChangeReasonRef.current = "bucket";
                      setTrendBucketMode("auto");
                    }}
                  >
                    자동
                  </button>
                  {TREND_BUCKET_OPTIONS.map((option) => {
                    const disabled =
                      Math.ceil(trendDurationMs / (option.minutes * 60_000)) > MAX_POINTS_PER_QUERY ||
                      trendBucketOptionState[option.id].disabled;
                    return (
                       <button
                          key={option.id}
                          className={trendBucketMode === option.id ? "is-active" : ""}
                          onClick={() => {
                            trendWindowChangeReasonRef.current = "bucket";
                            setTrendBucketMode(option.id);
                          }}
                          disabled={disabled}
                          title={disabled ? "현재 기간에서는 포인트 수가 너무 많습니다." : option.label}
                        >
                          {option.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              {trend.loading && !trend.data ? (
                  <LoadingState label="시계열 데이터를 불러오는 중..." />
                ) : trend.error && !trend.data ? (
                  <EmptyState title="트렌드 로드 실패" body={trend.error} />
                ) : !checkedTrendKeywords.length ? (
                  <EmptyState title="선택된 키워드 없음" body="상위 키워드 목록의 체크박스로 비교 대상을 선택하세요." />
                ) : (
                  <>
                    {/* {trend.loading && trend.data ? (
                      <div className="chart-inline-status">
                        시계열 데이터 갱신 중...
                      </div>
                    ) : null} */}

                    <TrendLine
                      series={visibleTrendSeries}
                      bucketMin={trend.data?.range.bucketMin ?? activeRange.bucketMin}
                      viewStartMs={trendWindow.startMs}
                      viewEndMs={trendWindow.endMs}
                      hidden={hiddenSeries}
                      onToggle={toggleSeries}
                      selectedBucket={selectedBucket}
                      onPointClick={setSelectedBucket}
                      onWheelZoom={handleTrendWheelZoom}
                      onDragPan={handleTrendDragPan}
                    />
                  </>
                )}
            </div>
          </div>
        </div>

        {/* Row mid: spike heatmap + spike table */}
        <div className="grid row-mid">
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">
                <Icon.Flame size={12} />
                급상승 키워드 타임라인
                <span className="tag mono">히트맵 · 강도</span>
              </div>
              <div className="panel-tools">
                {selectedBucket != null && (
                  <button className="panel-tool" onClick={() => setSelectedBucket(null)}>
                    clear selection
                  </button>
                )}
              </div>
            </div>
            <div className="panel-body scroll" style={{ padding: "8px 12px" }}>
              {spikes.loading ? (
                <LoadingState label="급상승 이벤트를 계산하는 중..." />
              ) : (
                <SpikeHeatmap
                  keywords={spikeHeatmapKeywords}
                  events={filteredSpikeEvents}
                  buckets={spikes.data?.range.buckets ?? activeRange.buckets}
                  bucketMin={spikes.data?.range.bucketMin ?? activeRange.bucketMin}
                  selectedBucket={selectedBucket}
                  onSelectBucket={setSelectedBucket}
                  selectedKeyword={selectedKeyword}
                  onSelectKeyword={setSelectedKeyword}
                  nowMs={now}
                />
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">
                <Icon.Flame size={12} />
                급상승 목록
                {selectedBucket != null && (
                  <span className="tag" style={{ color: "var(--accent)" }}>
                    bucket {selectedBucket + 1}
                  </span>
                )}
              </div>
              <div className="panel-tools">
                <div className="seg">
                  <button
                    className={spikeSort === "score" ? "is-active" : ""}
                    onClick={() => setSpikeSort("score")}
                  >
                    이벤트 점수
                  </button>
                  <button
                    className={spikeSort === "growth" ? "is-active" : ""}
                    onClick={() => setSpikeSort("growth")}
                  >
                    증가율
                  </button>
                </div>
              </div>
            </div>
            <div className="panel-body flush scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>키워드</th>
                    <th className="num">언급 수</th>
                    <th className="num">증가율</th>
                    <th className="num">이벤트</th>
                  </tr>
                </thead>
                <tbody>
                  {spikeRows.map((k) => (
                    <tr
                      key={k.keyword}
                      className={selectedKeyword === k.keyword ? "is-selected" : ""}
                      onClick={() => setSelectedKeyword(k.keyword)}
                    >
                      <td>
                        <span style={{ color: "var(--spike)", marginRight: 6 }}>●</span>
                        {k.keyword}
                      </td>
                      <td className="num">{fmtNum(k.mentions)}</td>
                      <td className="num" style={{ color: "var(--up)" }}>
                        {fmtPct(k.growth)}
                      </td>
                      <td className="num">
                        <span className="score-bar">
                          <span style={{ width: `${Math.min(100, k.eventScore ?? 0)}%` }} />
                        </span>
                        {k.eventScore}
                      </td>
                    </tr>
                  ))}
                  {spikeRows.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="empty">
                        선택한 구간에 해당하는 급상승 키워드가 없습니다.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {selectedKeyword && (
        <DashboardRightRail
          selectedKeyword={selectedKeyword}
          activeKeywordSummary={activeKeywordSummary}
          activeWindowLabel={activeWindowLabel}
          watchlist={watchlist}
          addToWatchlist={addToWatchlist}
          removeFromWatchlist={removeFromWatchlist}
          detailTrend={detailTrend}
          detailTrendSeries={detailTrendSeries}
          activeRange={activeRange}
          themeDistribution={themeDistribution}
          themeBarItems={themeBarItems}
          related={related}
          relatedView={relatedView}
          setRelatedView={setRelatedView}
          articles={articles}
          articleSort={articleSort}
          setArticleSort={setArticleSort}
          selectedArticle={selectedArticle}
          setSelectedArticle={setSelectedArticle}
          setSelectedKeyword={setSelectedKeyword}
          onClose={() => setSelectedKeyword(null)}
        />
      )}

      {dictionaryOpen ? <DictionaryApiModal onClose={() => setDictionaryOpen(false)} /> : null}
      {queryKeywordOpen ? <QueryKeywordModal onClose={() => setQueryKeywordOpen(false)} /> : null}
    </div>
  );
}
