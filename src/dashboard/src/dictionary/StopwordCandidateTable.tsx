import type { StopwordCandidateItem } from "../data";
import { SW_CANDIDATE_STATUS_CHIP, SW_CANDIDATE_STATUS_LABEL } from "./types";

interface Props {
  items: StopwordCandidateItem[];
  busy: string | null;
  loading: boolean;
  onApprove: (item: StopwordCandidateItem) => void;
  onReject: (item: StopwordCandidateItem) => void;
}

export function StopwordCandidateTable({ items, busy, loading, onApprove, onReject }: Props) {
  return (
    <table className="table" style={{ fontSize: 12 }}>
      <thead>
        <tr>
          <th>후보어</th>
          <th>도메인</th>
          <th className="num">점수</th>
          <th className="num">도메인폭</th>
          <th className="num">반복률</th>
          <th className="num">안정성</th>
          <th className="num">공출현</th>
          <th className="num">빈도</th>
          <th>상태</th>
          <th>작업</th>
        </tr>
      </thead>
      <tbody>
        {items.map((c) => (
          <tr key={c.id}>
            <td>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--down)", fontWeight: 600 }}>{c.word}</span>
            </td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-3)" }}>
              {c.domain ?? "all"}
            </td>
            <td
              className="num"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                color: c.score >= 0.6 ? "var(--down)" : "var(--text-2)",
              }}
            >
              {c.score?.toFixed(3) ?? "—"}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {c.domainBreadth?.toFixed(2) ?? "—"}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {c.repetitionRate?.toFixed(2) ?? "—"}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {c.trendStability?.toFixed(2) ?? "—"}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {c.cooccurrenceBreadth?.toFixed(2) ?? "—"}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {c.frequency.toLocaleString()}
            </td>
            <td>
              <span className={"chip " + (SW_CANDIDATE_STATUS_CHIP[c.status] ?? "muted")} style={{ fontSize: 11 }}>
                {SW_CANDIDATE_STATUS_LABEL[c.status] ?? c.status}
              </span>
            </td>
            <td style={{ display: "flex", gap: 4 }}>
              {c.status === "needs_review" && (
                <>
                  <button
                    disabled={busy === `approve-sw-${c.id}`}
                    onClick={() => onApprove(c)}
                    className="table-action approve"
                  >
                    {busy === `approve-sw-${c.id}` ? "…" : "승인"}
                  </button>
                  <button
                    disabled={busy === `reject-sw-${c.id}`}
                    onClick={() => onReject(c)}
                    className="table-action danger"
                  >
                    {busy === `reject-sw-${c.id}` ? "…" : "반려"}
                  </button>
                </>
              )}
            </td>
          </tr>
        ))}
        {!loading && items.length === 0 && (
          <tr>
            <td colSpan={10} className="empty">
              추천된 불용어 후보가 없습니다 (분석 실행 후 표시됩니다)
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
