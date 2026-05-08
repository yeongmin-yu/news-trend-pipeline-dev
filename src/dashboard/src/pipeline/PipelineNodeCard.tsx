import { fmtNum } from "../ui";
import { statusVar, type PipelineNodeDef } from "./data";

function Metric({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div style={{ background: "var(--bg)", borderRadius: 5, padding: "5px 7px" }}>
      <div
        style={{
          fontSize: 9,
          color: "var(--text-4)",
          fontFamily: "var(--font-mono)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color, fontVariantNumeric: "tabular-nums", marginTop: 1 }}>
        {value}
      </div>
    </div>
  );
}

export function PipelineNodeCard({
  node,
  isSelected,
  onSelect,
}: {
  node: PipelineNodeDef;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const m = node.meta;
  return (
    <div
      onClick={onSelect}
      style={{
        background: isSelected ? "var(--bg-3)" : "var(--bg-2)",
        border: `1.5px solid ${isSelected ? node.color : "var(--border)"}`,
        borderRadius: 10,
        padding: "16px 18px",
        cursor: "pointer",
        width: 190,
        flexShrink: 0,
        transition: "border-color 0.15s, background 0.15s",
        boxShadow: isSelected ? `0 0 0 3px ${node.color}22` : "none",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: -30,
          right: -30,
          width: 80,
          height: 80,
          borderRadius: "50%",
          background: node.color,
          opacity: 0.07,
          pointerEvents: "none",
        }}
      />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18, lineHeight: 1 }}>{node.icon}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 13, color: "var(--text)" }}>{node.label}</div>
            <div style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{node.sub}</div>
          </div>
        </div>
        <div
          style={{
            width: 9,
            height: 9,
            borderRadius: "50%",
            background: statusVar(m.status),
            boxShadow: `0 0 6px ${statusVar(m.status)}`,
          }}
        />
      </div>
      {m.kind === "airflow" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <Metric label="DAGs" value={m.dags} color={node.color} />
          <Metric label="실행중" value={m.running} color="var(--accent)" />
          <Metric label="성공" value={m.success} color="var(--up)" />
          <Metric label="실패" value={m.failed} color={m.failed > 0 ? "var(--down)" : "var(--text-4)"} />
        </div>
      )}
      {m.kind === "kafka" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <Metric label="Topics" value={m.topics} color={node.color} />
          <Metric label="Msg/s" value={fmtNum(m.msgRate)} color="var(--accent)" />
          <Metric label="Lag" value={fmtNum(m.totalLag)} color={m.totalLag > 1000 ? "var(--down)" : "var(--up)"} />
          <Metric label="Size" value={m.sizeGB.toFixed(0) + "GB"} color="var(--text-3)" />
        </div>
      )}
      {m.kind === "spark" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <Metric label="Workers" value={m.workers} color={node.color} />
          <Metric label="Jobs" value={m.running} color="var(--accent)" />
          <Metric label="Cores" value={m.coreUsed + "/" + m.coreMax} color="var(--text-3)" />
          <Metric label="실패" value={m.failed} color={m.failed > 0 ? "var(--down)" : "var(--text-4)"} />
        </div>
      )}
      {m.kind === "db" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <Metric label="Tables" value={m.tables} color={node.color} />
          <Metric label="Write/s" value={fmtNum(m.writeRate)} color="var(--accent)" />
          <Metric label="Size" value={m.totalGB.toFixed(0) + "GB"} color="var(--text-3)" />
          <Metric label="DLQ" value="18" color="var(--warn)" />
        </div>
      )}
      {isSelected && (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: 2,
            background: node.color,
            borderRadius: "0 0 8px 8px",
          }}
        />
      )}
    </div>
  );
}
