import { useEffect, useMemo, useState } from "react";
import { Icon, fmtNum } from "./ui";
import { PipelineFlow } from "./pipeline/PipelineFlow";
import { AirflowDetail } from "./pipeline/AirflowDetail";
import { KafkaDetail } from "./pipeline/KafkaDetail";
import { SparkDetail } from "./pipeline/SparkDetail";
import { DBDetail } from "./pipeline/DBDetail";
import {
  AIRFLOW_DAGS,
  DB_TABLES,
  KAFKA_TOPICS,
  SPARK_JOBS,
  SPARK_WORKERS,
  type PipelineEdgeDef,
  type PipelineNodeDef,
  type PipelineNodeId,
  type PipelineNodeMeta,
} from "./pipeline/data";

function buildNodes(): PipelineNodeDef[] {
  const airflowMeta: PipelineNodeMeta = {
    kind: "airflow",
    dags: AIRFLOW_DAGS.length,
    running: AIRFLOW_DAGS.filter((d) => d.status === "running").length,
    failed: AIRFLOW_DAGS.filter((d) => d.status === "failed").length,
    success: AIRFLOW_DAGS.filter((d) => d.status === "success").length,
    nextIn: "03:22",
    status: AIRFLOW_DAGS.some((d) => d.status === "failed") ? "warn" : "ok",
  };
  const kafkaMeta: PipelineNodeMeta = {
    kind: "kafka",
    topics: KAFKA_TOPICS.length,
    totalLag: KAFKA_TOPICS.reduce((s, t) => s + t.lag, 0),
    msgRate: KAFKA_TOPICS.reduce((s, t) => s + t.msgRate, 0),
    sizeGB: KAFKA_TOPICS.reduce((s, t) => s + t.sizeGB, 0),
    status: KAFKA_TOPICS.some((t) => t.status === "lag") ? "warn" : "ok",
  };
  const sparkMeta: PipelineNodeMeta = {
    kind: "spark",
    workers: SPARK_WORKERS.length,
    running: SPARK_JOBS.filter((j) => j.status === "running").length,
    failed: SPARK_JOBS.filter((j) => j.status === "failed").length,
    coreUsed: SPARK_WORKERS.reduce((s, w) => s + w.coresUsed, 0),
    coreMax: SPARK_WORKERS.reduce((s, w) => s + w.cores, 0),
    status: SPARK_JOBS.some((j) => j.status === "failed") ? "warn" : "ok",
  };
  const dbMeta: PipelineNodeMeta = {
    kind: "db",
    tables: DB_TABLES.length,
    totalGB: DB_TABLES.reduce((s, t) => s + t.sizeGB, 0),
    writeRate: DB_TABLES.reduce((s, t) => s + t.writeRate, 0),
    status: DB_TABLES.some((t) => t.status === "warn") ? "warn" : "ok",
  };
  return [
    { id: "airflow", label: "Airflow",  sub: "Orchestrator", meta: airflowMeta, color: "#e27d2d", icon: "✦" },
    { id: "kafka",   label: "Kafka",    sub: "Message Bus",  meta: kafkaMeta,   color: "#5eead4", icon: "⇌" },
    { id: "spark",   label: "Spark",    sub: "Processing",   meta: sparkMeta,   color: "#a78bfa", icon: "⚡" },
    { id: "db",      label: "Database", sub: "Storage",      meta: dbMeta,      color: "#34d399", icon: "⬡" },
  ];
}

function buildEdges(nodes: PipelineNodeDef[]): PipelineEdgeDef[] {
  const kafkaMeta = nodes.find((n) => n.id === "kafka")!.meta as Extract<PipelineNodeMeta, { kind: "kafka" }>;
  const dbMeta = nodes.find((n) => n.id === "db")!.meta as Extract<PipelineNodeMeta, { kind: "db" }>;
  return [
    { from: "airflow", to: "kafka", label: "DAG trigger",      rate: fmtNum(kafkaMeta.msgRate) + "/s",  latency: "~1s",  color: "#e27d2d" },
    { from: "kafka",   to: "spark", label: "Stream consume",   rate: fmtNum(kafkaMeta.msgRate) + "/s",  latency: "~3s",  color: "#5eead4" },
    { from: "spark",   to: "db",    label: "Aggregated write", rate: fmtNum(dbMeta.writeRate) + "/s",   latency: "~12s", color: "#a78bfa" },
  ];
}

function PipelineDetailPanel({
  selectedNode,
  nodes,
  onClose,
}: {
  selectedNode: PipelineNodeId | null;
  nodes: PipelineNodeDef[];
  onClose: () => void;
}) {
  const node = nodes.find((n) => n.id === selectedNode) ?? null;
  if (!selectedNode || !node) {
    return (
      <div className="pipeline-detail-empty">
        <div style={{ fontSize: 32, opacity: 0.3 }}>↑</div>
        <div style={{ fontSize: 12 }}>노드를 클릭하면 상세 데이터가 여기에 표시됩니다</div>
      </div>
    );
  }
  return (
    <>
      <div className="pipeline-detail-head">
        <span style={{ fontSize: 16, lineHeight: 1 }}>{node.icon}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>{node.label}</span>
        <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{node.sub}</span>
        <div style={{ flex: 1 }} />
        <button
          onClick={onClose}
          style={{
            fontSize: 10,
            color: "var(--text-3)",
            padding: "2px 8px",
            border: "1px solid var(--border)",
            borderRadius: 3,
          }}
        >
          <Icon.Close size={12} />
        </button>
      </div>
      <div className="pipeline-detail-body">
        {selectedNode === "airflow" && <AirflowDetail />}
        {selectedNode === "kafka" && <KafkaDetail />}
        {selectedNode === "spark" && <SparkDetail />}
        {selectedNode === "db" && <DBDetail />}
      </div>
    </>
  );
}

function PipelineFooter({ nodes }: { nodes: PipelineNodeDef[] }) {
  return (
    <div className="pipeline-footer">
      {nodes.map((n) => (
        <span key={n.id} style={{ color: n.meta.status === "ok" ? "var(--up)" : "var(--warn)" }}>
          ■ {n.label}
        </span>
      ))}
      <div style={{ flex: 1 }} />
      <span>prod · k8s: ntp-prod · auto-refresh 4s</span>
    </div>
  );
}

export function PipelinePage() {
  const [selectedNode, setSelectedNode] = useState<PipelineNodeId | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 4000);
    return () => clearInterval(t);
  }, []);

  const nodes = useMemo(() => buildNodes(), []);
  const edges = useMemo(() => buildEdges(nodes), [nodes]);

  return (
    <div className="pipeline-page">
      <PipelineFlow
        nodes={nodes}
        edges={edges}
        selectedNode={selectedNode}
        onSelectNode={setSelectedNode}
        animated={tick % 2 === 0}
      />
      <div className="pipeline-detail">
        <PipelineDetailPanel
          selectedNode={selectedNode}
          nodes={nodes}
          onClose={() => setSelectedNode(null)}
        />
      </div>
      <PipelineFooter nodes={nodes} />
    </div>
  );
}
