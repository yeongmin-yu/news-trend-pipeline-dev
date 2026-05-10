import type { CompoundCandidateItem, DomainOption } from "../data";
import {
  AUTO_DECISION_CHIP,
  AUTO_DECISION_LABEL,
  CANDIDATE_STATUS_CHIP,
  CANDIDATE_STATUS_LABEL,
  renderAutoEvidence,
} from "./types";

interface Props {
  items: CompoundCandidateItem[];
  domains: DomainOption[];
  busy: string | null;
  loading: boolean;
  onApprove: (item: CompoundCandidateItem) => void;
  onReject: (item: CompoundCandidateItem) => void;
}

function DomainChip({ domain, domains }: { domain: string; domains: DomainOption[] }) {
  const isAll = domain === "all" || !domain;
  const label = domains.find((d) => d.id === domain)?.label ?? (isAll ? "전체" : domain);
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 4,
        border: "1px solid var(--border)",
        background: isAll ? "var(--bg-3)" : "var(--accent-weak)",
        color: isAll ? "var(--text-3)" : "var(--accent)",
        fontSize: 11,
        fontFamily: "var(--font-mono)",
      }}
    >
      {label}
    </span>
  );
}

export function CandidateTable({ items, domains, busy, loading, onApprove, onReject }: Props) {
  return (
    <table className="table" style={{ fontSize: 12 }}>
      <thead>
        <tr>
          <th>후보어</th>
          <th>도메인</th>
          <th className="num">빈도</th>
          <th className="num">문서 수</th>
          <th>마지막 확인</th>
          <th>상태</th>
          <th>자동판정</th>
          <th>판단근거</th>
          <th>평가시각</th>
          <th>검토자</th>
          <th>작업</th>
        </tr>
      </thead>
      <tbody>
        {items.map((c) => (
          <tr key={c.id}>
            <td>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)", fontWeight: 600 }}>{c.word}</span>
            </td>
            <td>
              <DomainChip domain={c.domain ?? "all"} domains={domains} />
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {c.frequency?.toLocaleString() ?? "—"}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {c.docCount?.toLocaleString() ?? "—"}
            </td>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 11 }}>
              {c.lastSeenAt?.slice(0, 10) ?? "—"}
            </td>
            <td>
              <span className={"chip " + (CANDIDATE_STATUS_CHIP[c.status] ?? "muted")} style={{ fontSize: 11 }}>
                {CANDIDATE_STATUS_LABEL[c.status] ?? c.status}
              </span>
            </td>
            <td>
              {c.autoDecision ? (
                <span className={"chip " + (AUTO_DECISION_CHIP[c.autoDecision] ?? "muted")} style={{ fontSize: 11 }}>
                  {AUTO_DECISION_LABEL[c.autoDecision] ?? c.autoDecision}
                </span>
              ) : (
                <span style={{ color: "var(--text-4)", fontSize: 11 }}>—</span>
              )}
            </td>
            <td style={{ minWidth: 220, maxWidth: 320 }}>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-2)",
                  fontFamily: "var(--font-mono)",
                  whiteSpace: "nowrap",
                }}
              >
                {renderAutoEvidence(c)}
              </div>
              {c.autoEvidenceSummary?.matchedTitle && (
                <div
                  title={c.autoEvidenceSummary.matchedTitle}
                  style={{
                    marginTop: 2,
                    fontSize: 10,
                    color: "var(--text-4)",
                    maxWidth: 300,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c.autoEvidenceSummary?.matchedLink ? (
                    <a
                      href={c.autoEvidenceSummary.matchedLink}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: "inherit", textDecoration: "underline" }}
                    >
                      {c.autoEvidenceSummary.matchedTitle}
                    </a>
                  ) : (
                    c.autoEvidenceSummary.matchedTitle
                  )}
                </div>
              )}
            </td>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 11 }}>
              {c.autoCheckedAt?.slice(0, 16).replace("T", " ") ?? "—"}
            </td>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 11 }}>
              {c.reviewedBy ?? "—"}
            </td>
            <td style={{ display: "flex", gap: 4 }}>
              {c.status === "needs_review" && (
                <>
                  <button
                    disabled={busy === `approve-${c.id}`}
                    onClick={() => onApprove(c)}
                    className="table-action approve"
                  >
                    {busy === `approve-${c.id}` ? "…" : "승인"}
                  </button>
                  <button
                    disabled={busy === `reject-${c.id}`}
                    onClick={() => onReject(c)}
                    className="table-action danger"
                  >
                    {busy === `reject-${c.id}` ? "…" : "반려"}
                  </button>
                </>
              )}
            </td>
          </tr>
        ))}
        {!loading && items.length === 0 && (
          <tr>
            <td colSpan={12} className="empty">
              검색 결과가 없습니다
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
