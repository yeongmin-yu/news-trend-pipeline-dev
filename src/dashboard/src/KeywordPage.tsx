import { useEffect, useMemo, useState } from "react";
import {
  api,
  type DomainOption,
  type QueryKeywordAdminOverview,
  type QueryKeywordItem,
} from "./data";
import { Icon, LoadingState } from "./ui";
import { KeywordForm } from "./keyword/KeywordForm";
import { KeywordTable } from "./keyword/KeywordTable";
import { MetricsTable } from "./keyword/MetricsTable";
import { LogsTable } from "./keyword/LogsTable";
import { EMPTY_KEYWORD_FORM, type KeywordFormState, type KeywordTabId } from "./keyword/types";

export function KeywordPage() {
  const [tab, setTab] = useState<KeywordTabId>("keywords");
  const [data, setData] = useState<QueryKeywordAdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [domainFilter, setDomainFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<KeywordFormState>(EMPTY_KEYWORD_FORM);
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
      setForm(EMPTY_KEYWORD_FORM);
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청을 처리하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  const domains: DomainOption[] = useMemo(() => data?.domains ?? [], [data]);
  const filteredKeywords = useMemo(() => {
    return (data?.queryKeywords ?? []).filter((item) => {
      const domainMatched = domainFilter === "all" || item.domainId === domainFilter;
      const searchMatched = !search || item.query.toLowerCase().includes(search.toLowerCase());
      return domainMatched && searchMatched;
    });
  }, [data, domainFilter, search]);

  const filteredMetrics = useMemo(() => {
    return (data?.collectionMetrics ?? []).filter(
      (item) => domainFilter === "all" || item.domain === domainFilter,
    );
  }, [data, domainFilter]);

  const filteredLogs = useMemo(() => {
    return (data?.auditLogs ?? []).filter((item) => {
      if (domainFilter === "all") return true;
      const afterDomain =
        item.afterJson && typeof item.afterJson["domainId"] === "string"
          ? String(item.afterJson["domainId"])
          : null;
      const beforeDomain =
        item.beforeJson && typeof item.beforeJson["domainId"] === "string"
          ? String(item.beforeJson["domainId"])
          : null;
      return afterDomain === domainFilter || beforeDomain === domainFilter;
    });
  }, [data, domainFilter]);

  function startEdit(item: QueryKeywordItem) {
    setForm({
      id: item.id,
      domainId: item.domainId,
      query: item.query,
      sortOrder: item.sortOrder,
      isActive: item.isActive,
    });
  }

  function submitForm() {
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
    );
  }

  return (
    <div className="dict-page">
      <div className="dict-page__header">
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>키워드 관리</div>
        <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
          naver queries {data?.queryKeywords.length ?? 0}
        </div>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => void load()}
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

      <div className="dict-page__tabs">
        {(
          [
            ["keywords", "쿼리 키워드"],
            ["metrics", "수집 지표"],
            ["logs", "변경 로그"],
          ] as const
        ).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} className={tab === id ? "is-active" : ""}>
            {label}
          </button>
        ))}
      </div>

      <div className="dict-page__filterbar">
        <div className="field" style={{ gap: 6 }}>
          <Icon.Search size={12} />
          <input
            placeholder="키워드 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 180, fontSize: 12 }}
          />
        </div>
        <div className="seg">
          <button
            className={domainFilter === "all" ? "is-active" : ""}
            onClick={() => setDomainFilter("all")}
          >
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
        <KeywordForm
          form={form}
          setForm={setForm}
          domains={domains}
          busy={busy === "save-query"}
          onSubmit={submitForm}
          onReset={() => setForm(EMPTY_KEYWORD_FORM)}
        />
      )}

      {error && (
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
          {error}
        </div>
      )}

      <div className="dict-page__body">
        {loading && !data ? (
          <LoadingState label="도메인 키워드 데이터를 불러오는 중..." />
        ) : tab === "keywords" ? (
          <KeywordTable
            items={filteredKeywords}
            onEdit={startEdit}
            onToggleActive={(item) =>
              void run(
                `toggle-${item.id}`,
                () =>
                  api.updateQueryKeyword(item.id, {
                    domainId: item.domainId,
                    query: item.query,
                    sortOrder: item.sortOrder,
                    isActive: !item.isActive,
                  }),
                item.isActive ? "키워드를 비활성화했습니다." : "키워드를 활성화했습니다.",
              )
            }
            onDelete={(item) =>
              void run(`delete-${item.id}`, () => api.deleteQueryKeyword(item.id), "키워드를 삭제했습니다.")
            }
          />
        ) : tab === "metrics" ? (
          <MetricsTable items={filteredMetrics} domains={domains} />
        ) : (
          <LogsTable items={filteredLogs} />
        )}
      </div>

      <div className="dict-page__footer">
        <span>도메인별 네이버 수집 키워드와 최근 24시간 지표를 함께 관리합니다.</span>
        <div style={{ flex: 1 }} />
        <span>변경 즉시 DB에 반영되며 다음 수집 주기부터 적용됩니다.</span>
      </div>

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
