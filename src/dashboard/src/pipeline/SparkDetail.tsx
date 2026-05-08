import { SPARK_JOBS, SPARK_WORKERS, type SparkJob, type SparkWorker } from "./data";

function WorkerCard({ worker }: { worker: SparkWorker }) {
  const cpuRatio = worker.coresUsed / worker.cores;
  const memRatio = worker.memUsedGB / worker.memGB;
  return (
    <div
      style={{
        background: "var(--bg-2)",
        border: `1px solid ${worker.status === "busy" ? "var(--warn)" : "var(--border)"}`,
        borderRadius: 6,
        padding: "8px 10px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontWeight: 700, fontSize: 11 }}>{worker.id}</span>
        <span className={worker.status === "busy" ? "chip warn" : "chip up"} style={{ fontSize: 9 }}>
          {worker.status === "busy" ? "포화" : "활성"}
        </span>
      </div>
      <div style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-mono)", marginBottom: 5 }}>
        {worker.host}
      </div>
      <div style={{ fontSize: 9, color: "var(--text-3)", marginBottom: 3 }}>
        CPU {worker.coresUsed}/{worker.cores}
      </div>
      <div style={{ height: 3, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden", marginBottom: 5 }}>
        <div
          style={{
            width: cpuRatio * 100 + "%",
            height: "100%",
            background: cpuRatio > 0.85 ? "var(--down)" : "var(--accent)",
          }}
        />
      </div>
      <div style={{ fontSize: 9, color: "var(--text-3)", marginBottom: 3 }}>
        Mem {Math.round(worker.memUsedGB)}/{worker.memGB}GB
      </div>
      <div style={{ height: 3, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden" }}>
        <div
          style={{
            width: memRatio * 100 + "%",
            height: "100%",
            background: memRatio > 0.85 ? "var(--down)" : "var(--info)",
          }}
        />
      </div>
    </div>
  );
}

function JobStatusChip({ status }: { status: SparkJob["status"] }) {
  if (status === "succeeded") return <span className="chip up" style={{ fontSize: 9 }}>완료</span>;
  if (status === "running") return <span className="chip info" style={{ fontSize: 9 }}>실행중</span>;
  return <span className="chip down" style={{ fontSize: 9 }}>실패</span>;
}

export function SparkDetail() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4,1fr)",
          gap: 8,
          padding: "10px 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg)",
        }}
      >
        {SPARK_WORKERS.map((w) => (
          <WorkerCard key={w.id} worker={w} />
        ))}
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Job ID</th>
            <th>Application</th>
            <th>Worker</th>
            <th>시작</th>
            <th>소요</th>
            <th>Stage</th>
            <th>Tasks</th>
            <th>Shuffle</th>
            <th>상태</th>
          </tr>
        </thead>
        <tbody>
          {SPARK_JOBS.map((job) => {
            const [doneStr, totalStr] = job.tasks.split("/");
            const taskRatio = Number(doneStr) / Number(totalStr);
            return (
              <tr key={job.id}>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-3)" }}>{job.id}</td>
                <td style={{ fontWeight: 600, fontSize: 11 }}>{job.app}</td>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-3)" }}>{job.worker}</td>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-3)" }}>{job.startedAt}</td>
                <td
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: job.duration === "running" ? "var(--accent)" : "var(--text)",
                  }}
                >
                  {job.duration}
                </td>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{job.stage}</td>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{ width: 30, height: 3, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden" }}>
                      <div style={{ width: taskRatio * 100 + "%", height: "100%", background: "var(--up)" }} />
                    </div>
                    {job.tasks}
                  </div>
                </td>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-3)" }}>{job.shuffle}</td>
                <td>
                  <JobStatusChip status={job.status} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
