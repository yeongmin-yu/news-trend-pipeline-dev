import type {
  ArticleItem,
  KeywordSummary,
  RangeOption,
  RelatedKeyword,
  ThemeDistributionItem,
  ThemeDistributionResponse,
  TrendResponse,
  TrendSeries,
} from "./data";
import type { AsyncState } from "./hooks";
import { RelatedNetwork, TrendLine } from "./charts";
import { EmptyState, fmtAgo, fmtNum, fmtPct, Icon, LoadingState } from "./ui";

interface DashboardRightRailProps {
  selectedKeyword: string;
  activeKeywordSummary: KeywordSummary | null;
  activeWindowLabel: string;
  watchlist: string[];
  addToWatchlist: (kw: string) => void;
  removeFromWatchlist: (kw: string) => void;
  detailTrend: AsyncState<TrendResponse>;
  detailTrendSeries: TrendSeries | null;
  activeRange: RangeOption;
  themeDistribution: AsyncState<ThemeDistributionResponse>;
  themeBarItems: Array<ThemeDistributionItem & { displayShare: number }>;
  related: AsyncState<RelatedKeyword[]>;
  relatedView: "network" | "bar";
  setRelatedView: (v: "network" | "bar") => void;
  articles: AsyncState<ArticleItem[]>;
  articleSort: "latest" | "relevance";
  setArticleSort: (v: "latest" | "relevance") => void;
  selectedArticle: string | null;
  setSelectedArticle: (id: string | null) => void;
  setSelectedKeyword: (kw: string | null) => void;
  onClose: () => void;
}

export function DashboardRightRail({
  selectedKeyword,
  activeKeywordSummary,
  activeWindowLabel,
  watchlist,
  addToWatchlist,
  removeFromWatchlist,
  detailTrend,
  detailTrendSeries,
  activeRange,
  themeDistribution,
  themeBarItems,
  related,
  relatedView,
  setRelatedView,
  articles,
  articleSort,
  setArticleSort,
  selectedArticle,
  setSelectedArticle,
  setSelectedKeyword,
  onClose,
}: DashboardRightRailProps) {
  return (
    <div className="right-rail">
      <div className="rail-head">
        <div>
          <div className="rail-title">
            {activeKeywordSummary?.spike ? <span className="spike-dot" /> : null}
            {selectedKeyword}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
            {!watchlist.includes(selectedKeyword) ? (
              <button
                onClick={() => addToWatchlist(selectedKeyword)}
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
                onClick={() => removeFromWatchlist(selectedKeyword)}
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
            <div className="rail-sub">KEYWORD DETAIL · {activeWindowLabel} window</div>
          </div>
        </div>
        <button className="rail-close" onClick={onClose}>
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
            style={{
              color: (activeKeywordSummary?.growth ?? 0) > 0 ? "var(--up)" : "var(--down)",
            }}
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
          최근 추이<span>{activeWindowLabel}</span>
        </h4>
        <div style={{ height: 120, position: "relative" }}>
          {detailTrend.loading ? (
            <LoadingState label="최근 추이를 불러오는 중..." />
          ) : detailTrendSeries?.points?.length ? (
            <TrendLine
              series={[detailTrendSeries]}
              bucketMin={detailTrend.data?.range.bucketMin ?? activeRange.bucketMin}
              mini={true}
              hidden={[]}
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
                  style={{
                    width: `${item.displayShare * 100}%`,
                    background: item.color ?? "var(--accent)",
                  }}
                  title={`${item.label} ${fmtPct(item.share, false)}`}
                />
              ))}
            </div>
            <div
              className="src-legend"
              style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
            >
              {themeBarItems.map((item) => (
                <span key={item.id} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span>
                    <span style={{ color: item.color ?? "var(--accent)" }}>■</span> {item.label}
                  </span>
                  <span>{fmtPct(item.share, false)}</span>
                </span>
              ))}
            </div>
          </>
        ) : (
          <EmptyState
            title="테마 분포 없음"
            body="선택한 키워드의 테마 분포 데이터를 찾지 못했습니다."
          />
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
            {related.data ? (
              <RelatedNetwork
                center={selectedKeyword}
                related={related.data}
                onSelect={setSelectedKeyword}
              />
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

      <div
        className="rail-section"
        style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}
      >
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
  );
}
