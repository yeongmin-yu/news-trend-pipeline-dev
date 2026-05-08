import type { HistoryItem } from "./types";

interface Props {
  items: HistoryItem[];
  loading: boolean;
}

export function HistoryTable({ items, loading }: Props) {
  return (
    <table className="table" style={{ fontSize: 12 }}>
      <thead>
        <tr>
          <th>시각</th>
          <th>대상</th>
          <th>액션</th>
          <th>작업자</th>
          <th>이전 값</th>
          <th>변경 값</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id}>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {item.acted_at?.slice(0, 16).replace("T", " ")}
            </td>
            <td>
              <span className="chip muted">{item.entity_type}</span>
            </td>
            <td>
              <span className="chip info">{item.action}</span>
            </td>
            <td>{item.actor}</td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {item.before_json ? JSON.stringify(item.before_json) : "-"}
            </td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {item.after_json ? JSON.stringify(item.after_json) : "-"}
            </td>
          </tr>
        ))}
        {!loading && items.length === 0 && (
          <tr>
            <td colSpan={6} className="empty">
              사전 변경 로그가 없습니다.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
