import type { FiltersResponse, KeywordSummary, SystemStatusResponse } from "./data";
import type { AsyncState } from "./hooks";
import { fmtPct } from "./ui";
import { getDomainColor } from "./utils";

interface DashboardSidebarProps {
  activeFilters: FiltersResponse;
  domain: string;
  setDomain: (d: string) => void;
  watchlist: string[];
  selectedKeyword: string | null;
  setSelectedKeyword: (k: string | null) => void;
  displayKeywordLookup: Map<string, KeywordSummary>;
  addToWatchlist: (kw: string) => void;
  removeFromWatchlist: (kw: string) => void;
  spikeMinMentions: number;
  setSpikeMinMentions: (n: number) => void;
  spikeMinGrowth: number;
  setSpikeMinGrowth: (n: number) => void;
  system: AsyncState<SystemStatusResponse>;
}

export function DashboardSidebar({
  activeFilters,
  domain,
  setDomain,
  watchlist,
  selectedKeyword,
  setSelectedKeyword,
  displayKeywordLookup,
  addToWatchlist,
  removeFromWatchlist,
  spikeMinMentions,
  setSpikeMinMentions,
  spikeMinGrowth,
  setSpikeMinGrowth,
  system,
}: DashboardSidebarProps) {
  return (
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
                <span
                  className="dot"
                  style={{ background: kwObj?.spike ? "var(--spike)" : "var(--accent)" }}
                />
                {kw}
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {kwObj && (
                  <span
                    className="n"
                    style={{ color: kwObj.spike ? "var(--spike)" : "var(--text-4)" }}
                  >
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
          <div style={{ fontSize: 11, color: "var(--text-4)", padding: "4px 8px" }}>
            키워드를 추가하세요
          </div>
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
        {(system.error
          ? [
              {
                key: "api",
                label: "API 서버",
                status: "down" as const,
                detail: system.error,
                statusCode: null,
              },
            ]
          : system.data?.services ?? []
        ).map((svc) => (
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
              {svc.statusCode != null ? `HTTP ${svc.statusCode}` : "HTTP -"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
