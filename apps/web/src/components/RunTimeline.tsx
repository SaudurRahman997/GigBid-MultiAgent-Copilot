"use client";
import type { RunEvent } from "@/lib/sse";
import type { TraceLine } from "@/lib/types";

/** Node-by-node progress: live SSE events while running, the checkpointed trace afterwards. */
export function RunTimeline({ events, trace }: { events: RunEvent[]; trace?: TraceLine[] }) {
  const live = events.flatMap((e) => (e.type === "node" ? e.items.map((i) => ({ ...i, id: e.id })) : []));
  const rows = live.length ? live.map((l) => ({ node: l.node, note: l.note ?? l.event })) : (trace ?? []);
  if (!rows.length) return <p className="text-sm text-muted">No steps yet.</p>;
  return (
    <ol className="relative border-l border-line ml-2" aria-label="Run timeline" data-testid="run-timeline">
      {rows.map((r, i) => (
        <li key={i} className="ml-4 pb-3">
          <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-accent" aria-hidden />
          <p className="text-sm font-medium">{r.node}</p>
          {r.note && <p className="text-xs text-muted break-words">{r.note}</p>}
          {"ms" in r && typeof r.ms === "number" && (
            <p className="text-xs text-muted">
              {r.ms} ms{typeof (r as TraceLine).tokens === "number" ? ` · ${(r as TraceLine).tokens} tokens` : ""}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
