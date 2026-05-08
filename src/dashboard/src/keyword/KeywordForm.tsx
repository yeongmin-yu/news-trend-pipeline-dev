import type { DomainOption } from "../data";
import type { KeywordFormState } from "./types";

interface Props {
  form: KeywordFormState;
  setForm: (next: KeywordFormState) => void;
  domains: DomainOption[];
  busy: boolean;
  onSubmit: () => void;
  onReset: () => void;
}

export function KeywordForm({ form, setForm, domains, busy, onSubmit, onReset }: Props) {
  const saveDisabled = !form.query.trim() || !form.domainId;
  const fieldStyle = {
    padding: "6px 8px",
    background: "var(--bg-3)",
    border: "1px solid var(--border-hi)",
    borderRadius: 4,
    color: "var(--text)",
    fontSize: 12,
  } as const;

  return (
    <div
      style={{
        padding: "12px 20px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-2)",
        display: "flex",
        gap: 10,
        alignItems: "flex-end",
        flexWrap: "wrap",
        flexShrink: 0,
      }}
    >
      <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
        도메인
        <select
          value={form.domainId}
          onChange={(e) => setForm({ ...form, domainId: e.target.value })}
          style={fieldStyle}
        >
          {domains.map((domain) => (
            <option key={domain.id} value={domain.id}>
              {domain.label}
            </option>
          ))}
        </select>
      </label>
      <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
        키워드
        <input
          value={form.query}
          onChange={(e) => setForm({ ...form, query: e.target.value })}
          style={{ ...fieldStyle, width: 220 }}
        />
      </label>
      <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
        정렬 순서
        <input
          type="number"
          value={form.sortOrder}
          onChange={(e) => setForm({ ...form, sortOrder: Number(e.target.value) })}
          style={{ ...fieldStyle, width: 96 }}
        />
      </label>
      <label
        style={{
          fontSize: 11,
          color: "var(--text-3)",
          display: "flex",
          gap: 6,
          alignItems: "center",
          paddingBottom: 8,
        }}
      >
        <input
          type="checkbox"
          checked={form.isActive}
          onChange={(e) => setForm({ ...form, isActive: e.target.checked })}
        />
        활성화
      </label>
      <button
        disabled={saveDisabled || busy}
        onClick={onSubmit}
        style={{
          padding: "6px 16px",
          background: "var(--accent)",
          color: "#061617",
          borderRadius: 5,
          fontSize: 12,
          fontWeight: 600,
          border: "none",
          cursor: "pointer",
          opacity: saveDisabled ? 0.5 : 1,
        }}
      >
        {form.id == null ? "추가" : "저장"}
      </button>
      <button
        onClick={onReset}
        style={{
          padding: "6px 16px",
          background: "transparent",
          color: "var(--text-3)",
          borderRadius: 5,
          fontSize: 12,
          border: "1px solid var(--border)",
          cursor: "pointer",
        }}
      >
        초기화
      </button>
    </div>
  );
}
