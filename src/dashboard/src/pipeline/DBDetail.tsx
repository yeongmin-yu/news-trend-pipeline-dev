import { DB_TABLES } from "./data";

export function DBDetail() {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Table</th>
          <th className="num">Rows</th>
          <th className="num">Size</th>
          <th className="num">Write/s</th>
          <th>마지막 쓰기</th>
          <th>상태</th>
        </tr>
      </thead>
      <tbody>
        {DB_TABLES.map((t) => (
          <tr key={t.name}>
            <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 11 }}>{t.name}</td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {t.rows.toLocaleString()}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {t.sizeGB.toFixed(1)} GB
            </td>
            <td
              className="num"
              style={{ fontFamily: "var(--font-mono)", color: t.writeRate > 0 ? "var(--accent)" : "var(--text-4)" }}
            >
              {t.writeRate}
            </td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-3)" }}>{t.lastWrite}</td>
            <td>
              <span className={t.status === "ok" ? "chip up" : "chip warn"}>{t.status === "ok" ? "정상" : "경고"}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
