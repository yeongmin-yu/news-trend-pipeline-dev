import { useEffect, useMemo, useRef, useState } from "react";

function fmtKST(ms: number, withSeconds = false): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  const kst = new Date(ms + 9 * 3600_000);
  const date = `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())}`;
  const time = withSeconds
    ? `${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}:${pad(kst.getUTCSeconds())}`
    : `${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}`;
  void d;
  return `${date} ${time} KST`;
}
import {
  api,
  type ArticleItem,
  type FiltersResponse,
  type KeywordSummary,
  type RangeId,
  type RelatedKeyword,
  type SourceId,
  type ThemeDistributionResponse,
  type TrendResponse,
} from "./data";
import { RelatedNetwork, SpikeHeatmap, TopKeywords, TrendLine } from "./charts";
import { DictionaryApiModal } from "./dictionary-modal";
import { QueryKeywordModal } from "./query-keyword-modal";
import { EmptyState, fmtAgo, fmtNum, fmtPct, Icon, LoadingState, StatusChip } from "./ui";

type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

const DEFAULT_FILTERS: FiltersResponse = {
  domains: [{ id: "ai_tech", label: "AI · 테크", available: true }],
  sources: [
    { id: "all", label: "전체", color: "#7dd3fc" },
    { id: "naver", label: "네이버 뉴스", color: "#34d399" },
    { id: "global", label: "글로벌 뉴스", color: "#f59e0b" },
  ],
  ranges: [
    { id: "10m", label: "10분", bucketMin: 1, buckets: 10 },
    { id: "30m", label: "30분", bucketMin: 3, buckets: 10 },
    { id: "1h", label: "1시간", bucketMin: 5, buckets: 12 },
    { id: "6h", label: "6시간", bucketMin: 30, buckets: 12 },
    { id: "12h", label: "12시간", bucketMin: 60, buckets: 12 },
    { id: "1d", label: "1일", bucketMin: 120, buckets: 12 },
  ],
};

const EMPTY_THEME_DISTRIBUTION: ThemeDistributionResponse = {
  keyword: "",
  totalMentions: 0,
  items: [],
};

const DOMAIN_COLORS: Record<string, string> = {
  all: "#a78bfa",
  ai_tech: "#5eead4",
  economy_finance: "#f472b6",
  politics_policy: "#fbbf24",
  entertainment_culture: "#60a5fa",
};

function useAsyncData<T>(factory: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null });

  useEffect(() => {
    let alive = true;
    setState({ data: null, loading: true, error: null });
    factory()
      .then((data) => {
        if (alive) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (alive)
          setState({
            data: null,
            loading: false,
            error: error instanceof Error ? error.message : "알 수 없는 오류",
          });
      });
    return () => { alive = false; };
  }, deps);

  return state;
}

function KpiCard({
  label,
  value,
  sub,
  delta,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  delta: string;
  tone: "up" | "down" | "warn" | "info" | "muted" | "spike";
}) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-delta">
        <StatusChip tone={tone}>{delta}</StatusChip>
      </div>
      <div className="side-footer" style={{ padding: 0, marginTop: 8 }}>
        {sub}
      </div>
    </div>
  );
}

function getDomainColor(domainId: string, available: boolean): string {
  if (!available) return "var(--text-4)";
  return DOMAIN_COLORS[domainId] ?? "var(--accent)";
}

function getTopKeywordBarColor(domainId: string): string {
  return DOMAIN_COLORS[domainId] ?? DOMAIN_COLORS.all;
}

function rankKeywords(items: KeywordSummary[], sortBy: "mentions" | "growth"): KeywordSummary[] {
  const ranked = [...items];
  if (sortBy === "growth") ranked.sort((a, b) => (b.growth ?? 0) - (a.growth ?? 0));
  else ranked.sort((a, b) => b.mentions - a.mentions);
  return ranked;
}

function isSpikeKeyword(item: Pick<KeywordSummary, "mentions" | "growth">, minMentions: number, minGrowth: number): boolean {
  return item.mentions >= minMentions && item.growth >= minGrowth;
}

