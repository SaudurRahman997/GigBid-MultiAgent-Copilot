"use client";
import { useId, useState } from "react";
import type { Claim, EvidenceRef } from "@/lib/types";

const TONE = { supported: "decoration-good", partial: "decoration-warn", unsupported: "decoration-bad" } as const;

/** A claim in the draft; hover or keyboard focus shows the portfolio evidence behind it. */
export function EvidenceHover({ claim, index }: { claim: Claim; index: Record<string, EvidenceRef> }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const refs = claim.evidence.map((e) => index[e] ?? { evidence_id: e, snippet: "(evidence text not loaded)", score: 0 });
  return (
    <span className="relative inline">
      <span
        tabIndex={0}
        role="button"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className={`underline decoration-2 underline-offset-4 cursor-help outline-none focus-visible:ring-2 ring-accent rounded ${TONE[claim.status]}`}
        data-testid="claim"
      >
        {claim.text}
      </span>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-0 top-full z-20 mt-1 w-80 max-w-[85vw] rounded-lg border border-line bg-panel p-3 text-xs shadow-lg"
        >
          <span className="block font-semibold mb-1">
            {claim.status} · {refs.length} evidence item{refs.length === 1 ? "" : "s"}
          </span>
          {refs.length === 0 && <span className="block text-bad">No evidence found — remove or rephrase this claim.</span>}
          {refs.map((r) => (
            <span key={r.evidence_id} className="block border-t border-line pt-1 mt-1">
              <code className="text-muted">{r.evidence_id}</code>
              <span className="block">{r.snippet.slice(0, 260)}</span>
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
