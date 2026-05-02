import type { DomainOption, FiltersResponse, KeywordSummary, SystemStatusResponse } from "./data";
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

function domainGroupId(domain: DomainOption): string {
  return domain.groupId ?? domain.group_id ?? (domain.id === "all" ? "all" : "other");
}

function domainGroupLabel(domain: DomainOption): string {
  return domain.groupLabel ?? domain.group_label ?? (domain.id === "all" ? "전체" : "기타");
}

function domainGroupSortOrder(domain: DomainOption): number {
  return domain.groupSortOrder ?? domain.group_sort_order ?? (domain.id === "all" ? 0 : 999);
}

function groupDomains(domains: DomainOption[]): Array<{ id: string; label: string; domains: DomainOption[]; order: number }> {
  const grouped = new Map<string, { id: string; label: string; domains: DomainOption[]; order: number }>();
  for (const item of domains) {
    const id = domainGroupId(item);
    const existing = grouped.get(id);
    if (existing) {
      existing.domains.push(item);
      existing.order = Math.min(existing.order, domainGroupSortOrder(item));
      continue;
    }
    grouped.set(id, {
      id,
      label: domainGroupLabel(item),
      domains: [item],
      order: domainGroupSortOrder(item),
    });
  }
  return Array.from(grouped.values()).sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
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
  const domainGroups = groupDomains(activeFilters.domains);

  return (
    <div className="sidebar">
      <div className="side-section">
        <div className="side-heading">
          <span>도메인 그룹</span>
          <span className="count">{domainGroups.length}</span>
        </div>
        {domainGroups.map((group) => (
          <div className="domain-group" key={group.id}>
            <div
              className={`side-item domain-group-head${domain === group.id ? " is-active" : ""}`}
              onClick={() => setDomain(group.id)}
            >
              <span className="label">{group.label}</span>
              <span className="n">{group.domains.length}</span>
            </div>
            {group.domains.map((d) => (
              <div
                key={d.id}
                className="side-item domain-child"
                onClick={() => d.available && setDomain(group.id)}
              >
                <span className="label">
                  <span className="dot" style={{ background: getDomainColor(d.id, d.available) }} />
                  {d.label}
                </span>
                <span className="n">{d.available ? "live" : "plan"}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="side-section">
        <div className="side-heading">
          <span>지켜볼 키워드</span>
          <span className="count">{watchlist.length}</span>
        </div>
        <div className="field" style={{ width: "100%" }}>
          <input
            placeholder="+ 키워드 추가"
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
                  x
                </button>
              </span>
            </div>
          );
        })}
        {watchlist.length === 0 && (
          <div style={{ fontSize: 11, color: "var(--text-4)", padding: "4px 8px" }}>
            키워드를 추가하세요.
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
