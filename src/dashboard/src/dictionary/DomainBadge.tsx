import { useEffect, useRef, useState } from "react";
import type { DomainOption } from "../data";
import { DOMAIN_LABEL } from "./types";

interface Props {
  domain: string;
  domains: DomainOption[];
  itemId: number;
  onUpdate: (id: number, newDomain: string) => void;
}

export function DomainBadge({ domain, domains, itemId, onUpdate }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const label = domains.find((d) => d.id === domain)?.label ?? DOMAIN_LABEL[domain] ?? domain;

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen(!open)}
        title="도메인 변경"
        style={{
          padding: "2px 8px",
          borderRadius: 4,
          border: "1px solid var(--border)",
          background: domain === "all" ? "var(--bg-3)" : "var(--accent-weak)",
          color: domain === "all" ? "var(--text-3)" : "var(--accent)",
          fontSize: 11,
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
        }}
      >
        {label} ▾
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            zIndex: 400,
            background: "var(--bg-1)",
            border: "1px solid var(--border-hi)",
            borderRadius: 6,
            minWidth: 130,
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
            marginTop: 2,
          }}
        >
          {[{ id: "all", label: "전체 (공통)" } as DomainOption, ...domains].map((d) => (
            <button
              key={d.id}
              onClick={() => {
                onUpdate(itemId, d.id);
                setOpen(false);
              }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "7px 12px",
                fontSize: 11,
                background: d.id === domain ? "var(--accent-weak)" : "transparent",
                color: d.id === domain ? "var(--accent)" : "var(--text-2)",
                border: "none",
                cursor: "pointer",
                fontFamily: "var(--font-mono)",
              }}
            >
              {d.label ?? d.id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
