import type { QueryKeywordItem } from "../data";

interface Props {
  items: QueryKeywordItem[];
  onEdit: (item: QueryKeywordItem) => void;
  onToggleActive: (item: QueryKeywordItem) => void;
  onDelete: (item: QueryKeywordItem) => void;
}

export function KeywordTable({ items, onEdit, onToggleActive, onDelete }: Props) {
  return (
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
        {items.map((item) => (
          <tr key={item.id}>
            <td>{item.domainLabel}</td>
            <td>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 600 }}>
                {item.query}
              </span>
            </td>
            <td className="num">{item.sortOrder}</td>
            <td>
              <span className={"chip " + (item.isActive ? "up" : "muted")}>
                {item.isActive ? "활성" : "비활성"}
              </span>
            </td>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>
              {item.updatedAt?.slice(0, 16).replace("T", " ")}
            </td>
            <td style={{ display: "flex", gap: 4 }}>
              <button onClick={() => onEdit(item)} className="table-action">
                수정
              </button>
              <button onClick={() => onToggleActive(item)} className="table-action">
                {item.isActive ? "비활성화" : "활성화"}
              </button>
              <button onClick={() => onDelete(item)} className="table-action danger">
                삭제
              </button>
            </td>
          </tr>
        ))}
        {items.length === 0 && (
          <tr>
            <td colSpan={6} className="empty">
              표시할 키워드가 없습니다.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
