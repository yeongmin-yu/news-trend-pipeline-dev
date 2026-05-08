import type { CompoundNounItem, DomainOption } from "../data";
import { DomainBadge } from "./DomainBadge";

interface Props {
  items: CompoundNounItem[];
  domains: DomainOption[];
  busy: string | null;
  loading: boolean;
  onUpdateDomain: (id: number, newDomain: string) => void;
  onDelete: (item: CompoundNounItem) => void;
  onBackfill: (item: CompoundNounItem) => void;
}

export function CompoundTable({ items, domains, busy, loading, onUpdateDomain, onDelete, onBackfill }: Props) {
  return (
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
        {items.map((c) => (
          <tr key={c.id}>
            <td>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 600 }}>{c.word}</span>
            </td>
            <td>
              <DomainBadge domain={c.domain ?? "all"} domains={domains} itemId={c.id} onUpdate={onUpdateDomain} />
            </td>
            <td>
              <span className="chip muted" style={{ fontSize: 11 }}>
                {c.source}
              </span>
            </td>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 11 }}>
              {c.createdAt?.slice(0, 16).replace("T", " ") ?? "—"}
            </td>
            <td style={{ display: "flex", gap: 4 }}>
              <button
                disabled={busy === "compound-backfill"}
                onClick={() => onBackfill(c)}
                className="table-action"
              >
                과거 재처리
              </button>
              <button
                disabled={busy === `del-c-${c.id}`}
                onClick={() => onDelete(c)}
                className="table-action danger"
              >
                {busy === `del-c-${c.id}` ? "…" : "삭제"}
              </button>
            </td>
          </tr>
        ))}
        {!loading && items.length === 0 && (
          <tr>
            <td colSpan={5} className="empty">
              검색 결과가 없습니다
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
