import { fmtNum } from "../ui";
import { KAFKA_TOPICS, type KafkaTopic } from "./data";

function lagColor(lag: number) {
  if (lag > 1000) return "var(--down)";
  if (lag > 0) return "var(--warn)";
  return "var(--text-3)";
}

function StatusChip({ status }: { status: KafkaTopic["status"] }) {
  if (status === "healthy") return <span className="chip up">정상</span>;
  if (status === "lag") return <span className="chip down">지연</span>;
  return <span className="chip warn">경고</span>;
}

export function KafkaDetail() {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Topic</th>
          <th className="num">Partitions</th>
          <th className="num">Retention</th>
          <th className="num">Consumer Lag</th>
          <th className="num">Msg/s</th>
          <th className="num">Size</th>
          <th>상태</th>
        </tr>
      </thead>
      <tbody>
        {KAFKA_TOPICS.map((t) => (
          <tr key={t.name}>
            <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 11 }}>{t.name}</td>
            <td className="num">{t.partitions}</td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {t.retentionHr}h
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)", color: lagColor(t.lag) }}>
              {t.lag.toLocaleString()}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)" }}>
              {fmtNum(t.msgRate)}
            </td>
            <td className="num" style={{ fontFamily: "var(--font-mono)" }}>
              {t.sizeGB.toFixed(1)} GB
            </td>
            <td>
              <StatusChip status={t.status} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
