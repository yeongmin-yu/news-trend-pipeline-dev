import type { PipelineEdgeDef } from "./data";

export function PipelineEdgeArrow({ edge, animated }: { edge: PipelineEdgeDef; animated: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 4,
        width: 80,
        flexShrink: 0,
      }}
    >
      <div
        style={{
          fontSize: 9,
          color: "var(--text-4)",
          fontFamily: "var(--font-mono)",
          textAlign: "center",
        }}
      >
        {edge.label}
      </div>
      <div
        style={{
          width: "100%",
          height: 20,
          position: "relative",
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
        }}
      >
        <div style={{ width: "100%", height: 2, background: "var(--border)", borderRadius: 1 }} />
        <div
          style={{
            position: "absolute",
            left: 0,
            width: "40%",
            height: 2,
            background: `linear-gradient(90deg, transparent, ${edge.color}, transparent)`,
            borderRadius: 1,
            animation: animated ? "flowPulse 1.5s linear infinite" : "none",
          }}
        />
        <div
          style={{
            position: "absolute",
            right: 0,
            width: 0,
            height: 0,
            borderTop: "5px solid transparent",
            borderBottom: "5px solid transparent",
            borderLeft: `7px solid ${edge.color}`,
            opacity: 0.8,
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          gap: 8,
          fontSize: 9,
          fontFamily: "var(--font-mono)",
          color: "var(--text-3)",
        }}
      >
        <span style={{ color: edge.color }}>{edge.rate}</span>
        <span>{edge.latency}</span>
      </div>
    </div>
  );
}