export default function App() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [source, setSource] = useState<SourceId>("all");
  const [range, setRange] = useState<RangeId>("1h");
  const [domain, setDomain] = useState("ai_tech");
  const [search, setSearch] = useState("");
  const [searchFocus, setSearchFocus] = useState(false);
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null);
  const [checkedTrendKeywords, setCheckedTrendKeywords] = useState<string[]>([]);
  const [selectedBucket, setSelectedBucket] = useState<number | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<string | null>(null);
  const [articleSort, setArticleSort] = useState<"latest" | "relevance">("latest");
  const [relatedView, setRelatedView] = useState<"network" | "bar">("network");
  const [topSort, setTopSort] = useState<"mentions" | "growth">("mentions");
  const [topLimit, setTopLimit] = useState(20);
  const [trendFetchLimit, setTrendFetchLimit] = useState(20);
  const [spikeMinMentions, setSpikeMinMentions] = useState(5);
  const [spikeMinGrowth, setSpikeMinGrowth] = useState(0.4);
  const [hiddenSeries, setHiddenSeries] = useState<string[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [now, setNow] = useState(() => Date.now());
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

  const filters = useAsyncData(() => api.filters(), []);
  const kpis = useAsyncData(() => api.kpis(source, domain, range), [source, domain, range]);
  const keywords = useAsyncData(() => api.keywords(source, domain, range, search, 30), [source, domain, range, search]);
  const spikes = useAsyncData(() => api.spikes(source, domain, range), [source, domain, range]);
  const system = useAsyncData(() => api.system(), []);
  const rawKeywords = keywords.data ?? [];
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
    if (displayKeywords.some((item) => item.keyword === selectedKeyword)) {
      return;
    }
    if (watchlist.includes(selectedKeyword)) {
      return;
    }
    setSelectedKeyword(displayKeywords[0].keyword);
  }, [selectedKeyword, displayKeywords, watchlist]);

  useEffect(() => {
    if (!rankedKeywords.length) return;
    const defaultTopFive = rankedKeywords
      .slice(0, 5)
      .map((item) => item.keyword);
    setCheckedTrendKeywords(defaultTopFive);
  }, [rankedKeywords, domain, source, range, search]);

  useEffect(() => {
    setTrendFetchLimit(topLimit);
  }, [domain, source, range, topSort, search]);

  useEffect(() => {
    setTrendFetchLimit((prev) => Math.max(prev, topLimit));
  }, [topLimit]);

  const preloadedTrendKeywords = useMemo(
    () => rankedKeywords.slice(0, trendFetchLimit).map((item) => item.keyword),
    [rankedKeywords, trendFetchLimit],
  );

  const trend = useAsyncData(
    () =>
      preloadedTrendKeywords.length
        ? api.trend(source, domain, range, preloadedTrendKeywords[0], preloadedTrendKeywords)
        : Promise.resolve({ series: [], range: DEFAULT_FILTERS.ranges[2] } as TrendResponse),
    [source, domain, range, preloadedTrendKeywords.join("|")],
  );
  const detailTrend = useAsyncData(
    () =>
      selectedKeyword
        ? api.trend(source, domain, range, selectedKeyword, [selectedKeyword])
        : Promise.resolve({ series: [], range: DEFAULT_FILTERS.ranges[2] } as TrendResponse),
    [source, domain, range, selectedKeyword],
  );
  const related = useAsyncData(
    () => (selectedKeyword ? api.related(source, domain, range, selectedKeyword) : Promise.resolve([] as RelatedKeyword[])),
    [source, domain, range, selectedKeyword],
  );
  const themeDistribution = useAsyncData(
    () =>
      selectedKeyword
        ? api.themeDistribution(source, range, selectedKeyword)
        : Promise.resolve(EMPTY_THEME_DISTRIBUTION),
    [source, range, selectedKeyword],
  );
  const articles = useAsyncData(
    () => (selectedKeyword ? api.articles(source, domain, range, selectedKeyword, articleSort) : Promise.resolve([] as ArticleItem[])),
    [source, domain, range, selectedKeyword, articleSort],
  );

  const activeFilters = filters.data ?? DEFAULT_FILTERS;
  const activeRange = useMemo(
    () => activeFilters.ranges.find((r) => r.id === range) ?? DEFAULT_FILTERS.ranges[2],
    [activeFilters.ranges, range],
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
    () => detailTrend.data?.series.find((series) => series.name === selectedKeyword) ?? detailTrend.data?.series[0] ?? null,
    [detailTrend.data, selectedKeyword],
  );
  const visibleTrendSeries = useMemo(
    () => (trend.data?.series ?? []).filter((series) => checkedTrendKeywords.includes(series.name)),
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
    const currentKeywords = displayKeywords;
    const filteredEvents = filteredSpikeEvents.filter((e) => selectedBucket == null || e.bucket === selectedBucket);
    const eventKeywords = new Set(filteredEvents.map((e) => e.keyword));
    return (selectedBucket == null
      ? currentKeywords.filter((k) => k.spike)
      : currentKeywords.filter((k) => eventKeywords.has(k.keyword))
    ).slice(0, 12);
  }, [displayKeywords, filteredSpikeEvents, selectedBucket]);

  const themeBarItems = useMemo(() => {
    const items = themeDistribution.data?.items ?? [];
    if (!items.length) return [];
    const visibleItemCount = items.length;
    const minShare = 0.02;
    const zeroCount = items.filter((item) => item.share <= 0).length;
    const reservedShare = Math.min(zeroCount * minShare, 0.24);
    const positiveItems = items.filter((item) => item.share > 0);
    const positiveTotal = positiveItems.reduce((sum, item) => sum + item.share, 0);

    if (positiveTotal <= 0) {
      const equalShare = 1 / visibleItemCount;
      return items.map((item) => ({ ...item, displayShare: equalShare }));
    }

    const scale = (1 - reservedShare) / positiveTotal;
    return items.map((item) => ({
      ...item,
      displayShare: item.share > 0 ? item.share * scale : minShare,
    }));
  }, [themeDistribution.data]);

  // Typeahead matches for search
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

  useEffect(() => {
    const visibleNames = new Set((trend.data?.series ?? []).map((series) => series.name));
    setHiddenSeries((prev) => prev.filter((name) => visibleNames.has(name)));
  }, [trend.data]);

  function addToWatchlist(keyword: string) {
    if (!keyword.trim() || watchlist.includes(keyword)) return;
    setWatchlist((prev) => [keyword, ...prev]);
  }

  function removeFromWatchlist(keyword: string) {
    setWatchlist((prev) => prev.filter((k) => k !== keyword));
  }


  return (
    <div className="app" data-right-closed={selectedKeyword ? "false" : "true"}>
      {/* Header */}
      <div className="header">
        <div className="brand">
          <div className="brand-mark">N</div>
          <div>
            <div className="brand-title">News Trend Pipeline</div>
            <div className="brand-sub">실시간 뉴스 트렌드 대시보드</div>
          </div>
        </div>
        <div className="header-nav">
          <div className="nav-item is-active">
            <Icon.Activity />
            대시보드
          </div>
          <div className="nav-item">
            <Icon.Flame />
            이벤트
          </div>
          <div className="nav-item">
            <Icon.Hash />
            키워드
          </div>
          <div className="nav-item">
            <Icon.Activity />
            파이프라인
          </div>
          <div className="nav-item" style={{ cursor: "pointer" }} onClick={() => setDictionaryOpen(true)}>
            <Icon.Settings />
            용어 사전
          </div>
          <div className="nav-item" style={{ cursor: "pointer" }} onClick={() => setQueryKeywordOpen(true)}>
            <Icon.Hash />
            도메인 키워드 관리
          </div>
        </div>
        <div className="header-spacer" />
        <div className="header-meta">
          <span>
            <span className="pulse" />
            LIVE · {fmtKST(now, true)}
          </span>
        </div>
        <button
          className={`header-btn${autoRefresh ? " is-active" : ""}`}
          onClick={() => setAutoRefresh(!autoRefresh)}
          title="자동 새로고침 (5분)"
        >
          <Icon.Refresh />
          {autoRefresh ? "Auto · 5m" : "Manual"}
        </button>
        <button className="header-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Icon.Sun /> : <Icon.Moon />}
        </button>
      </div>

      {/* Subbar */}
      <div className="subbar">
        <span className="subbar-label">SOURCE</span>
        <div className="seg">
          {activeFilters.sources.map((s) => (
            <button key={s.id} className={source === s.id ? "is-active" : ""} onClick={() => setSource(s.id)}>
              {s.label}
            </button>
          ))}
        </div>
        <span className="divider" />
        <span className="subbar-label">DOMAIN</span>
        <div className="seg">
          {activeFilters.domains.map((d) => (
            <button
              key={d.id}
              className={domain === d.id ? "is-active" : ""}
              onClick={() => d.available && setDomain(d.id)}
              disabled={!d.available}
              title={d.available ? "" : "DB 스키마 확장 후 지원 예정"}
            >
              {d.label}
            </button>
          ))}
        </div>
        <span className="divider" />
        <span className="subbar-label">RANGE</span>
        <div className="seg">
          {activeFilters.ranges.map((r) => (
            <button key={r.id} className={range === r.id ? "is-active" : ""} onClick={() => setRange(r.id)}>
              {r.label}
            </button>
          ))}
        </div>
        <span className="divider" />
        {/* Typeahead search */}
        <div className="typeahead-wrap" ref={searchRef}>
          <div className="field">
            <Icon.Search />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="키워드 검색…"
              style={{ width: 160 }}
              onFocus={() => setSearchFocus(true)}
              onBlur={() => setTimeout(() => setSearchFocus(false), 150)}
            />
          </div>
          {searchFocus && typeaheadMatches.length > 0 && (
            <div className="typeahead-list">
              {typeaheadMatches.map((k) => (
                <div
                  key={k.keyword}
                  className="typeahead-item"
                  onMouseDown={() => {
                    setSelectedKeyword(k.keyword);
                    setSearch("");
                  }}
                >
                  <span>{k.keyword}</span>
                  <span className="count">{fmtNum(k.mentions)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ flex: 1 }} />
        <span className="subbar-label">AS OF</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>
          {fmtKST(now - activeRange.bucketMin * activeRange.buckets * 60_000)}
        </span>
      </div>

      {/* Sidebar */}
      <div className="sidebar">
        <div className="side-section">
          <div className="side-heading">
            <span>도메인 요약</span>
            <span className="count">{activeFilters.domains.length}</span>
          </div>
          {activeFilters.domains.map((d) => (
            <div
              key={d.id}
              className={`side-item${domain === d.id ? " is-active" : ""}`}
              onClick={() => d.available && setDomain(d.id)}
            >
              <span className="label">
                <span className="dot" style={{ background: getDomainColor(d.id, d.available) }} />
                {d.label}
              </span>
              <span className="n">{d.available ? "live" : "plan"}</span>
            </div>
          ))}
        </div>

        <div className="side-section">
          <div className="side-heading">
            <span>지켜보기항목</span>
            <span className="count">{watchlist.length}</span>
          </div>
          <div className="field" style={{ width: "100%" }}>
            <input
              placeholder="+ 키워드 추가…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && selectedKeyword && !watchlist.includes(selectedKeyword)) {
                  addToWatchlist(selectedKeyword);
                }
              }}
            />
          </div>
          {watchlist.map((kw) => {
            const kwObj = displayKeywordLookup.get(kw);
            return (
              <div
                key={kw}
                className={`side-item${selectedKeyword === kw ? " is-active" : ""}`}
                style={{ paddingRight: 4 }}
                onClick={() => setSelectedKeyword(kw)}
              >
                <span className="label">
                  <span className="dot" style={{ background: kwObj?.spike ? "var(--spike)" : "var(--accent)" }} />
                  {kw}
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  {kwObj && (
                    <span className="n" style={{ color: kwObj.spike ? "var(--spike)" : "var(--text-4)" }}>
                      {fmtPct(kwObj.growth ?? 0)}
                    </span>
                  )}
                  <button
                    className="n"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFromWatchlist(kw);
                    }}
                    style={{ padding: "1px 3px", borderRadius: 2 }}
                    title="제거"
                  >
                    ×
                  </button>
                </span>
              </div>
            );
          })}
          {watchlist.length === 0 && (
            <div style={{ fontSize: 11, color: "var(--text-4)", padding: "4px 8px" }}>키워드를 추가하세요</div>
          )}
        </div>

        <div className="side-section">
          <div className="side-heading">
            <span>급상승 기준</span>
            <span className="count">live</span>
          </div>
          <div className="side-control">
            <div className="side-control-head">
              <span>최소 언급량</span>
              <span className="mono">{spikeMinMentions}</span>
            </div>
            <input
              type="range"
              min={1}
              max={20}
              step={1}
              value={spikeMinMentions}
              onChange={(e) => setSpikeMinMentions(Number(e.target.value))}
            />
          </div>
          <div className="side-control">
            <div className="side-control-head">
              <span>최소 증가율</span>
              <span className="mono">{fmtPct(spikeMinGrowth)}</span>
            </div>
            <input
              type="range"
              min={0.1}
              max={2}
              step={0.05}
              value={spikeMinGrowth}
              onChange={(e) => setSpikeMinGrowth(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="side-section">
          <div className="side-heading">파이프라인 상태</div>
          {(system.data?.services ?? []).map((svc) => (
            <div className="side-item" key={svc.key}>
              <span className="label">
                <span
                  className="dot"
                  style={{
                    background:
                      svc.status === "ok"
                        ? "var(--up)"
                        : svc.status === "warn"
                          ? "var(--warn)"
                          : svc.status === "down"
                            ? "var(--down)"
                            : "var(--text-4)",
                  }}
                />
                {svc.label}
              </span>
              <span className="n">
                {svc.statusCode != null ? `${svc.statusCode} · ${svc.detail}` : svc.detail}
              </span>
            </div>
          ))}
        </div>
      </div>

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
          <KpiCard label="고유 키워드" value={fmtNum(kpis.data?.uniqueKeywords ?? 0)} delta="중복 제거" tone="info" sub="keyword_trends 기준" />
          <KpiCard label="급상승 키워드" value={String(displayKeywords.filter((item) => item.spike).length)} delta="증가율 기반" tone="spike" sub="트렌드 델타 기반" />
          <KpiCard label="마지막 업데이트" value={kpis.data?.lastUpdateRelative ?? "-"} delta={autoRefresh ? "Auto 5m" : "Manual"} tone={autoRefresh ? "info" : "muted"} sub={kpis.data?.lastUpdateAbsolute ?? "로딩 중"} />
          <KpiCard label="데이터 지원" value={String(activeFilters.domains.filter((d) => d.available).length)} delta="스키마" tone="warn" sub="추가 도메인은 추후 지원" />
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
            />
          )}

          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">
                <Icon.TrendUp size={12} />
                키워드 트렌드
                <span className="tag mono">
                  {activeRange.label} · {activeRange.buckets} pts
                </span>
              </div>
              <div className="panel-tools">
                {selectedBucket != null && (
                  <button className="panel-tool" onClick={() => setSelectedBucket(null)}>
                    clear
                  </button>
                )}
              </div>
            </div>
            <div className="panel-body">
              {trend.loading ? (
                <LoadingState label="시계열 데이터를 불러오는 중..." />
              ) : !checkedTrendKeywords.length ? (
                <EmptyState title="선택된 키워드 없음" body="상위 키워드 목록의 체크박스로 비교 대상을 선택하세요." />
              ) : (
                <TrendLine
                  series={visibleTrendSeries}
                  bucketMin={activeRange.bucketMin}
                  hidden={hiddenSeries}
                  onToggle={toggleSeries}
                  selectedBucket={selectedBucket}
                  onPointClick={setSelectedBucket}
                  nowMs={now}
                />
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
                  <button className="is-active">이벤트 점수</button>
                  <button>증가율</button>
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
                      <td className="num" style={{ color: "var(--up)" }}>{fmtPct(k.growth)}</td>
                      <td className="num">
                        <span className="score-bar">
                          <span style={{ width: `${Math.min(100, (k.eventScore ?? 0))}%` }} />
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

      {/* Right rail */}
      {selectedKeyword && (
        <div className="right-rail">
          <div className="rail-head">
            <div>
              <div className="rail-title">
                {activeKeywordSummary?.spike ? <span className="spike-dot" /> : null}
                {selectedKeyword ?? "선택된 키워드 없음"}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                {!watchlist.includes(selectedKeyword ?? "") ? (
                  <button
                    onClick={() => selectedKeyword && addToWatchlist(selectedKeyword)}
                    style={{
                      fontSize: 10,
                      color: "var(--accent)",
                      padding: "2px 7px",
                      border: "1px solid var(--accent)",
                      borderRadius: 3,
                      background: "var(--accent-weak)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    + 지켜보기항목
                  </button>
                ) : (
                  <button
                    onClick={() => selectedKeyword && removeFromWatchlist(selectedKeyword)}
                    style={{
                      fontSize: 10,
                      color: "var(--text-4)",
                      padding: "2px 7px",
                      border: "1px solid var(--border)",
                      borderRadius: 3,
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    ✓ 워치중
                  </button>
                )}
                <div className="rail-sub">KEYWORD DETAIL · {activeRange.label} window</div>
              </div>
            </div>
            <button className="rail-close" onClick={() => setSelectedKeyword(null)}>
              <Icon.Close />
            </button>
          </div>

          <div className="rail-metrics">
            <div className="rail-metric">
              <div className="lbl">Mentions</div>
              <div className="val">{fmtNum(activeKeywordSummary?.mentions ?? 0)}</div>
            </div>
            <div className="rail-metric">
              <div className="lbl">증가율</div>
              <div
                className="val"
                style={{ color: (activeKeywordSummary?.growth ?? 0) > 0 ? "var(--up)" : "var(--down)" }}
              >
                {fmtPct(activeKeywordSummary?.growth ?? 0)}
              </div>
            </div>
            <div className="rail-metric">
              <div className="lbl">Event</div>
              <div
                className="val"
                style={{ color: activeKeywordSummary?.spike ? "var(--spike)" : "var(--text-3)" }}
              >
                {fmtNum(activeKeywordSummary?.eventScore ?? 0)}
              </div>
            </div>
          </div>

          <div className="rail-section">
            <h4>
              최근 추이<span>{activeRange.label}</span>
            </h4>
            <div style={{ height: 120, position: "relative" }}>
              {detailTrend.loading ? (
                <LoadingState label="최근 추이를 불러오는 중..." />
              ) : detailTrendSeries?.points?.length ? (
                <TrendLine
                  series={[detailTrendSeries]}
                  bucketMin={activeRange.bucketMin}
                  mini={true}
                  hidden={[]}
                  nowMs={now}
                />
              ) : (
                <EmptyState title="추이 없음" body="표시할 최근 추이 데이터가 없습니다." />
              )}
            </div>
          </div>

          <div className="rail-section">
            <h4>테마별 분포</h4>
            {themeDistribution.loading ? (
              <LoadingState label="테마 분포를 불러오는 중..." />
            ) : themeBarItems.length ? (
              <>
                <div className="src-bar">
                  {themeBarItems.map((item) => (
                    <div
                      key={item.id}
                      style={{ width: `${item.displayShare * 100}%`, background: item.color ?? "var(--accent)" }}
                      title={`${item.label} ${fmtPct(item.share, false)}`}
                    />
                  ))}
                </div>
                <div className="src-legend" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  {themeBarItems.map((item) => (
                    <span key={item.id} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                      <span>
                        <span style={{ color: item.color ?? "var(--accent)" }}>■</span>{" "}
                        {item.label}
                      </span>
                      <span>{fmtPct(item.share, false)}</span>
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState title="테마 분포 없음" body="선택한 키워드의 테마 분포 데이터를 찾지 못했습니다." />
            )}
          </div>

          <div className="rail-section">
            <h4>
              연관 키워드
              <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <span className="tag">centered on · {selectedKeyword}</span>
                <div className="seg" style={{ marginLeft: 4 }}>
                  <button
                    className={relatedView === "network" ? "is-active" : ""}
                    onClick={() => setRelatedView("network")}
                  >
                    네트워크
                  </button>
                  <button
                    className={relatedView === "bar" ? "is-active" : ""}
                    onClick={() => setRelatedView("bar")}
                  >
                    막대
                  </button>
                </div>
              </span>
            </h4>
            {relatedView === "network" ? (
              <div style={{ height: 260 }}>
                {selectedKeyword && related.data ? (
                  <RelatedNetwork center={selectedKeyword} related={related.data} onSelect={setSelectedKeyword} />
                ) : (
                  <EmptyState title="선택된 키워드 없음" body="왼쪽 목록에서 키워드를 선택해 주세요." />
                )}
              </div>
            ) : (
              <div className="rail-rel" style={{ paddingTop: 4 }}>
                {(related.data ?? []).slice(0, 12).map((r) => (
                  <div
                    key={r.keyword}
                    className="rel-row"
                    onClick={() => {
                      if (r.weight >= 1) setSelectedKeyword(r.keyword);
                    }}
                    style={{ cursor: r.weight >= 1 ? "pointer" : "default" }}
                  >
                    <span className="name">{r.keyword}</span>
                    <span className="meter">
                      <div style={{ width: `${r.weight * 100}%` }} />
                    </span>
                    <span className="w">{r.weight.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rail-section" style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <h4>
              관련 기사
              <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <span>{articles.data?.length ?? 0}건</span>
                <div className="seg" style={{ marginLeft: 4 }}>
                  <button
                    className={articleSort === "latest" ? "is-active" : ""}
                    onClick={() => setArticleSort("latest")}
                  >
                    최신순
                  </button>
                  <button
                    className={articleSort === "relevance" ? "is-active" : ""}
                    onClick={() => setArticleSort("relevance")}
                  >
                    관련도순
                  </button>
                </div>
              </span>
            </h4>
            <div style={{ flex: 1, overflowY: "auto" }}>
              {articles.loading ? (
                <LoadingState label="기사 목록을 불러오는 중..." />
              ) : (
                (articles.data ?? []).map((item) => (
                  <a
                    className={`article${selectedArticle === item.id ? " is-selected" : ""}`}
                    key={item.id}
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={() => setSelectedArticle(item.id)}
                  >
                    <div className="head">
                      <span
                        className="src-dot"
                        style={{
                          width: 6,
                          height: 6,
                          background: item.source === "naver" ? "var(--up)" : "var(--warn)",
                        }}
                      />
                      <span>{item.publisher}</span>
                      <span>·</span>
                      <span>{fmtAgo(item.minutesAgo)}</span>
                    </div>
                    <div className="title">{item.title}</div>
                    <div className="ext-icon">
                      <Icon.External />
                    </div>
                    <div className="summary">{item.summary || "요약이 아직 없습니다."}</div>
                    <div className="tags">
                      {item.keywords.slice(0, 4).map((kw) => (
                        <span
                          className="tag"
                          key={`${item.id}-${kw}`}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setSelectedKeyword(kw);
                          }}
                        >
                          {kw}
                        </span>
                      ))}
                    </div>
                  </a>
                ))
              )}
              {!articles.loading && (articles.data?.length ?? 0) === 0 ? (
                <EmptyState title="기사 없음" body="선택한 키워드에 연결된 기사가 없습니다." />
              ) : null}
            </div>
          </div>
        </div>
      )}

      {dictionaryOpen ? <DictionaryApiModal onClose={() => setDictionaryOpen(false)} /> : null}
      {queryKeywordOpen ? <QueryKeywordModal onClose={() => setQueryKeywordOpen(false)} /> : null}
    </div>
  );
}
