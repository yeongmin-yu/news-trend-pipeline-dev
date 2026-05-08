import { useEffect, useState } from "react";
import {
  api,
  type CompoundCandidateItem,
  type CompoundNounItem,
  type DictionaryMeta,
  type DictionaryPage as DictionaryPageData,
  type DomainOption,
  type StopwordCandidateItem,
  type StopwordItem,
} from "./data";
import { Icon, LoadingState } from "./ui";
import { Paginator } from "./dictionary/Paginator";
import { AddEntryForm } from "./dictionary/AddEntryForm";
import { CompoundTable } from "./dictionary/CompoundTable";
import { StopwordTable } from "./dictionary/StopwordTable";
import { CandidateTable } from "./dictionary/CandidateTable";
import { StopwordCandidateTable } from "./dictionary/StopwordCandidateTable";
import { HistoryTable } from "./dictionary/HistoryTable";
import { BackfillDialog } from "./dictionary/BackfillDialog";
import {
  CANDIDATE_STATUS_LABEL,
  DICTIONARY_PAGE_SIZE,
  SW_CANDIDATE_STATUS_LABEL,
  emptyDictionaryTabState,
  type BackfillDialogState,
  type DictionaryTabId,
  type DictionaryTabState,
  type HistoryItem,
} from "./dictionary/types";

