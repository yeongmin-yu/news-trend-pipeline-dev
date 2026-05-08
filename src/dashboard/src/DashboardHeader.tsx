import { Icon } from "./ui";
import { fmtKST } from "./utils";

export type ActiveTab = "dashboard" | "pipeline" | "dict" | "keyword";

interface DashboardHeaderProps {
  now: number;
  autoRefresh: boolean;
  setAutoRefresh: (v: boolean) => void;
  theme: "dark" | "light";
  setTheme: (t: "dark" | "light") => void;
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
}

export function DashboardHeader({
  now,
  autoRefresh,
  setAutoRefresh,
  theme,
  setTheme,
  activeTab,
  setActiveTab,
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
        <div
          className={`nav-item${activeTab === "dashboard" ? " is-active" : ""}`}
          style={{ cursor: "pointer" }}
          onClick={() => setActiveTab("dashboard")}
        >
          <Icon.Activity />
          대시보드
        </div>
        
        <div
          className={`nav-item${activeTab === "pipeline" ? " is-active" : ""}`}
          style={{ cursor: "pointer" }}
          onClick={() => setActiveTab("pipeline")}
        >
          <Icon.Activity />
          파이프라인
        </div>
        <div
          className={`nav-item${activeTab === "dict" ? " is-active" : ""}`}
          style={{ cursor: "pointer" }}
          onClick={() => setActiveTab("dict")}
        >
          <Icon.Settings />
          용어 사전
        </div>
        <div
          className={`nav-item${activeTab === "keyword" ? " is-active" : ""}`}
          style={{ cursor: "pointer" }}
          onClick={() => setActiveTab("keyword")}
        >
          <Icon.Hash />
          키워드 관리
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
