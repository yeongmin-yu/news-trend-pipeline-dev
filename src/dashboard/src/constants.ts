import type { DashboardOverviewResponse, FiltersResponse, ThemeDistributionResponse, TrendBucketId } from "./data";

export const OVERVIEW_FETCH_EDGE_RATIO = 0.1;
export const OVERVIEW_FETCH_EDGE_MIN_MS = 2 * 60 * 1000;

export const DEFAULT_FILTERS: FiltersResponse = {
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

export const EMPTY_THEME_DISTRIBUTION: ThemeDistributionResponse = {
  keyword: "",
  totalMentions: 0,
  items: [],
};

export const EMPTY_KEYWORD_LIST: DashboardOverviewResponse["keywords"] = [];

export const DOMAIN_COLORS: Record<string, string> = {
  all: "#a78bfa",
  ai_tech: "#5eead4",
  economy_finance: "#f472b6",
  politics_policy: "#fbbf24",
  entertainment_culture: "#60a5fa",
};

export const TREND_BUCKET_OPTIONS: Array<{ id: TrendBucketId; label: string; minutes: number }> = [
  { id: "5m", label: "5분", minutes: 5 },
  { id: "15m", label: "15분", minutes: 15 },
  { id: "30m", label: "30분", minutes: 30 },
  { id: "1h", label: "1시간", minutes: 60 },
  { id: "4h", label: "4시간", minutes: 240 },
  { id: "1d", label: "1일", minutes: 1440 },
];

export const MIN_TREND_WINDOW_MS = 30 * 60 * 1000;
export const MAX_TREND_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;
export const MAX_POINTS_PER_QUERY = 480;
export const TREND_FETCH_OVERSCAN_BUCKETS = 7;
export const DASHBOARD_WINDOW_COMMIT_DELAY_MS = 550;
export const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
