import { Icon } from "./ui";
import { fmtKST } from "./utils";

interface DashboardHeaderProps {
  now: number;
  autoRefresh: boolean;
  setAutoRefresh: (v: boolean) => void;
  theme: "dark" | "light";
  setTheme: (t: "dark" | "light") => void;
  setDictionaryOpen: (v: boolean) => void;
  setQueryKeywordOpen: (v: boolean) => void;
}

export function DashboardHeader({
  now,
  autoRefresh,
  setAutoRefresh,
  theme,
  setTheme,
  setDictionaryOpen,
  setQueryKeywordOpen,
}: DashboardHeaderProps) {
  return (
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
  );
}
