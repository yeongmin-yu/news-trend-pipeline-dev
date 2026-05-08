import type { QueryKeywordAuditLog } from "../data";

interface Props {
  items: QueryKeywordAuditLog[];
}

export function LogsTable({ items }: Props) {
  return (
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
        {items.map((item) => (
          <tr key={item.id}>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>
              {item.actedAt?.slice(0, 16).replace("T", " ")}
            </td>
            <td>
              <span className="chip info">{item.action}</span>
            </td>
            <td>{item.actor}</td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {item.beforeJson ? JSON.stringify(item.beforeJson) : "-"}
            </td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {item.afterJson ? JSON.stringify(item.afterJson) : "-"}
            </td>
          </tr>
        ))}
        {items.length === 0 && (
          <tr>
            <td colSpan={5} className="empty">
              변경 로그가 없습니다.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
