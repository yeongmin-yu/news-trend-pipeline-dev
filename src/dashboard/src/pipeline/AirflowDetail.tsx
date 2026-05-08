import { AIRFLOW_DAGS, type AirflowDag } from "./data";

const STATUS_CHIP: Record<AirflowDag["status"], string> = {
  success: "chip up",
  running: "chip info",
  failed: "chip down",
};

const STATUS_LABEL: Record<AirflowDag["status"], string> = {
  success: "성공",
  running: "실행중",
  failed: "실패",
};

function RunBar({ runs }: { runs: number[] }) {
  return (
    <div style={{ display: "flex", gap: 2, alignItems: "flex-end", height: 14 }}>
      {runs.map((v, i) => (
        <div
          key={i}
          style={{
            width: 3,
            height: v === 0 ? 4 : 10,
            borderRadius: 1,
            background: v === 2 ? "var(--accent)" : v === 1 ? "var(--up)" : "var(--down)",
            opacity: 0.85,
          }}
        />
      ))}
    </div>
  );
}

export function AirflowDetail() {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>DAG ID</th>
          <th>스케줄</th>
          <th>마지막 실행</th>
          <th>소요시간</th>
          <th>상태</th>
          <th>최근 20회</th>
        </tr>
      </thead>
      <tbody>
        {AIRFLOW_DAGS.map((dag) => (
          <tr key={dag.id}>
            <td>
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 11 }}>{dag.name}</span>
            </td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-3)" }}>{dag.schedule}</td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-3)" }}>{dag.lastRun}</td>
            <td style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{dag.duration}</td>
            <td>
              <span className={STATUS_CHIP[dag.status]}>{STATUS_LABEL[dag.status]}</span>
            </td>
            <td>
              <RunBar runs={dag.runs} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
