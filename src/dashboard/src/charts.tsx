import { useEffect, useMemo, useRef, useState } from "react";
import { fmtNum, fmtPct, Icon } from "./ui";
import type { KeywordSummary, RelatedKeyword, SpikeEvent, TrendSeries } from "./data";

export function TopKeywords({
  keywords,
  selected,
  onSelect,
  checkedKeywords,
  onToggleCheck,
  barColor,
  limit,
  sortBy = "mentions",
  onLimitChange,
  onSortChange,
}: {
  keywords: KeywordSummary[];
  selected: string | null;
  onSelect: (keyword: string) => void;
  checkedKeywords: string[];
  onToggleCheck: (keyword: string) => void;
  barColor: string;
  limit: number;
  sortBy?: "mentions" | "growth";
  onLimitChange?: (n: number) => void;
  onSortChange?: (s: "mentions" | "growth") => void;
}) {
  const list = useMemo(() => {
    const arr = [...keywords];
    if (sortBy === "growth") arr.sort((a, b) => (b.growth ?? 0) - (a.growth ?? 0));
    else arr.sort((a, b) => b.mentions - a.mentions);
    return arr.slice(0, limit);
  }, [keywords, sortBy, limit]);

  const max = Math.max(1, ...list.map((item) => item.mentions));

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="panel-title">
          <Icon.Hash size={12} />
          상위 키워드
          <span className="tag mono">TOP {limit}</span>
          <span className="spike-dot" />급상승
        </div>
        {(onSortChange || onLimitChange) && (
          <div className="panel-tools">
            {onSortChange && (
              <div className="seg">
                <button
                  className={sortBy === "mentions" ? "is-active" : ""}
                  onClick={() => onSortChange("mentions")}
                >
                  언급량
                </button>
                <button
                  className={sortBy === "growth" ? "is-active" : ""}
                  onClick={() => onSortChange("growth")}
                >
                  증가율
                </button>
              </div>
            )}
            {onLimitChange && (
              <div className="seg">
                {[10, 20, 30].map((n) => (
                  <button
                    key={n}
                    className={limit === n ? "is-active" : ""}
                    onClick={() => onLimitChange(n)}
                  >
                    {n}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <div className="panel-body flush scroll">
        {list.map((item, index) => (
          <div
            key={item.keyword}
            className={`bar-row${selected === item.keyword ? " is-selected" : ""}${item.spike ? " is-spike" : ""}`}
            onClick={() => onSelect(item.keyword)}
          >
            <label
              className="bar-check"
              onClick={(e) => e.stopPropagation()}
              title={checkedKeywords.includes(item.keyword) ? "트렌드 비교에서 제외" : "트렌드 비교에 추가"}
            >
              <input
                type="checkbox"
                checked={checkedKeywords.includes(item.keyword)}
                disabled={!checkedKeywords.includes(item.keyword) && checkedKeywords.length >= 5}
                onChange={() => onToggleCheck(item.keyword)}
              />
            </label>
            <div className="rank">{String(index + 1).padStart(2, "0")}</div>
            <div className="name">
              {item.spike ? <span className="spike-dot" /> : null}
              {item.keyword}
            </div>
            <div className="bar-wrap">
              <div
                className="bar-fill"
                style={{
                  width: `${(item.mentions / max) * 100}%`,
                  background: item.spike
                    ? "linear-gradient(90deg, var(--spike), #fb7185)"
                    : barColor,
                }}
              />
            </div>
            <div className="val">{fmtNum(item.mentions)}</div>
            <div className={`chg chip ${item.growth >= 0 ? "up" : "down"}`}>{fmtPct(item.growth)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TrendLine({
  series,
  bucketMin,
  hidden = [],
  onToggle,
  selectedBucket,
  onPointClick,
  mini = false,
  nowMs,
}: {
  series: TrendSeries[];
  bucketMin: number;
  hidden?: string[];
  onToggle?: (name: string) => void;
  selectedBucket?: number | null;
  onPointClick?: (bucketIdx: number) => void;
  mini?: boolean;
  nowMs?: number;
}) {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 600, height: 280 });
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [pointer, setPointer] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const resize = () => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (rect) setSize({ width: rect.width, height: rect.height });
    };
    resize();
    const observer = new ResizeObserver(resize);
    if (canvasRef.current) observer.observe(canvasRef.current);
    return () => observer.disconnect();
  }, []);

  const visibleSeries = series.filter((s) => !hidden.includes(s.name));
  const points = series[0]?.points ?? [];
  const maxValue = Math.max(1, ...visibleSeries.flatMap((s) => s.points.map((p) => p.value)));
  const pad = mini
    ? { top: 8, right: 8, bottom: 20, left: 30 }
    : { top: 14, right: 16, bottom: 26, left: 40 };
  const innerWidth = Math.max(10, size.width - pad.left - pad.right);
  const innerHeight = Math.max(10, size.height - pad.top - pad.bottom);

  const x = (index: number) => pad.left + (index / Math.max(1, points.length - 1)) * innerWidth;
  const y = (value: number) => pad.top + innerHeight - (value / maxValue) * innerHeight;

  const linePath = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const areaPath = (values: number[]) =>
    `${linePath(values)} L ${x(values.length - 1).toFixed(1)} ${size.height - pad.bottom} L ${x(0).toFixed(1)} ${size.height - pad.bottom} Z`;

  // Y-axis ticks (fewer in mini mode)
  const yTicks = mini ? 2 : 4;
  const yVals = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((maxValue / yTicks) * i));

  // X-axis ticks
  const xTicks = useMemo(() => {
    const step = Math.ceil(points.length / 6);
    const ticks: number[] = [];
    for (let i = 0; i < points.length; i += step) ticks.push(i);
    if (ticks[ticks.length - 1] !== points.length - 1) ticks.push(points.length - 1);
    return ticks;
  }, [points]);

  const xLabel = (index: number) => {
    const minutesBack = (points.length - 1 - index) * bucketMin;
    if (nowMs != null) {
      const kst = new Date(nowMs - minutesBack * 60_000 + 9 * 3_600_000);
      return `${String(kst.getUTCHours()).padStart(2, "0")}:${String(kst.getUTCMinutes()).padStart(2, "0")}`;
    }
    if (minutesBack === 0) return "now";
    if (minutesBack < 60) return `-${minutesBack}m`;
    return `-${Math.round(minutesBack / 60)}h`;
  };

  const primarySeries = visibleSeries[0];

  return (
    <div className="trend-wrap">
      <div className="trend-svg-wrap" ref={canvasRef}>
      <svg
        className="trend-svg"
        viewBox={`0 0 ${size.width} ${size.height}`}
        style={{ cursor: onPointClick ? "pointer" : "default" }}
        onMouseLeave={() => setHoverIndex(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const localX = e.clientX - rect.left;
          const localY = e.clientY - rect.top;
          if (localX < pad.left || localX > size.width - pad.right) { setHoverIndex(null); return; }
          const ratio = Math.min(1, Math.max(0, (localX - pad.left) / innerWidth));
          setHoverIndex(Math.round(ratio * Math.max(0, points.length - 1)));
          setPointer({ x: localX, y: localY });
        }}
        onClick={() => {
          if (hoverIndex != null && onPointClick) onPointClick(hoverIndex);
        }}
      >
        {/* Y-axis grid + labels */}
        {yVals.map((v, i) => (
          <g key={i}>
            <line
              x1={pad.left} x2={size.width - pad.right}
              y1={y(v)} y2={y(v)}
              stroke="var(--divider)" strokeDasharray="2 3"
            />
            <text x={pad.left - 6} y={y(v) + 3} fill="var(--text-4)" fontSize="9" textAnchor="end" fontFamily="var(--font-mono)">
              {fmtNum(Math.round(v))}
            </text>
          </g>
        ))}
        {/* X-axis labels */}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={size.height - pad.bottom + 14} fill="var(--text-4)" fontSize="9" textAnchor="middle" fontFamily="var(--font-mono)">
            {xLabel(i)}
          </text>
        ))}
        {/* Selected bucket line */}
        {selectedBucket != null && (
          <line
            x1={x(selectedBucket)} x2={x(selectedBucket)}
            y1={pad.top} y2={size.height - pad.bottom}
            stroke="var(--accent)" strokeWidth="1" strokeDasharray="3 2" opacity="0.6"
          />
        )}
        {/* Areas */}
        {visibleSeries.map((s) => (
          <path key={s.name + "-area"} d={areaPath(s.points.map((p) => p.value))} fill={s.color} opacity="0.08" />
        ))}
        {/* Lines */}
        {visibleSeries.map((s) => (
          <path
            key={s.name}
            d={linePath(s.points.map((p) => p.value))}
            fill="none"
            stroke={s.color}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
        {/* Dots on primary series */}
        {primarySeries && primarySeries.points.map((p, i) => (
          <circle
            key={i}
            cx={x(i)} cy={y(p.value)}
            r="2"
            fill={primarySeries.color}
            opacity={hoverIndex === i ? 1 : 0.55}
          />
        ))}
        {/* Hover guideline */}
        {hoverIndex != null && (
          <g>
            <line
              x1={x(hoverIndex)} x2={x(hoverIndex)}
              y1={pad.top} y2={size.height - pad.bottom}
              stroke="var(--text-3)" strokeWidth="1" strokeDasharray="2 2"
            />
            {visibleSeries.map((s) => (
              <circle
                key={s.name + "-h"}
                cx={x(hoverIndex)}
                cy={y(s.points[hoverIndex]?.value ?? 0)}
                r="3.5"
                fill={s.color}
                stroke="var(--bg-1)"
                strokeWidth="1.5"
              />
            ))}
          </g>
        )}
      </svg>

      {/* Tooltip */}
      {hoverIndex != null && (
        <div
          className="tooltip trend-tooltip"
          style={{
            left: Math.min(pointer.x + 12, size.width - 180),
            top: Math.max(8, pointer.y - 20),
          }}
        >
          <div className="t-head">{xLabel(hoverIndex)} · bucket {hoverIndex + 1}/{points.length}</div>
          {visibleSeries.map((s) => (
            <div className="t-row" key={s.name}>
              <span>
                <span className="sw" style={{ background: s.color }} />
                {s.name}
              </span>
              <span className="v">{fmtNum(s.points[hoverIndex]?.value ?? 0)}</span>
            </div>
          ))}
        </div>
      )}

      </div>{/* end trend-svg-wrap */}

      {/* Legend (hidden in mini mode) */}
      {!mini && (
        <div className="trend-legend">
          {series.map((s) => (
            <div
              key={s.name}
              className={`item${hidden.includes(s.name) ? " is-off" : ""}`}
              onClick={() => onToggle?.(s.name)}
              style={{ cursor: onToggle ? "pointer" : "default" }}
            >
              <span className="swatch" style={{ background: s.color }} />
              {s.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function SpikeHeatmap({
  keywords,
  events,
  buckets,
  bucketMin,
  selectedBucket,
  onSelectBucket,
  selectedKeyword,
  onSelectKeyword,
  nowMs,
}: {
  keywords: string[];
  events: SpikeEvent[];
  buckets: number;
  bucketMin: number;
  selectedBucket: number | null;
  onSelectBucket: (bucket: number | null) => void;
  selectedKeyword?: string | null;
  onSelectKeyword?: (keyword: string) => void;
  nowMs?: number;
}) {
  const matrix = useMemo(() => {
    const value: Record<string, number[]> = {};
    for (const keyword of keywords) {
      value[keyword] = new Array(buckets).fill(0);
    }
    for (const event of events) {
      if (!value[event.keyword]) continue;
      // Spread intensity to neighbouring buckets with falloff
      for (let offset = -1; offset <= 1; offset++) {
        const idx = event.bucket + offset;
        if (idx < 0 || idx >= buckets) continue;
        const falloff = offset === 0 ? 1 : 0.45;
        value[event.keyword][idx] = Math.max(value[event.keyword][idx], event.intensity * falloff);
      }
    }
    return value;
  }, [events, keywords, buckets]);

  const xLabel = (index: number) => {
    const minutesBack = (buckets - 1 - index) * bucketMin;
    if (nowMs != null) {
      const kst = new Date(nowMs - minutesBack * 60_000 + 9 * 3_600_000);
      return `${String(kst.getUTCHours()).padStart(2, "0")}:${String(kst.getUTCMinutes()).padStart(2, "0")}`;
    }
    if (minutesBack === 0) return "now";
    if (minutesBack < 60) return `-${minutesBack}m`;
    return `-${Math.round(minutesBack / 60)}h`;
  };

  const step = Math.ceil(buckets / 6);

  function cellColor(v: number) {
    if (v < 0.05) return "var(--bg-2)";
    const alpha = 0.15 + v * 0.85;
    return `rgba(239, 68, 68, ${alpha.toFixed(2)})`;
  }

  return (
    <div className="heat-grid">
      {keywords.map((keyword) => (
        <div className="heat-row" key={keyword} style={{ ["--cols" as never]: String(buckets) }}>
          <div
            className="lbl"
            title={keyword}
            style={{
              color: selectedKeyword === keyword ? "var(--text)" : undefined,
              fontWeight: selectedKeyword === keyword ? 600 : 400,
              cursor: onSelectKeyword ? "pointer" : "default",
            }}
            onClick={() => onSelectKeyword?.(keyword)}
          >
            {keyword}
          </div>
          {matrix[keyword].map((value, index) => (
            <div
              key={`${keyword}-${index}`}
              className={`heat-cell${selectedBucket === index ? " is-selected" : ""}`}
              style={{ background: cellColor(value) }}
              title={`${keyword} · ${xLabel(index)} · 강도 ${(value * 100).toFixed(0)}%`}
              onClick={() => onSelectBucket(selectedBucket === index ? null : index)}
            />
          ))}
        </div>
      ))}
      <div className="heat-axis" style={{ ["--cols" as never]: String(buckets) }}>
        <div />
        {Array.from({ length: buckets }, (_, index) => (
          <div className="tick" key={index}>
            {index % step === 0 || index === buckets - 1 ? xLabel(index) : ""}
          </div>
        ))}
      </div>
    </div>
  );
}

export function RelatedNetwork({
  center,
  related,
  onSelect,
}: {
  center: string;
  related: RelatedKeyword[];
  onSelect: (keyword: string) => void;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 400, height: 280 });

  useEffect(() => {
    const resize = () => {
      const rect = wrapRef.current?.getBoundingClientRect();
      if (rect) setSize({ width: rect.width, height: rect.height });
    };
    resize();
    const observer = new ResizeObserver(resize);
    if (wrapRef.current) observer.observe(wrapRef.current);
    return () => observer.disconnect();
  }, []);

  const radius = Math.min(size.width, size.height) / 2 - 42;
  const cx = size.width / 2;
  const cy = size.height / 2;
  const nodes = related.slice(0, 12).map((item, index, list) => {
    const angle = (index / Math.max(1, list.length)) * Math.PI * 2 - Math.PI / 2;
    const distance = radius * (1.15 - item.weight * 0.45);
    return {
      ...item,
      x: cx + Math.cos(angle) * distance,
      y: cy + Math.sin(angle) * distance,
      r: 10 + item.weight * 16,
    };
  });

  return (
    <div className="network-wrap" ref={wrapRef}>
      <svg className="network-svg" viewBox={`0 0 ${size.width} ${size.height}`}>
        {nodes.map((node) => (
          <line
            key={`line-${node.keyword}`}
            x1={cx} y1={cy} x2={node.x} y2={node.y}
            className="network-edge"
            strokeWidth={0.5 + node.weight * 2}
            opacity={0.4 + node.weight * 0.5}
          />
        ))}
        <circle cx={cx} cy={cy} r="26" fill="var(--accent-weak)" stroke="var(--accent)" strokeWidth="1.5" />
        <text x={cx} y={cy + 4} textAnchor="middle" fill="var(--accent)" fontSize="11" fontWeight="600">
          {center}
        </text>
        {nodes.map((node) => (
          <g
            key={node.keyword}
            style={{ cursor: node.weight >= 1 ? "pointer" : "default" }}
            onClick={() => {
              if (node.weight >= 1) onSelect(node.keyword);
            }}
          >
            <circle cx={node.x} cy={node.y} r={node.r} fill="var(--bg-2)" stroke="var(--border-hi)" strokeWidth="1" />
            <circle cx={node.x} cy={node.y} r={node.r - 3} fill={`rgba(139, 92, 246, ${0.15 + node.weight * 0.35})`} />
            <text className="network-node-label" x={node.x} y={node.y - node.r - 4} textAnchor="middle">
              {node.keyword}
            </text>
            <text x={node.x} y={node.y + 3} textAnchor="middle" fill="var(--text-2)" fontSize="9" fontFamily="var(--font-mono)">
              {node.weight.toFixed(2)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export function MiniTrend({
  points,
  color = "var(--accent)",
}: {
  points: { value: number }[];
  color?: string;
}) {
  const width = 420;
  const height = 88;
  const pad = { top: 10, right: 10, bottom: 16, left: 10 };
  const maxValue = Math.max(1, ...points.map((p) => p.value));
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;

  const x = (i: number) => pad.left + (i / Math.max(1, points.length - 1)) * innerWidth;
  const y = (v: number) => pad.top + innerHeight - (v / maxValue) * innerHeight;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.value)}`).join(" ");
  const area = `${path} L ${x(points.length - 1)} ${height - pad.bottom} L ${x(0)} ${height - pad.bottom} Z`;

  return (
    <div className="mini-trend">
      <svg className="mini-trend-svg" viewBox={`0 0 ${width} ${height}`}>
        {[0, 1, 2, 3].map((tick) => {
          const v = (maxValue / 3) * tick;
          return (
            <line key={tick} x1={pad.left} x2={width - pad.right} y1={y(v)} y2={y(v)} stroke="var(--divider)" strokeDasharray="2 4" />
          );
        })}
        <path d={area} fill={color} opacity="0.12" />
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
