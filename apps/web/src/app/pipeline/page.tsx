"use client";
import Link from "next/link";
import { api, useApi } from "@/lib/api/client";
import type { Run } from "@/lib/types";
import { ErrorBox, Loading } from "@/components/States";

export default function Pipeline() {
  const { data, error, loading, reload } = useApi(() => api.GET("/proposals/pipeline"), []);
  const cols = (data as { columns?: { stage: string; items: Run[] }[] } | undefined)?.columns ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Pipeline</h1>
      {loading && <Loading label="Loading pipeline" />}
      {error && <ErrorBox error={error} retry={reload} />}
      <div className="flex gap-3 overflow-x-auto pb-2 snap-x" role="list" aria-label="Pipeline columns">
        {cols.map((c) => (
          <section key={c.stage} role="listitem" aria-label={c.stage} className="snap-start shrink-0 w-64 rounded-xl bg-panel2 p-3">
            <h2 className="text-sm font-semibold capitalize mb-2">{c.stage} <span className="text-muted">({c.items.length})</span></h2>
            {c.items.length === 0 && <p className="text-xs text-muted">Nothing here yet.</p>}
            <ul className="space-y-2">
              {c.items.map((r) => (
                <li key={r.thread_id} className="card p-3 text-sm">
                  <Link href={r.kind === "bid" ? `/studio/${r.thread_id}` : `/runs/${r.thread_id}`} className="hover:underline">{r.title || r.subject}</Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
