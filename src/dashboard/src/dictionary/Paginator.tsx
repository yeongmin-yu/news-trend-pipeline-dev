interface Props {
  page: number;
  total: number;
  limit: number;
  onChange: (page: number) => void;
}

export function Paginator({ page, total, limit, onChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  if (totalPages <= 1) return null;

  const baseBtn = {
    padding: "3px 8px",
    borderRadius: 4,
    border: "1px solid var(--border)",
    background: "transparent",
    fontSize: 11,
  } as const;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)" }}>
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        style={{
          ...baseBtn,
          color: page <= 1 ? "var(--text-4)" : "var(--text-2)",
          cursor: page <= 1 ? "default" : "pointer",
        }}
      >
        ← 이전
      </button>
      <span style={{ color: "var(--text-3)" }}>
        {page} / {totalPages}
      </span>
      <button
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        style={{
          ...baseBtn,
          color: page >= totalPages ? "var(--text-4)" : "var(--text-2)",
          cursor: page >= totalPages ? "default" : "pointer",
        }}
      >
        다음 →
      </button>
    </div>
  );
}
