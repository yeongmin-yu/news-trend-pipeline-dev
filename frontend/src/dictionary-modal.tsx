import { useEffect, useMemo, useState } from "react";
import {
  api,
  type CompoundCandidateItem,
  type CompoundNounItem,
  type DictionaryOverview,
  type StopwordItem,
} from "./data";
import { Icon, LoadingState } from "./ui";

type TabId = "compound" | "stopword" | "candidates";

const CANDIDATE_STATUS_LABEL: Record<string, string> = {
  pending: "대기",
  approved: "승인됨",
  rejected: "반려됨",
};

const CANDIDATE_STATUS_CHIP: Record<string, string> = {
  pending: "warn",
  approved: "up",
  rejected: "muted",
};

export function DictionaryApiModal({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<TabId>("compound");
  const [data, setData] = useState<DictionaryOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("전체");
  const [showAddForm, setShowAddForm] = useState(false);
  const [editWord, setEditWord] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await api.dictionary());
    } catch (err) {
      setError(err instanceof Error ? err.message : "사전 데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2200);
  }

  async function run(key: string, action: () => Promise<unknown>, successMsg: string) {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
      showToast(successMsg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청을 처리하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  const filteredCompounds = useMemo<CompoundNounItem[]>(() => {
    return (data?.compoundNouns ?? []).filter(
      (c) => !searchQ || c.word.toLowerCase().includes(searchQ.toLowerCase()),
    );
  }, [data, searchQ]);

  const filteredStopwords = useMemo<StopwordItem[]>(() => {
    return (data?.stopwords ?? []).filter(
      (s) => !searchQ || s.word.toLowerCase().includes(searchQ.toLowerCase()),
    );
  }, [data, searchQ]);

  const filteredCandidates = useMemo<CompoundCandidateItem[]>(() => {
    return (data?.compoundCandidates ?? []).filter((c) => {
      const matchQ = !searchQ || c.word.toLowerCase().includes(searchQ.toLowerCase());
      const matchStatus = statusFilter === "전체" || c.status === statusFilter;
      return matchQ && matchStatus;
    });
  }, [data, searchQ, statusFilter]);

  const versions = data?.versions;

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.7)", backdropFilter: "blur(6px)",
        display: "flex", flexDirection: "column",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          margin: "32px auto",
          width: "min(1200px, 96vw)",
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
        {/* Header */}
        <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 16, background: "var(--bg-2)", flexShrink: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>용어 사전 관리</div>
          {versions && (
            <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
              compound v{versions.compoundNounDict} · stopword v{versions.stopwordDict}
            </div>
          )}
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

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border)", background: "var(--bg-1)", padding: "0 20px", flexShrink: 0 }}>
          {([
            ["compound", "복합명사 사전", data?.compoundNouns.length],
            ["stopword", "불용어 사전", data?.stopwords.length],
            ["candidates", "복합명사 후보", data?.compoundCandidates.length],
          ] as const).map(([id, label, count]) => (
            <button
              key={id}
              onClick={() => { setTab(id); setShowAddForm(false); setStatusFilter("전체"); }}
              style={{
                padding: "10px 18px",
                fontSize: 12, fontWeight: 500,
                borderBottom: tab === id ? "2px solid var(--accent)" : "2px solid transparent",
                color: tab === id ? "var(--text)" : "var(--text-3)",
                marginBottom: -1,
                background: "transparent", border: "none",
                cursor: "pointer",
                display: "flex", alignItems: "center", gap: 6,
              }}
            >
              {label}
              {count !== undefined && (
                <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 9, background: "var(--bg-3)", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Filter bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--bg)", flexShrink: 0 }}>
          <div className="field" style={{ gap: 6 }}>
            <Icon.Search size={12} />
            <input
              placeholder="검색…"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              style={{ width: 180, fontSize: 12 }}
            />
          </div>
          {tab === "candidates" && (
            <div className="seg">
              {(["전체", "pending", "approved", "rejected"] as const).map((v) => (
                <button
                  key={v}
                  className={statusFilter === v ? "is-active" : ""}
                  onClick={() => setStatusFilter(v)}
                  style={{ fontSize: 11 }}
                >
                  {v === "전체" ? "전체" : CANDIDATE_STATUS_LABEL[v] ?? v}
                </button>
              ))}
            </div>
          )}
          <div style={{ flex: 1 }} />
          {tab !== "candidates" && (
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              style={{
                padding: "5px 12px", borderRadius: 5,
                border: "1px solid var(--accent)", color: "var(--accent)",
                fontSize: 11, fontFamily: "var(--font-mono)",
                background: showAddForm ? "var(--accent-weak)" : "transparent",
                cursor: "pointer",
              }}
            >
              {showAddForm ? "취소" : "+ 새 항목 추가"}
            </button>
          )}
        </div>

        {/* Add form */}
        {showAddForm && tab === "compound" && (
          <div style={{ padding: "12px 20px", background: "var(--bg-2)", borderBottom: "1px solid var(--border)", display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", flexShrink: 0 }}>
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
              복합명사 용어
              <input
                value={editWord}
                onChange={(e) => setEditWord(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") document.getElementById("dict-add-btn")?.click(); }}
                placeholder="예: AI반도체클러스터"
                style={{ padding: "5px 8px", background: "var(--bg-3)", border: "1px solid var(--border-hi)", borderRadius: 4, color: "var(--text)", fontSize: 12, outline: "none", width: 200 }}
              />
            </label>
            <button
              id="dict-add-btn"
              disabled={!editWord.trim() || busy === "create-compound"}
              onClick={() =>
                void run("create-compound", async () => {
                  await api.createCompound(editWord.trim());
                  setEditWord(""); setShowAddForm(false);
                }, `"${editWord.trim()}" 복합명사 등록 완료`)
              }
              style={{ padding: "6px 16px", background: "var(--accent)", color: "#061617", borderRadius: 5, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", opacity: !editWord.trim() ? 0.5 : 1 }}
            >
              {busy === "create-compound" ? "등록 중…" : "등록"}
            </button>
          </div>
        )}

        {showAddForm && tab === "stopword" && (
          <div style={{ padding: "12px 20px", background: "var(--bg-2)", borderBottom: "1px solid var(--border)", display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", flexShrink: 0 }}>
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
              불용어
              <input
                value={editWord}
                onChange={(e) => setEditWord(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") document.getElementById("dict-add-btn")?.click(); }}
                placeholder="예: 관계자"
                style={{ padding: "5px 8px", background: "var(--bg-3)", border: "1px solid var(--border-hi)", borderRadius: 4, color: "var(--text)", fontSize: 12, outline: "none", width: 180 }}
              />
            </label>
            <button
              id="dict-add-btn"
              disabled={!editWord.trim() || busy === "create-stopword"}
              onClick={() =>
                void run("create-stopword", async () => {
                  await api.createStopword(editWord.trim());
                  setEditWord(""); setShowAddForm(false);
                }, `"${editWord.trim()}" 불용어 등록 완료`)
              }
              style={{ padding: "6px 16px", background: "var(--accent)", color: "#061617", borderRadius: 5, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", opacity: !editWord.trim() ? 0.5 : 1 }}
            >
              {busy === "create-stopword" ? "등록 중…" : "등록"}
            </button>
          </div>
        )}

        {/* Error bar */}
        {error && (
          <div style={{ padding: "8px 20px", color: "var(--down)", fontSize: 11, background: "var(--down-weak)", borderBottom: "1px solid var(--down)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
            {error}
          </div>
        )}

        {/* Table area */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {loading && !data ? (
            <LoadingState label="사전 데이터를 불러오는 중..." />
          ) : tab === "compound" ? (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>복합명사</th>
                  <th>출처</th>
                  <th>등록일</th>
                  <th>상태</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {filteredCompounds.map((c) => (
                  <tr key={c.id}>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 600 }}>{c.word}</span></td>
                    <td><span className="chip muted" style={{ fontSize: 10 }}>{c.source}</span></td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{c.createdAt?.slice(0, 16).replace("T", " ") ?? "—"}</td>
                    <td><span className="chip up">활성</span></td>
                    <td>
                      <button
                        disabled={busy === `del-c-${c.id}`}
                        onClick={() => void run(`del-c-${c.id}`, () => api.deleteCompound(c.id), `"${c.word}" 삭제됨`)}
                        className="table-action danger"
                      >
                        {busy === `del-c-${c.id}` ? "…" : "삭제"}
                      </button>
                    </td>
                  </tr>
                ))}
                {filteredCompounds.length === 0 && (
                  <tr><td colSpan={5} className="empty">{loading ? "로딩 중…" : "검색 결과가 없습니다"}</td></tr>
                )}
              </tbody>
            </table>
          ) : tab === "stopword" ? (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>불용어</th>
                  <th>언어</th>
                  <th>등록일</th>
                  <th>상태</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {filteredStopwords.map((s) => (
                  <tr key={s.id}>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--down)", fontWeight: 600 }}>{s.word}</span></td>
                    <td><span className="chip info" style={{ fontSize: 10 }}>{s.language}</span></td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{s.createdAt?.slice(0, 10) ?? "—"}</td>
                    <td><span className="chip up">활성</span></td>
                    <td>
                      <button
                        disabled={busy === `del-s-${s.id}`}
                        onClick={() => void run(`del-s-${s.id}`, () => api.deleteStopword(s.id), `"${s.word}" 삭제됨`)}
                        className="table-action danger"
                      >
                        {busy === `del-s-${s.id}` ? "…" : "삭제"}
                      </button>
                    </td>
                  </tr>
                ))}
                {filteredStopwords.length === 0 && (
                  <tr><td colSpan={5} className="empty">{loading ? "로딩 중…" : "검색 결과가 없습니다"}</td></tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>후보어</th>
                  <th className="num">빈도</th>
                  <th className="num">문서 수</th>
                  <th>마지막 확인</th>
                  <th>상태</th>
                  <th>검토자</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map((c) => (
                  <tr key={c.id}>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--text)", fontWeight: 600 }}>{c.word}</span></td>
                    <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{c.frequency?.toLocaleString() ?? "—"}</td>
                    <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{c.docCount?.toLocaleString() ?? "—"}</td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{c.lastSeenAt?.slice(0, 10) ?? "—"}</td>
                    <td>
                      <span className={"chip " + (CANDIDATE_STATUS_CHIP[c.status] ?? "muted")} style={{ fontSize: 10 }}>
                        {CANDIDATE_STATUS_LABEL[c.status] ?? c.status}
                      </span>
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{c.reviewedBy ?? "—"}</td>
                    <td style={{ display: "flex", gap: 4 }}>
                      {c.status === "pending" && (
                        <>
                          <button
                            disabled={busy === `approve-${c.id}`}
                            onClick={() => void run(`approve-${c.id}`, () => api.approveCandidate(c.id), `"${c.word}" 승인됨`)}
                            className="table-action approve"
                          >
                            {busy === `approve-${c.id}` ? "…" : "승인"}
                          </button>
                          <button
                            disabled={busy === `reject-${c.id}`}
                            onClick={() => void run(`reject-${c.id}`, () => api.rejectCandidate(c.id), `"${c.word}" 반려됨`)}
                            className="table-action danger"
                          >
                            {busy === `reject-${c.id}` ? "…" : "반려"}
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
                {filteredCandidates.length === 0 && (
                  <tr><td colSpan={7} className="empty">{loading ? "로딩 중…" : "검색 결과가 없습니다"}</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "8px 20px", borderTop: "1px solid var(--border)", display: "flex", gap: 14, fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", background: "var(--bg-2)", alignItems: "center", flexShrink: 0 }}>
          {tab === "compound" && <span>전체 {filteredCompounds.length}건 (표시) / {data?.compoundNouns.length ?? 0}건 (전체)</span>}
          {tab === "stopword" && <span>전체 {filteredStopwords.length}건 (표시) / {data?.stopwords.length ?? 0}건 (전체)</span>}
          {tab === "candidates" && (
            <span>
              전체 {data?.compoundCandidates.length ?? 0}건 ·{" "}
              대기 {data?.compoundCandidates.filter((c) => c.status === "pending").length ?? 0} ·{" "}
              승인됨 {data?.compoundCandidates.filter((c) => c.status === "approved").length ?? 0}
            </span>
          )}
          <div style={{ flex: 1 }} />
          <span>변경사항은 다음 Spark 집계 주기(최대 5분)에 반영됩니다</span>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 32, left: "50%", transform: "translateX(-50%)",
          background: "var(--bg-1)", border: "1px solid var(--accent)", borderRadius: 8,
          padding: "10px 20px", fontSize: 12, color: "var(--text)", zIndex: 300,
          boxShadow: "0 8px 30px rgba(0,0,0,0.5)", fontFamily: "var(--font-mono)",
          whiteSpace: "nowrap",
        }}>{toast}</div>
      )}
    </div>
  );
}
