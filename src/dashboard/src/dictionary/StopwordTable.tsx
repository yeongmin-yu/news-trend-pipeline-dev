import type { DomainOption, StopwordItem } from "../data";
import { DomainBadge } from "./DomainBadge";

interface Props {
  items: StopwordItem[];
  domains: DomainOption[];
  busy: string | null;
  loading: boolean;
  onUpdateDomain: (id: number, newDomain: string) => void;
  onDelete: (item: StopwordItem) => void;
}

export function StopwordTable({ items, domains, busy, loading, onUpdateDomain, onDelete }: Props) {
  return (
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
        {items.map((s) => (
          <tr key={s.id}>
            <td>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--down)", fontWeight: 600 }}>{s.word}</span>
            </td>
            <td>
              <DomainBadge domain={s.domain ?? "all"} domains={domains} itemId={s.id} onUpdate={onUpdateDomain} />
            </td>
            <td>
              <span className="chip info" style={{ fontSize: 11 }}>
                {s.language}
              </span>
            </td>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 11 }}>
              {s.createdAt?.slice(0, 10) ?? "—"}
            </td>
            <td>
              <button
                disabled={busy === `del-s-${s.id}`}
                onClick={() => onDelete(s)}
                className="table-action danger"
              >
                {busy === `del-s-${s.id}` ? "…" : "삭제"}
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
