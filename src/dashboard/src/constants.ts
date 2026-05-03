import type { DashboardOverviewResponse, FiltersResponse, ThemeDistributionResponse, TrendBucketId } from "./data";

export const OVERVIEW_FETCH_EDGE_RATIO = 0.1;
export const OVERVIEW_FETCH_EDGE_MIN_MS = 2 * 60 * 1000;

export const DEFAULT_FILTERS: FiltersResponse = {
  domains: [
    {
      id: "tech_science",
      label: "IT·과학·테크",
      groupId: "tech",
      groupLabel: "IT·과학·테크",
      groupSortOrder: 4,
      available: true,
    },
  ],
  sources: [
    { id: "all", label: "전체", color: "#7dd3fc" },
    { id: "naver", label: "NaverNews", color: "#34d399" },
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

// `all` 가상 도메인 전용 예약 색상 (보라/액센트 톤).
export const DOMAIN_ALL_COLOR = "#a78bfa";

// 도메인 id를 모르는 상태에서도 충분히 구분되는 색상 팔레트.
// 서버가 내려준 도메인 순서대로 buildDomainColorMap()이 이 리스트를 순환 할당한다.
// red 계열은 --spike(급상승 키워드) 색상과 충돌하므로 의도적으로 제외한다.
export const DOMAIN_COLOR_PALETTE: string[] = [
  "#fbbf24", // amber
  "#f97316", // orange
  "#ec4899", // pink
  "#d946ef", // fuchsia
  "#a855f7", // purple
  "#6366f1", // indigo
  "#3b82f6", // blue
  "#0ea5e9", // sky
  "#06b6d4", // cyan
  "#5eead4", // teal
  "#10b981", // emerald
  "#22c55e", // green
  "#84cc16", // lime
];

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
