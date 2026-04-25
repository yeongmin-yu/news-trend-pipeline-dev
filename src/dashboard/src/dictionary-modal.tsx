import { useEffect, useRef, useState } from "react";
import {
  api,
  type CompoundCandidateItem,
  type CompoundNounItem,
  type DictionaryMeta,
  type DictionaryPage,
  type DomainOption,
  type StopwordItem,
} from "./data";
import { Icon, LoadingState } from "./ui";

type TabId = "compound" | "stopword" | "candidates";

const PAGE_SIZE = 50;

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

const DOMAIN_LABEL: Record<string, string> = { all: "전체" };

interface TabState<T> {
  data: DictionaryPage<T> | null;
  loading: boolean;
  error: string | null;
}

function emptyTab<T>(): TabState<T> {
  return { data: null, loading: false, error: null };
}

function Paginator({
  page,
  total,
  limit,
  onChange,
}: {
  page: number;
  total: number;
  limit: number;
  onChange: (p: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  if (totalPages <= 1) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)" }}>
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        style={{ padding: "3px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "transparent", color: page <= 1 ? "var(--text-4)" : "var(--text-2)", cursor: page <= 1 ? "default" : "pointer", fontSize: 11 }}
      >
        ← 이전
      </button>
      <span style={{ color: "var(--text-3)" }}>
        {page} / {totalPages}
      </span>
      <button
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        style={{ padding: "3px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "transparent", color: page >= totalPages ? "var(--text-4)" : "var(--text-2)", cursor: page >= totalPages ? "default" : "pointer", fontSize: 11 }}
      >
        다음 →
      </button>
    </div>
  );
}

function DomainBadge({ domain, domains, itemId, onUpdate }: {
  domain: string;
  domains: DomainOption[];
  itemId: number;
  onUpdate: (id: number, newDomain: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const label = domains.find((d) => d.id === domain)?.label ?? DOMAIN_LABEL[domain] ?? domain;

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen(!open)}
        title="도메인 변경"
        style={{
          padding: "2px 8px",
          borderRadius: 4,
          border: "1px solid var(--border)",
          background: domain === "all" ? "var(--bg-3)" : "var(--accent-weak)",
          color: domain === "all" ? "var(--text-3)" : "var(--accent)",
          fontSize: 10,
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
        }}
      >
        {label} ▾
      </button>
      {open && (
        <div style={{
          position: "absolute",
          top: "100%",
          left: 0,
          zIndex: 400,
          background: "var(--bg-1)",
          border: "1px solid var(--border-hi)",
          borderRadius: 6,
          minWidth: 130,
          boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
          marginTop: 2,
        }}>
          {[{ id: "all", label: "전체 (공통)" }, ...domains].map((d) => (
            <button
              key={d.id}
              onClick={() => { onUpdate(itemId, d.id); setOpen(false); }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "7px 12px",
                fontSize: 11,
                background: d.id === domain ? "var(--accent-weak)" : "transparent",
                color: d.id === domain ? "var(--accent)" : "var(--text-2)",
                border: "none",
                cursor: "pointer",
                fontFamily: "var(--font-mono)",
              }}
            >
              {d.label ?? d.id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function DictionaryApiModal({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<TabId>("compound");
  const [meta, setMeta] = useState<DictionaryMeta | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);
  const [domains, setDomains] = useState<DomainOption[]>([]);

  const [compound, setCompound] = useState<TabState<CompoundNounItem>>(emptyTab);
  const [stopword, setStopword] = useState<TabState<StopwordItem>>(emptyTab);
  const [candidates, setCandidates] = useState<TabState<CompoundCandidateItem>>(emptyTab);

  const [pages, setPages] = useState({ compound: 1, stopword: 1, candidates: 1 });
  const [searchQ, setSearchQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");

  const [busy, setBusy] = useState<string | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editWord, setEditWord] = useState("");
  const [editDomain, setEditDomain] = useState("all");
  const [toast, setToast] = useState<string | null>(null);

  // debounce search
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedQ(searchQ);
      setPages((p) => ({ ...p, [tab]: 1 }));
    }, 300);
    return () => clearTimeout(t);
  }, [searchQ, tab]);

  // load meta + domains
  async function loadMeta() {
    setMetaLoading(true);
    try {
      const [metaData, filtersData] = await Promise.all([api.dictionaryMeta(), api.filters()]);
      setMeta(metaData);
      setDomains(filtersData.domains);
    } finally {
      setMetaLoading(false);
    }
  }

  useEffect(() => { void loadMeta(); }, []);

  // load compound nouns
  useEffect(() => {
    if (tab !== "compound") return;
    let alive = true;
    setCompound((p) => ({ ...p, loading: true, error: null }));
    api.dictionaryCompoundNouns(pages.compound, PAGE_SIZE, debouncedQ, domainFilter !== "all" ? domainFilter : undefined)
      .then((data) => { if (alive) setCompound({ data, loading: false, error: null }); })
      .catch((e: unknown) => { if (alive) setCompound((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" })); });
    return () => { alive = false; };
  }, [tab, pages.compound, debouncedQ, domainFilter]);

  // load stopwords
  useEffect(() => {
    if (tab !== "stopword") return;
    let alive = true;
    setStopword((p) => ({ ...p, loading: true, error: null }));
    api.dictionaryStopwords(pages.stopword, PAGE_SIZE, debouncedQ, domainFilter !== "all" ? domainFilter : undefined)
      .then((data) => { if (alive) setStopword({ data, loading: false, error: null }); })
      .catch((e: unknown) => { if (alive) setStopword((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" })); });
    return () => { alive = false; };
  }, [tab, pages.stopword, debouncedQ, domainFilter]);

  // load candidates
  useEffect(() => {
    if (tab !== "candidates") return;
    let alive = true;
    setCandidates((p) => ({ ...p, loading: true, error: null }));
    api.dictionaryCandidates(pages.candidates, PAGE_SIZE, debouncedQ, statusFilter, domainFilter !== "all" ? domainFilter : undefined)
      .then((data) => { if (alive) setCandidates({ data, loading: false, error: null }); })
      .catch((e: unknown) => { if (alive) setCandidates((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" })); });
    return () => { alive = false; };
  }, [tab, pages.candidates, debouncedQ, statusFilter, domainFilter]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2200);
  }

  async function reloadCurrentTab() {
    await loadMeta();
    const reset = (setter: typeof setCompound | typeof setStopword | typeof setCandidates, fetcher: () => Promise<DictionaryPage<CompoundNounItem | StopwordItem | CompoundCandidateItem>>) => {
      setter((p) => ({ ...p, loading: true }));
      fetcher()
        .then((data) => setter({ data: data as never, loading: false, error: null }))
        .catch((e: unknown) => setter((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" })));
    };
    const df = domainFilter !== "all" ? domainFilter : undefined;
    if (tab === "compound") reset(setCompound as never, () => api.dictionaryCompoundNouns(pages.compound, PAGE_SIZE, debouncedQ, df));
    if (tab === "stopword") reset(setStopword as never, () => api.dictionaryStopwords(pages.stopword, PAGE_SIZE, debouncedQ, df));
    if (tab === "candidates") reset(setCandidates as never, () => api.dictionaryCandidates(pages.candidates, PAGE_SIZE, debouncedQ, statusFilter, df));
  }

  async function run(key: string, action: () => Promise<unknown>, successMsg: string) {
    setBusy(key);
    setGlobalError(null);
    try {
      await action();
      await reloadCurrentTab();
      showToast(successMsg);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "요청을 처리하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  function switchTab(id: TabId) {
    setTab(id);
    setShowAddForm(false);
    setStatusFilter("");
    setSearchQ("");
  }

  function setPage(t: TabId, p: number) {
    setPages((prev) => ({ ...prev, [t]: p }));
  }

  const activeError = tab === "compound" ? compound.error : tab === "stopword" ? stopword.error : candidates.error;
  const activeLoading = tab === "compound" ? compound.loading : tab === "stopword" ? stopword.loading : candidates.loading;

  // badge counts
  const compoundTotal = debouncedQ ? (compound.data?.total ?? meta?.compoundNounCount ?? 0) : (meta?.compoundNounCount ?? compound.data?.total ?? 0);
  const stopwordTotal = debouncedQ ? (stopword.data?.total ?? meta?.stopwordCount ?? 0) : (meta?.stopwordCount ?? stopword.data?.total ?? 0);
  const candidateTotal = (debouncedQ || statusFilter) ? (candidates.data?.total ?? meta?.candidateCount ?? 0) : (meta?.candidateCount ?? candidates.data?.total ?? 0);

  const domainOptions = [{ id: "all", label: "전체", available: true }, ...domains];

  return (
    <div
      style={{ position: "fixed", inset: 0, zIndex: 200, background: "rgba(0,0,0,0.7)", backdropFilter: "blur(6px)", display: "flex", flexDirection: "column" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{ margin: "32px auto", width: "min(1280px, 96vw)", height: "calc(100vh - 64px)", background: "var(--bg-1)", border: "1px solid var(--border-hi)", borderRadius: 10, display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 32px 80px rgba(0,0,0,0.6)" }}
      >
        {/* Header */}
        <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 16, background: "var(--bg-2)", flexShrink: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>용어 사전 관리</div>
          {meta && (
            <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
              compound v{meta.versions.compoundNounDict} · stopword v{meta.versions.stopwordDict}
            </div>
          )}
          <div style={{ flex: 1 }} />
          <button
            onClick={() => void reloadCurrentTab()}
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
            ["compound", "복합명사 사전", compoundTotal],
            ["stopword", "불용어 사전", stopwordTotal],
            ["candidates", "복합명사 후보", candidateTotal],
          ] as const).map(([id, label, count]) => (
            <button
              key={id}
              onClick={() => switchTab(id)}
              style={{ padding: "10px 18px", fontSize: 12, fontWeight: 500, borderBottom: tab === id ? "2px solid var(--accent)" : "2px solid transparent", color: tab === id ? "var(--text)" : "var(--text-3)", marginBottom: -1, background: "transparent", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
            >
              {label}
              {!metaLoading && (
                <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 9, background: "var(--bg-3)", color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Filter bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--bg)", flexShrink: 0, flexWrap: "wrap" }}>
          <div className="field" style={{ gap: 6 }}>
            <Icon.Search size={12} />
            <input
              placeholder="검색…"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              style={{ width: 160, fontSize: 12 }}
            />
          </div>
          {/* Domain filter */}
          <div className="seg">
            {domainOptions.map((d) => (
              <button
                key={d.id}
                className={domainFilter === d.id ? "is-active" : ""}
                onClick={() => { setDomainFilter(d.id); setPages((p) => ({ ...p, [tab]: 1 })); }}
                style={{ fontSize: 11 }}
              >
                {d.label}
              </button>
            ))}
          </div>
          {tab === "candidates" && (
            <div className="seg">
              {(["", "pending", "approved", "rejected"] as const).map((v) => (
                <button
                  key={v}
                  className={statusFilter === v ? "is-active" : ""}
                  onClick={() => { setStatusFilter(v); setPages((p) => ({ ...p, candidates: 1 })); }}
                  style={{ fontSize: 11 }}
                >
                  {v === "" ? "전체" : CANDIDATE_STATUS_LABEL[v] ?? v}
                </button>
              ))}
            </div>
          )}
          <div style={{ flex: 1 }} />
          {tab !== "candidates" && (
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              style={{ padding: "5px 12px", borderRadius: 5, border: "1px solid var(--accent)", color: "var(--accent)", fontSize: 11, fontFamily: "var(--font-mono)", background: showAddForm ? "var(--accent-weak)" : "transparent", cursor: "pointer" }}
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
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
              도메인
              <select
                value={editDomain}
                onChange={(e) => setEditDomain(e.target.value)}
                style={{ padding: "5px 8px", background: "var(--bg-3)", border: "1px solid var(--border-hi)", borderRadius: 4, color: "var(--text)", fontSize: 12, outline: "none" }}
              >
                <option value="all">전체 (공통)</option>
                {domains.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
              </select>
            </label>
            <button
              id="dict-add-btn"
              disabled={!editWord.trim() || busy === "create-compound"}
              onClick={() =>
                void run("create-compound", async () => {
                  await api.createCompound(editWord.trim(), editDomain);
                  setEditWord(""); setEditDomain("all"); setShowAddForm(false);
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
            <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
              도메인
              <select
                value={editDomain}
                onChange={(e) => setEditDomain(e.target.value)}
                style={{ padding: "5px 8px", background: "var(--bg-3)", border: "1px solid var(--border-hi)", borderRadius: 4, color: "var(--text)", fontSize: 12, outline: "none" }}
              >
                <option value="all">전체 (공통)</option>
                {domains.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
              </select>
            </label>
            <button
              id="dict-add-btn"
              disabled={!editWord.trim() || busy === "create-stopword"}
              onClick={() =>
                void run("create-stopword", async () => {
                  await api.createStopword(editWord.trim(), editDomain);
                  setEditWord(""); setEditDomain("all"); setShowAddForm(false);
                }, `"${editWord.trim()}" 불용어 등록 완료`)
              }
              style={{ padding: "6px 16px", background: "var(--accent)", color: "#061617", borderRadius: 5, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", opacity: !editWord.trim() ? 0.5 : 1 }}
            >
              {busy === "create-stopword" ? "등록 중…" : "등록"}
            </button>
          </div>
        )}

        {/* Error bar */}
        {(globalError ?? activeError) && (
          <div style={{ padding: "8px 20px", color: "var(--down)", fontSize: 11, background: "var(--down-weak)", borderBottom: "1px solid var(--down)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
            {globalError ?? activeError}
          </div>
        )}

        {/* Table area */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {activeLoading && !compound.data && !stopword.data && !candidates.data ? (
            <LoadingState label="사전 데이터를 불러오는 중..." />
          ) : tab === "compound" ? (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>복합명사</th>
                  <th>도메인</th>
                  <th>출처</th>
                  <th>등록일</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {(compound.data?.items ?? []).map((c) => (
                  <tr key={c.id}>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 600 }}>{c.word}</span></td>
                    <td>
                      <DomainBadge
                        domain={c.domain ?? "all"}
                        domains={domains}
                        itemId={c.id}
                        onUpdate={(id, d) => void run(`domain-c-${id}`, () => api.updateCompoundDomain(id, d), `도메인 변경 완료`)}
                      />
                    </td>
                    <td><span className="chip muted" style={{ fontSize: 10 }}>{c.source}</span></td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{c.createdAt?.slice(0, 16).replace("T", " ") ?? "—"}</td>
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
                {!activeLoading && (compound.data?.items.length ?? 0) === 0 && (
                  <tr><td colSpan={5} className="empty">검색 결과가 없습니다</td></tr>
                )}
              </tbody>
            </table>
          ) : tab === "stopword" ? (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>불용어</th>
                  <th>도메인</th>
                  <th>언어</th>
                  <th>등록일</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {(stopword.data?.items ?? []).map((s) => (
                  <tr key={s.id}>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--down)", fontWeight: 600 }}>{s.word}</span></td>
                    <td>
                      <DomainBadge
                        domain={s.domain ?? "all"}
                        domains={domains}
                        itemId={s.id}
                        onUpdate={(id, d) => void run(`domain-s-${id}`, () => api.updateStopwordDomain(id, d), `도메인 변경 완료`)}
                      />
                    </td>
                    <td><span className="chip info" style={{ fontSize: 10 }}>{s.language}</span></td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>{s.createdAt?.slice(0, 10) ?? "—"}</td>
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
                {!activeLoading && (stopword.data?.items.length ?? 0) === 0 && (
                  <tr><td colSpan={5} className="empty">검색 결과가 없습니다</td></tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>후보어</th>
                  <th>도메인</th>
                  <th className="num">빈도</th>
                  <th className="num">문서 수</th>
                  <th>마지막 확인</th>
                  <th>상태</th>
                  <th>검토자</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {(candidates.data?.items ?? []).map((c) => (
                  <tr key={c.id}>
                    <td><span style={{ fontFamily: "var(--font-mono)", color: "var(--text)", fontWeight: 600 }}>{c.word}</span></td>
                    <td>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: 4,
                          border: "1px solid var(--border)",
                          background: (c.domain ?? "all") === "all" ? "var(--bg-3)" : "var(--accent-weak)",
                          color: (c.domain ?? "all") === "all" ? "var(--text-3)" : "var(--accent)",
                          fontSize: 10,
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {domains.find((d) => d.id === c.domain)?.label ?? (c.domain === "all" || !c.domain ? "전체" : c.domain)}
                      </span>
                    </td>
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
                {!activeLoading && (candidates.data?.items.length ?? 0) === 0 && (
                  <tr><td colSpan={8} className="empty">검색 결과가 없습니다</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "8px 20px", borderTop: "1px solid var(--border)", display: "flex", gap: 14, fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", background: "var(--bg-2)", alignItems: "center", flexShrink: 0 }}>
          {tab === "compound" && (
            <>
              <span>
                {compound.data ? `${compound.data.total.toLocaleString()}건 전체 · ${pages.compound}페이지` : "—"}
              </span>
              <Paginator page={pages.compound} total={compound.data?.total ?? 0} limit={PAGE_SIZE} onChange={(p) => setPage("compound", p)} />
            </>
          )}
          {tab === "stopword" && (
            <>
              <span>
                {stopword.data ? `${stopword.data.total.toLocaleString()}건 전체 · ${pages.stopword}페이지` : "—"}
              </span>
              <Paginator page={pages.stopword} total={stopword.data?.total ?? 0} limit={PAGE_SIZE} onChange={(p) => setPage("stopword", p)} />
            </>
          )}
          {tab === "candidates" && (
            <>
              <span>
                {candidates.data ? `${candidates.data.total.toLocaleString()}건 전체 · ${pages.candidates}페이지` : "—"}
              </span>
              <Paginator page={pages.candidates} total={candidates.data?.total ?? 0} limit={PAGE_SIZE} onChange={(p) => setPage("candidates", p)} />
            </>
          )}
          <div style={{ flex: 1 }} />
          <span>변경사항은 다음 Spark 집계 주기(최대 5분)에 반영됩니다</span>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{ position: "fixed", bottom: 32, left: "50%", transform: "translateX(-50%)", background: "var(--bg-1)", border: "1px solid var(--accent)", borderRadius: 8, padding: "10px 20px", fontSize: 12, color: "var(--text)", zIndex: 300, boxShadow: "0 8px 30px rgba(0,0,0,0.5)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
          {toast}
        </div>
      )}
    </div>
  );
}