function toDateTimeLocal(date: Date) {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function DictionaryPage() {
  const [tab, setTab] = useState<DictionaryTabId>("compound");
  const [meta, setMeta] = useState<DictionaryMeta | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);
  const [domains, setDomains] = useState<DomainOption[]>([]);

  const [compound, setCompound] = useState<DictionaryTabState<CompoundNounItem>>(emptyDictionaryTabState);
  const [stopword, setStopword] = useState<DictionaryTabState<StopwordItem>>(emptyDictionaryTabState);
  const [candidates, setCandidates] = useState<DictionaryTabState<CompoundCandidateItem>>(emptyDictionaryTabState);
  const [swCandidates, setSwCandidates] = useState<DictionaryTabState<StopwordCandidateItem>>(emptyDictionaryTabState);

  const [pages, setPages] = useState({ compound: 1, stopword: 1, candidates: 1, "stopword-candidates": 1 });
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
  const [backfillDialog, setBackfillDialog] = useState<{ item: CompoundNounItem; state: BackfillDialogState } | null>(null);

  const [history, setHistory] = useState<{ data: HistoryItem[]; loading: boolean; error: string | null }>({
    data: [],
    loading: false,
    error: null,
  });

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedQ(searchQ);
      setPages((p) => ({ ...p, [tab]: 1 }));
    }, 300);
    return () => clearTimeout(t);
  }, [searchQ, tab]);

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

  useEffect(() => {
    void loadMeta();
  }, []);

  useEffect(() => {
    if (tab !== "compound") return;
    let alive = true;
    setCompound((p) => ({ ...p, loading: true, error: null }));
    api
      .dictionaryCompoundNouns(pages.compound, DICTIONARY_PAGE_SIZE, debouncedQ, domainFilter !== "all" ? domainFilter : undefined)
      .then((data) => {
        if (alive) setCompound({ data, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (alive) setCompound((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" }));
      });
    return () => {
      alive = false;
    };
  }, [tab, pages.compound, debouncedQ, domainFilter]);

  useEffect(() => {
    if (tab !== "stopword") return;
    let alive = true;
    setStopword((p) => ({ ...p, loading: true, error: null }));
    api
      .dictionaryStopwords(pages.stopword, DICTIONARY_PAGE_SIZE, debouncedQ, domainFilter !== "all" ? domainFilter : undefined)
      .then((data) => {
        if (alive) setStopword({ data, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (alive) setStopword((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" }));
      });
    return () => {
      alive = false;
    };
  }, [tab, pages.stopword, debouncedQ, domainFilter]);

  useEffect(() => {
    if (tab !== "candidates") return;
    let alive = true;
    setCandidates((p) => ({ ...p, loading: true, error: null }));
    api
      .dictionaryCandidates(pages.candidates, DICTIONARY_PAGE_SIZE, debouncedQ, statusFilter, domainFilter !== "all" ? domainFilter : undefined)
      .then((data) => {
        if (alive) setCandidates({ data, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (alive) setCandidates((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" }));
      });
    return () => {
      alive = false;
    };
  }, [tab, pages.candidates, debouncedQ, statusFilter, domainFilter]);

  useEffect(() => {
    if (tab !== "stopword-candidates") return;
    let alive = true;
    setSwCandidates((p) => ({ ...p, loading: true, error: null }));
    api
      .dictionaryStopwordCandidates(pages["stopword-candidates"], DICTIONARY_PAGE_SIZE, debouncedQ, statusFilter, domainFilter !== "all" ? domainFilter : undefined)
      .then((data) => {
        if (alive) setSwCandidates({ data, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (alive) setSwCandidates((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" }));
      });
    return () => {
      alive = false;
    };
  }, [tab, pages["stopword-candidates"], debouncedQ, statusFilter, domainFilter]);

  useEffect(() => {
    if (tab !== "history") return;
    let alive = true;
    setHistory((prev) => ({ ...prev, loading: true, error: null }));
    fetch("/api/v1/dictionary/history?limit=200")
      .then((res) => {
        if (!res.ok) throw new Error("사전 변경 로그를 불러오지 못했습니다.");
        return res.json();
      })
      .then((data) => {
        if (alive) setHistory({ data: data.items ?? [], loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (alive) setHistory({ data: [], loading: false, error: err instanceof Error ? err.message : "오류" });
      });
    return () => {
      alive = false;
    };
  }, [tab]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2200);
  }

  function openBackfillDialog(item: CompoundNounItem) {
    const until = new Date();
    const since = new Date(until.getTime() - 30 * 24 * 60 * 60 * 1000);
    setBackfillDialog({
      item,
      state: {
        word: item.word,
        domain: item.domain ?? "all",
        since: toDateTimeLocal(since),
        until: toDateTimeLocal(until),
        dryRun: false,
      },
    });
  }

  async function submitBackfill() {
    if (!backfillDialog) return;
    setBusy("compound-backfill");
    setGlobalError(null);
    try {
      const result = await api.triggerCompoundBackfill({
        word: backfillDialog.state.word.trim(),
        domain: backfillDialog.state.domain,
        since: new Date(backfillDialog.state.since).toISOString(),
        until: new Date(backfillDialog.state.until).toISOString(),
        dryRun: backfillDialog.state.dryRun,
      });
      setBackfillDialog(null);
      showToast(`과거 데이터 재처리 DAG 실행됨: ${result.dagRunId}`);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "과거 데이터 재처리 DAG를 실행하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function reloadCurrentTab() {
    await loadMeta();
    type Setter<T> = (fn: (p: DictionaryTabState<T>) => DictionaryTabState<T>) => void;
    type Fetcher<T> = () => Promise<DictionaryPageData<T>>;
    const reset = <T,>(setter: Setter<T>, fetcher: Fetcher<T>) => {
      setter((p) => ({ ...p, loading: true }));
      fetcher()
        .then((data) => setter(() => ({ data, loading: false, error: null })))
        .catch((e: unknown) =>
          setter((p) => ({ ...p, loading: false, error: e instanceof Error ? e.message : "오류" })),
        );
    };
    const df = domainFilter !== "all" ? domainFilter : undefined;
    if (tab === "compound") reset(setCompound, () => api.dictionaryCompoundNouns(pages.compound, DICTIONARY_PAGE_SIZE, debouncedQ, df));
    if (tab === "stopword") reset(setStopword, () => api.dictionaryStopwords(pages.stopword, DICTIONARY_PAGE_SIZE, debouncedQ, df));
    if (tab === "candidates") reset(setCandidates, () => api.dictionaryCandidates(pages.candidates, DICTIONARY_PAGE_SIZE, debouncedQ, statusFilter, df));
    if (tab === "stopword-candidates")
      reset(setSwCandidates, () =>
        api.dictionaryStopwordCandidates(pages["stopword-candidates"], DICTIONARY_PAGE_SIZE, debouncedQ, statusFilter, df),
      );
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

  function switchTab(id: DictionaryTabId) {
    setTab(id);
    setShowAddForm(false);
    setStatusFilter("");
    setSearchQ("");
    setDebouncedQ("");
  }

  function setPage(t: string, p: number) {
    setPages((prev) => ({ ...prev, [t]: p }));
  }

  const activeError =
    tab === "compound" ? compound.error
    : tab === "stopword" ? stopword.error
    : tab === "candidates" ? candidates.error
    : tab === "stopword-candidates" ? swCandidates.error
    : history.error;
  const activeLoading =
    tab === "compound" ? compound.loading
    : tab === "stopword" ? stopword.loading
    : tab === "candidates" ? candidates.loading
    : tab === "stopword-candidates" ? swCandidates.loading
    : history.loading;

  const compoundTotal = debouncedQ
    ? compound.data?.total ?? meta?.compoundNounCount ?? 0
    : meta?.compoundNounCount ?? compound.data?.total ?? 0;
  const stopwordTotal = debouncedQ
    ? stopword.data?.total ?? meta?.stopwordCount ?? 0
    : meta?.stopwordCount ?? stopword.data?.total ?? 0;
  const candidateTotal = debouncedQ || statusFilter
    ? candidates.data?.total ?? meta?.candidateCount ?? 0
    : meta?.candidateCount ?? candidates.data?.total ?? 0;
  const swCandidateTotal = swCandidates.data?.total ?? 0;

  const domainOptions = domains.some((d) => d.id === "all")
    ? domains
    : [{ id: "all", label: "전체", available: true } as DomainOption, ...domains];

  const tabDefs: Array<[DictionaryTabId, string, number]> = [
    ["compound", "복합명사 사전", compoundTotal],
    ["stopword", "불용어 사전", stopwordTotal],
    ["candidates", "복합명사 후보", candidateTotal],
    ["stopword-candidates", "불용어 후보", swCandidateTotal],
    ["history", "사전 변경 로그", history.data.length],
  ];

  return (
    <div className="dict-page">
      {/* Header */}
      <div className="dict-page__header">
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>용어 사전 관리</div>
        {meta && (
          <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
            compound v{meta.versions.compoundNounDict} · stopword v{meta.versions.stopwordDict}
          </div>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={() => void reloadCurrentTab()}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            padding: "5px 10px",
            borderRadius: 5,
            border: "1px solid var(--border)",
            color: "var(--text-3)",
            fontSize: 11,
            background: "transparent",
            cursor: "pointer",
          }}
        >
          <Icon.Refresh size={12} />
          새로고침
        </button>
      </div>

      {/* Tabs */}
      <div className="dict-page__tabs">
        {tabDefs.map(([id, label, count]) => (
          <button
            key={id}
            onClick={() => switchTab(id)}
            className={tab === id ? "is-active" : ""}
          >
            {label}
            {!metaLoading && (
              <span
                style={{
                  fontSize: 11,
                  padding: "1px 5px",
                  borderRadius: 9,
                  background: "var(--bg-3)",
                  color: "var(--text-3)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Filter bar */}
      <div className="dict-page__filterbar">
        <div className="field" style={{ gap: 6 }}>
          <Icon.Search size={12} />
          <input
            placeholder="검색…"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            style={{ width: 160, fontSize: 12 }}
          />
        </div>
        <div className="seg">
          {domainOptions.map((d) => (
            <button
              key={d.id}
              className={domainFilter === d.id ? "is-active" : ""}
              onClick={() => {
                setDomainFilter(d.id);
                setPages((p) => ({ ...p, [tab]: 1 }));
              }}
              style={{ fontSize: 11 }}
            >
              {d.label}
            </button>
          ))}
        </div>
        {tab === "candidates" && (
          <div className="seg">
            {(["", "needs_review", "approved", "rejected"] as const).map((v) => (
              <button
                key={v}
                className={statusFilter === v ? "is-active" : ""}
                onClick={() => {
                  setStatusFilter(v);
                  setPages((p) => ({ ...p, candidates: 1 }));
                }}
                style={{ fontSize: 11 }}
              >
                {v === "" ? "전체" : CANDIDATE_STATUS_LABEL[v] ?? v}
              </button>
            ))}
          </div>
        )}
        {tab === "stopword-candidates" && (
          <div className="seg">
            {(["", "needs_review", "approved", "rejected"] as const).map((v) => (
              <button
                key={v}
                className={statusFilter === v ? "is-active" : ""}
                onClick={() => {
                  setStatusFilter(v);
                  setPages((p) => ({ ...p, "stopword-candidates": 1 }));
                }}
                style={{ fontSize: 11 }}
              >
                {v === "" ? "전체" : SW_CANDIDATE_STATUS_LABEL[v] ?? v}
              </button>
            ))}
          </div>
        )}
        <div style={{ flex: 1 }} />
        {tab !== "candidates" && tab !== "stopword-candidates" && tab !== "history" && (
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            style={{
              padding: "5px 12px",
              borderRadius: 5,
              border: "1px solid var(--accent)",
              color: "var(--accent)",
              fontSize: 11,
              fontFamily: "var(--font-mono)",
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
        <AddEntryForm
          kind="compound"
          word={editWord}
          setWord={setEditWord}
          domain={editDomain}
          setDomain={setEditDomain}
          domains={domains}
          busy={busy === "create-compound"}
          onSubmit={() => {
            if (!editWord.trim()) return;
            void run(
              "create-compound",
              async () => {
                await api.createCompound(editWord.trim(), editDomain);
                setEditWord("");
                setEditDomain("all");
                setShowAddForm(false);
              },
              `"${editWord.trim()}" 복합명사 등록 완료`,
            );
          }}
        />
      )}
      {showAddForm && tab === "stopword" && (
        <AddEntryForm
          kind="stopword"
          word={editWord}
          setWord={setEditWord}
          domain={editDomain}
          setDomain={setEditDomain}
          domains={domains}
          busy={busy === "create-stopword"}
          onSubmit={() => {
            if (!editWord.trim()) return;
            void run(
              "create-stopword",
              async () => {
                await api.createStopword(editWord.trim(), editDomain);
                setEditWord("");
                setEditDomain("all");
                setShowAddForm(false);
              },
              `"${editWord.trim()}" 불용어 등록 완료`,
            );
          }}
        />
      )}

      {/* Error bar */}
      {(globalError ?? activeError) && (
        <div
          style={{
            padding: "8px 20px",
            color: "var(--down)",
            fontSize: 11,
            background: "var(--down-weak)",
            borderBottom: "1px solid var(--down)",
            fontFamily: "var(--font-mono)",
            flexShrink: 0,
          }}
        >
          {globalError ?? activeError}
        </div>
      )}

      {/* Table area */}
      <div className="dict-page__body">
        {activeLoading && !compound.data && !stopword.data && !candidates.data && !swCandidates.data && tab !== "history" ? (
          <LoadingState label="사전 데이터를 불러오는 중..." />
        ) : tab === "compound" ? (
          <CompoundTable
            items={compound.data?.items ?? []}
            domains={domains}
            busy={busy}
            loading={compound.loading}
            onUpdateDomain={(id, d) =>
              void run(`domain-c-${id}`, () => api.updateCompoundDomain(id, d), `도메인 변경 완료`)
            }
            onDelete={(item) =>
              void run(`del-c-${item.id}`, () => api.deleteCompound(item.id), `"${item.word}" 삭제됨`)
            }
            onBackfill={openBackfillDialog}
          />
        ) : tab === "stopword" ? (
          <StopwordTable
            items={stopword.data?.items ?? []}
            domains={domains}
            busy={busy}
            loading={stopword.loading}
            onUpdateDomain={(id, d) =>
              void run(`domain-s-${id}`, () => api.updateStopwordDomain(id, d), `도메인 변경 완료`)
            }
            onDelete={(item) =>
              void run(`del-s-${item.id}`, () => api.deleteStopword(item.id), `"${item.word}" 삭제됨`)
            }
          />
        ) : tab === "candidates" ? (
          <CandidateTable
            items={candidates.data?.items ?? []}
            domains={domains}
            busy={busy}
            loading={candidates.loading}
            onApprove={(item) =>
              void run(`approve-${item.id}`, () => api.approveCandidate(item.id), `"${item.word}" 승인됨`)
            }
            onReject={(item) =>
              void run(`reject-${item.id}`, () => api.rejectCandidate(item.id), `"${item.word}" 반려됨`)
            }
          />
        ) : tab === "history" ? (
          <HistoryTable items={history.data} loading={history.loading} />
        ) : (
          <StopwordCandidateTable
            items={swCandidates.data?.items ?? []}
            busy={busy}
            loading={swCandidates.loading}
            onApprove={(item) =>
              void run(
                `approve-sw-${item.id}`,
                () => api.approveStopwordCandidate(item.id),
                `"${item.word}" 불용어 승인됨`,
              )
            }
            onReject={(item) =>
              void run(`reject-sw-${item.id}`, () => api.rejectStopwordCandidate(item.id), `"${item.word}" 반려됨`)
            }
          />
        )}
      </div>

      {/* Footer */}
      <div className="dict-page__footer">
        {tab === "compound" && (
          <>
            <span>{compound.data ? `${compound.data.total.toLocaleString()}건 전체 · ${pages.compound}페이지` : "—"}</span>
            <Paginator
              page={pages.compound}
              total={compound.data?.total ?? 0}
              limit={DICTIONARY_PAGE_SIZE}
              onChange={(p) => setPage("compound", p)}
            />
          </>
        )}
        {tab === "stopword" && (
          <>
            <span>{stopword.data ? `${stopword.data.total.toLocaleString()}건 전체 · ${pages.stopword}페이지` : "—"}</span>
            <Paginator
              page={pages.stopword}
              total={stopword.data?.total ?? 0}
              limit={DICTIONARY_PAGE_SIZE}
              onChange={(p) => setPage("stopword", p)}
            />
          </>
        )}
        {tab === "candidates" && (
          <>
            <span>
              {candidates.data ? `${candidates.data.total.toLocaleString()}건 전체 · ${pages.candidates}페이지` : "—"}
            </span>
            <Paginator
              page={pages.candidates}
              total={candidates.data?.total ?? 0}
              limit={DICTIONARY_PAGE_SIZE}
              onChange={(p) => setPage("candidates", p)}
            />
          </>
        )}
        {tab === "stopword-candidates" && (
          <>
            <span>
              {swCandidates.data
                ? `${swCandidates.data.total.toLocaleString()}건 전체 · ${pages["stopword-candidates"]}페이지`
                : "—"}
            </span>
            <Paginator
              page={pages["stopword-candidates"]}
              total={swCandidates.data?.total ?? 0}
              limit={DICTIONARY_PAGE_SIZE}
              onChange={(p) => setPage("stopword-candidates", p)}
            />
          </>
        )}
        <div style={{ flex: 1 }} />
        <span>변경사항은 다음 Spark 집계 주기(최대 5분)에 반영됩니다</span>
      </div>

      {backfillDialog && (
        <BackfillDialog
          item={backfillDialog.item}
          state={backfillDialog.state}
          setState={(next) => setBackfillDialog((p) => (p ? { ...p, state: next } : p))}
          domains={domains}
          busy={busy}
          onClose={() => setBackfillDialog(null)}
          onSubmit={() => void submitBackfill()}
        />
      )}

      {toast && (
        <div
          style={{
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
          }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}
