import type { KeywordSummary, FiltersResponse, RangeId, SourceId } from "./data";
import { Icon, fmtNum } from "./ui";
import { fmtKST, toDateTimeLocalInput } from "./utils";

interface DashboardSubbarProps {
  activeFilters: FiltersResponse;
  source: SourceId;
  setSource: (s: SourceId) => void;
  domain: string;
  setDomain: (d: string) => void;
  trendWindow: { startMs: number; endMs: number };
  setTrendWindowBound: (kind: "start" | "end", value: string) => void;
  rangePreset: RangeId | null;
  applyRangePreset: (r: RangeId) => void;
  search: string;
  setSearch: (s: string) => void;
  searchFocus: boolean;
  setSearchFocus: (v: boolean) => void;
  typeaheadMatches: KeywordSummary[];
  setSelectedKeyword: (k: string | null) => void;
  searchRef: React.Ref<HTMLDivElement>;
}

export function DashboardSubbar({
  activeFilters,
  source,
  setSource,
  domain,
  setDomain,
  trendWindow,
  setTrendWindowBound,
  rangePreset,
  applyRangePreset,
  search,
  setSearch,
  searchFocus,
  setSearchFocus,
  typeaheadMatches,
  setSelectedKeyword,
  searchRef,
}: DashboardSubbarProps) {
  return (
    <div className="subbar">
      <span className="subbar-label">SOURCE</span>
      <div className="seg">
        {activeFilters.sources.map((s) => (
          <button
            key={s.id}
            className={source === s.id ? "is-active" : ""}
            onClick={() => setSource(s.id)}
          >
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
      <span className="subbar-label">DATE</span>
      <div className="subbar-date">
        <div className="field">
          <input
            type="datetime-local"
            value={toDateTimeLocalInput(trendWindow.startMs)}
            onChange={(e) => setTrendWindowBound("start", e.target.value)}
          />
        </div>
        <span className="subbar-date-sep">~</span>
        <div className="field">
          <input
            type="datetime-local"
            value={toDateTimeLocalInput(trendWindow.endMs)}
            onChange={(e) => setTrendWindowBound("end", e.target.value)}
          />
        </div>
      </div>
      <span className="divider" />
      <span className="subbar-label">현 시간 기준</span>
      <div className="range-buttons">
        {activeFilters.ranges.map((r) => (
          <button
            key={r.id}
            className={rangePreset === r.id ? "is-active" : ""}
            onClick={() => applyRangePreset(r.id)}
          >
            {r.label}
          </button>
        ))}
      </div>
      <span className="divider" />
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
        {fmtKST(trendWindow.endMs)}
      </span>
    </div>
  );
}
