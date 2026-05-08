import type { CollectionMetricItem, DomainOption } from "../data";

interface Props {
  items: CollectionMetricItem[];
  domains: DomainOption[];
}

export function MetricsTable({ items, domains }: Props) {
  return (
    <table className="table" style={{ fontSize: 12 }}>
      <thead>
        <tr>
          <th>도메인</th>
          <th>키워드</th>
          <th className="num">호출</th>
          <th className="num">성공</th>
          <th className="num">기사 수</th>
          <th className="num">중복</th>
          <th className="num">발행</th>
          <th className="num">오류</th>
          <th>최근 수집</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={`${item.domain}-${item.query}`}>
            <td>{domains.find((domain) => domain.id === item.domain)?.label ?? item.domain}</td>
            <td>{item.query}</td>
            <td className="num">{item.requestCount}</td>
            <td className="num">{item.successCount}</td>
            <td className="num">{item.articleCount}</td>
            <td className="num">{item.duplicateCount}</td>
            <td className="num">{item.publishCount}</td>
            <td className="num">{item.errorCount}</td>
            <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: 10 }}>
              {item.lastSeenAt?.slice(0, 16).replace("T", " ")}
            </td>
          </tr>
        ))}
        {items.length === 0 && (
          <tr>
            <td colSpan={9} className="empty">
              수집 지표가 아직 없습니다.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
