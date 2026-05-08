import type { DomainOption } from "../data";

interface Props {
  kind: "compound" | "stopword";
  word: string;
  setWord: (v: string) => void;
  domain: string;
  setDomain: (v: string) => void;
  domains: DomainOption[];
  busy: boolean;
  onSubmit: () => void;
}

export function AddEntryForm({ kind, word, setWord, domain, setDomain, domains, busy, onSubmit }: Props) {
  const isCompound = kind === "compound";
  return (
    <div
      style={{
        padding: "12px 20px",
        background: "var(--bg-2)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        gap: 10,
        alignItems: "flex-end",
        flexWrap: "wrap",
        flexShrink: 0,
      }}
    >
      <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
        {isCompound ? "복합명사 용어" : "불용어"}
        <input
          value={word}
          onChange={(e) => setWord(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSubmit();
          }}
          placeholder={isCompound ? "예: AI반도체클러스터" : "예: 관계자"}
          style={{
            padding: "5px 8px",
            background: "var(--bg-3)",
            border: "1px solid var(--border-hi)",
            borderRadius: 4,
            color: "var(--text)",
            fontSize: 12,
            outline: "none",
            width: isCompound ? 200 : 180,
          }}
        />
      </label>
      <label style={{ fontSize: 11, color: "var(--text-3)", display: "flex", flexDirection: "column", gap: 4 }}>
        도메인
        <select
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          style={{
            padding: "5px 8px",
            background: "var(--bg-3)",
            border: "1px solid var(--border-hi)",
            borderRadius: 4,
            color: "var(--text)",
            fontSize: 12,
            outline: "none",
          }}
        >
          <option value="all">전체 (공통)</option>
          {domains.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
      </label>
      <button
        disabled={!word.trim() || busy}
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
          opacity: !word.trim() ? 0.5 : 1,
        }}
      >
        {busy ? "등록 중…" : "등록"}
      </button>
    </div>
  );
}
