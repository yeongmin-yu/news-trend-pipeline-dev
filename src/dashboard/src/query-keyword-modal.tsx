import { useEffect, useMemo, useState } from "react";
import { api, type DomainOption, type QueryKeywordAdminOverview, type QueryKeywordItem } from "./data";
import { Icon, LoadingState } from "./ui";

type TabId = "keywords" | "metrics" | "logs";

const EMPTY_FORM = {
  id: null as number | null,
  domainId: "ai_tech",
  query: "",
  sortOrder: 1,
  isActive: true,
};

export function QueryKeywordModal({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<TabId>("keywords");
  const [data, setData] = useState<QueryKeywordAdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [domainFilter, setDomainFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [toast, setToast] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await api.queryKeywordAdmin());
    } catch (err) {
      setError(err instanceof Error ? err.message : "도메인 키워드 데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function showToast(message: string) {
    setToast(message);
    setTimeout(() => setToast(null), 2200);
  }

  async function run(key: string, action: () => Promise<unknown>, successMsg: string) {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
      showToast(successMsg);
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청을 처리하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  const domains: DomainOption[] = useMemo(() => data?.domains ?? [], [data]);
  const filteredKeywords = useMemo(() => {
    return (data?.queryKeywords ?? []).filter((item) => {
      const domainMatched = domainFilter === "all" || item.domain_id === domainFilter;
      const searchMatched = !search || item.query.toLowerCase().includes(search.toLowerCase());
      return domainMatched && searchMatched;
    });
  }, [data, domainFilter, search]);

  const filteredMetrics = useMemo(() => {
    return (data?.collectionMetrics ?? []).filter((item) => domainFilter === "all" || item.domain === domainFilter);
  }, [data, domainFilter]);

  const filteredLogs = useMemo(() => {
    return (data?.auditLogs ?? []).filter((item) => {
      if (domainFilter === "all") return true;
      const afterDomain = item.after_json && typeof item.after_json["domain_id"] === "string" ? String(item.after_json["domain_id"]) : null;
      const beforeDomain = item.before_json && typeof item.before_json["domain_id"] === "string" ? String(item.before_json["domain_id"]) : null;
      return afterDomain === domainFilter || beforeDomain === domainFilter;
    });
  }, [data, domainFilter]);

  function startEdit(item: QueryKeywordItem) {
    setForm({
      id: item.id,
      domainId: item.domain_id,
      query: item.query,
      sortOrder: item.sort_order,
      isActive: item.is_active,
    });
  }

  const saveDisabled = !form.query.trim() || !form.domainId;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 210,
        background: "rgba(0,0,0,0.72)",
        backdropFilter: "blur(6px)",
        display: "flex",
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        style={{
          margin: "32px auto",
          width: "min(1280px, 96vw)",
          height: "calc(100vh - 64px)",
          background: "var(--bg-1)",
          border: "1px solid var(--border-hi)",
          borderRadius: 10,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          boxShadow: "0 32px 80px rgba(0,0,0,0.6)",
        }}
      >
        <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 16, background: "var(--bg-2)", flexShrink: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>도메인 키워드 관리</div>
          <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
            naver queries {data?.queryKeywords.length ?? 0}
          </div>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => void load()}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 5, border: "1px solid var(--border)", color: "var(--text-3)", fontSize: 11, background: "transparent", cursor: "pointer" }}
          >
            <Icon.Refresh size={12} />
            새로고침
          </button>
          <button
            onClick={onClose}
            style={{ color: "var(--text-3)", padding: "4px 8px", borderRadius: 5, background: "transparent", border: "none", cursor: "pointer", display: "flex", alignItems: "center" }}
          >
            <Icon.Close size={16} />
          </button>
        </div>

        <div style={{ display: "flex", borderBottom: "1px solid var(--border)", background: "var(--bg-1)", padding: "0 20px", flexShrink: 0 }}>
          {([
            ["keywords", "쿼리 키워드"],
            ["metrics", "수집 지표"],
            ["logs", "변경 로그"],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              style={{
                padding: "10px 18px",
                fontSize: 12,
                fontWeight: 500,
                borderBottom: tab === id ? "2px solid var(--accent)" : "2px solid transparent",
                color: tab === id ? "var(--text)" : "var(--text-3)",
                marginBottom: -1,
                background: "transparent",
                borderTop: "none",
                borderLeft: "none",
                borderRight: "none",
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--bg)", flexShrink: 0 }}>
          <div className="field" style={{ gap: 6 }}>
            <Icon.Search size={12} />
            <input
              placeholder="키워드 검색"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              style={{ width: 180, fontSize: 12 }}
            />
          </div>
          <div className="seg">
            <button className={domainFilter === "all" ? "is-active" : ""} onClick={() => setDomainFilter("all")}>
              전체
            </button>
            {domains.map((domain) => (
              <button
                key={domain.id}
                className={domainFilter === domain.id ? "is-active" : ""}
                onClick={() => setDomainFilter(domain.id)}
              >
                {domain.label}
              </button>
            ))}
          </div>
        </div>

        {tab === "keywords" && (
          <div style={{ padding: "12px 20px", borderBottom: "1px solid var(--border)", background: "var(--bg-2)", display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", flexShrink: 0 }}>
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
              도메인
              <select
                value={form.domainId}
                onChange={(event) => setForm((prev) => ({ ...prev, domainId: event.target.value }))}
                style={{ padding: "6px 8px", background: "var(--bg-3)", border: "1px solid var(--border-hi)", borderRadius: 4, color: "var(--text)", fontSize: 12 }}
              >
                {domains.map((domain) => (
                  <option key={domain.id} value={domain.id}>
                    {domain.label}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
              키워드
              <input
                value={form.query}
                onChange={(event) => setForm((prev) => ({ ...prev, query: event.target.value }))}
                style={{ padding: "6px 8px", background: "var(--bg-3)", border: "1px solid var(--border-hi)", borderRadius: 4, color: "var(--text)", fontSize: 12, width: 220 }}
              />
            </label>
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
              정렬 순서
              <input
                type="number"
                value={form.sortOrder}
                onChange={(event) => setForm((prev) => ({ ...prev, sortOrder: Number(event.target.value) }))}
                style={{ padding: "6px 8px", background: "var(--bg-3)", border: "1px solid var(--border-hi)", borderRadius: 4, color: "var(--text)", fontSize: 12, width: 96 }}
              />
            </label>
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", gap: 6, alignItems: "center", paddingBottom: 8 }}>
              <input
                type="checkbox"
                checked={form.isActive}
                onChange={(event) => setForm((prev) => ({ ...prev, isActive: event.target.checked }))}
              />
              활성화
            </label>
            <button
              disabled={saveDisabled || busy === "save-query"}
              onClick={() =>
                void run(
                  "save-query",
                  () =>
                    form.id == null
                      ? api.createQueryKeyword({
                          domainId: form.domainId,
                          query: form.query.trim(),
                          sortOrder: form.sortOrder,
                          isActive: form.isActive,
                        })
                      : api.updateQueryKeyword(form.id, {
                          domainId: form.domainId,
                          query: form.query.trim(),
                          sortOrder: form.sortOrder,
                          isActive: form.isActive,
                        }),
                  form.id == null ? "키워드를 추가했습니다." : "키워드를 수정했습니다.",
                )
              }
              style={{ padding: "6px 16px", background: "var(--accent)", color: "#061617", borderRadius: 5, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", opacity: saveDisabled ? 0.5 : 1 }}
            >
              {form.id == null ? "추가" : "저장"}
            </button>
            <button
              onClick={() => setForm(EMPTY_FORM)}
              style={{ padding: "6px 16px", background: "transparent", color: "var(--text-3)", borderRadius: 5, fontSize: 12, border: "1px solid var(--border)", cursor: "pointer" }}
            >
              초기화
            </button>
          </div>
        )}

        {error && (
          <div style={{ padding: "8px 20px", color: "var(--down)", fontSize: 11, background: "var(--down-weak)", borderBottom: "1px solid var(--down)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
            {error}
          </div>
        )}

        <div style={{ flex: 1, overflowY: "auto" }}>
          {loading && !data ? (
            <LoadingState label="도메인 키워드 데이터를 불러오는 중..." />
          ) : tab === "keywords" ? (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>도메인</th>
                  <th>키워드</th>
                  <th className="num">순서</th>
                  <th>상태</th>
                  <th>업데이트</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {filteredKeywords.map((item) => (
                  <tr key={item.id}>
                    <td>{item.domain_label}</td>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 600 }}>{item.query}</span></td>
                    <td className="num">{item.sort_order}</td>
                    <td><span className={"chip " + (item.is_active ? "up" : "muted")}>{item.is_active ? "활성" : "비활성"}</span></td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{item.updated_at?.slice(0, 16).replace("T", " ")}</td>
                    <td style={{ display: "flex", gap: 4 }}>
                      <button onClick={() => startEdit(item)} className="table-action">수정</button>
                      <button
                        onClick={() =>
                          void run(`toggle-${item.id}`, () => api.updateQueryKeyword(item.id, {
                            domainId: item.domain_id,
                            query: item.query,
                            sortOrder: item.sort_order,
                            isActive: !item.is_active,
                          }), item.is_active ? "키워드를 비활성화했습니다." : "키워드를 활성화했습니다.")
                        }
                        className="table-action"
                      >
                        {item.is_active ? "비활성화" : "활성화"}
                      </button>
                      <button
                        onClick={() => void run(`delete-${item.id}`, () => api.deleteQueryKeyword(item.id), "키워드를 삭제했습니다.")}
                        className="table-action danger"
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                ))}
                {filteredKeywords.length === 0 && (
                  <tr><td colSpan={6} className="empty">표시할 키워드가 없습니다.</td></tr>
                )}
              </tbody>
            </table>
          ) : tab === "metrics" ? (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>도메인</th>
                  <th>키워드</th>
                  <th className="num">호출</th>
                  <th className="num">성공</th>
                  <th className="num">기사 수</th>
                  <th className="num">중복</th>
                  <th className="num">발행</th>
                  <th className="num">오류</th>
                  <th>최근 수집</th>
                </tr>
              </thead>
              <tbody>
                {filteredMetrics.map((item) => (
                  <tr key={`${item.domain}-${item.query}`}>
                    <td>{domains.find((domain) => domain.id === item.domain)?.label ?? item.domain}</td>
                    <td>{item.query}</td>
                    <td className="num">{item.request_count}</td>
                    <td className="num">{item.success_count}</td>
                    <td className="num">{item.article_count}</td>
                    <td className="num">{item.duplicate_count}</td>
                    <td className="num">{item.publish_count}</td>
                    <td className="num">{item.error_count}</td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{item.last_seen_at?.slice(0, 16).replace("T", " ")}</td>
                  </tr>
                ))}
                {filteredMetrics.length === 0 && (
                  <tr><td colSpan={9} className="empty">수집 지표가 아직 없습니다.</td></tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>시각</th>
                  <th>액션</th>
                  <th>작업자</th>
                  <th>이전 값</th>
                  <th>변경 값</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((item) => (
                  <tr key={item.id}>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{item.acted_at?.slice(0, 16).replace("T", " ")}</td>
                    <td><span className="chip info">{item.action}</span></td>
                    <td>{item.actor}</td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>{item.before_json ? JSON.stringify(item.before_json) : "-"}</td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>{item.after_json ? JSON.stringify(item.after_json) : "-"}</td>
                  </tr>
                ))}
                {filteredLogs.length === 0 && (
                  <tr><td colSpan={5} className="empty">변경 로그가 없습니다.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        <div style={{ padding: "8px 20px", borderTop: "1px solid var(--border)", display: "flex", gap: 14, fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", background: "var(--bg-2)", alignItems: "center", flexShrink: 0 }}>
          <span>도메인별 네이버 수집 키워드와 최근 24시간 지표를 함께 관리합니다.</span>
          <div style={{ flex: 1 }} />
          <span>변경 즉시 DB에 반영되며 다음 수집 주기부터 적용됩니다.</span>
        </div>
      </div>

      {toast && (
        <div style={{
          position: "fixed",
          bottom: 32,
          left: "50%",
          transform: "translateX(-50%)",
          background: "var(--bg-1)",
          border: "1px solid var(--accent)",
          borderRadius: 8,
          padding: "10px 20px",
          fontSize: 12,
          color: "var(--text)",
          zIndex: 300,
          boxShadow: "0 8px 30px rgba(0,0,0,0.5)",
          fontFamily: "var(--font-mono)",
          whiteSpace: "nowrap",
        }}>{toast}</div>
      )}
    </div>
  );
}
