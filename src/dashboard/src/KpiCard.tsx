import { StatusChip } from "./ui";

export function KpiCard({
  label,
  value,
  sub,
  delta,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  delta: string;
  tone: "up" | "down" | "warn" | "info" | "muted" | "spike";
}) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-delta">
        <StatusChip tone={tone}>{delta}</StatusChip>
      </div>
      <div className="side-footer" style={{ padding: 0, marginTop: 8 }}>
        {sub}
      </div>
    </div>
  );
}
