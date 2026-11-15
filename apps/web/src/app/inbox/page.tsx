"use client";
import Link from "next/link";
import { useState } from "react";
import { api, useApi } from "@/lib/api/client";
import { Badge, Empty, ErrorBox, Loading } from "@/components/States";

type JobItem = {
  job_id: string; title: string; category?: string; pay_type?: string; budget_usd?: number | null;
  hourly_low?: number | null; hourly_high?: number | null; connects_required?: number | null;
  applicants?: string | null; skills?: string[];
  run?: { thread_id: string; status: string } | null; decision?: { action: string } | null;
};

function pay(j: JobItem) {
  if (j.pay_type === "hourly") return j.hourly_low ? `$${j.hourly_low}–${j.hourly_high ?? "?"}/h` : "hourly";
  return j.budget_usd ? `$${j.budget_usd} fixed` : "fixed";
}

export default function Inbox() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, error, loading, reload } = useApi(
    () => api.GET("/jobs", { params: { query: { query: submitted || undefined, limit: 50 } } }),
    [submitted],
  );
  const pending = useApi(() => api.GET("/approvals"), []);
  const items = ((data as { items?: JobItem[] } | undefined)?.items ?? []);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="text-2xl font-bold mr-auto">Inbox</h1>
        <form onSubmit={(e) => { e.preventDefault(); setSubmitted(query); }} className="flex gap-2" role="search">
          <label htmlFor="q" className="sr-only">Search jobs</label>
          <input id="q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search jobs" className="input" />
          <button className="btn">Search</button>
        </form>
      </div>

      {(pending.data?.length ?? 0) > 0 && (
        <section aria-label="Waiting for you" className="card border-warn/50">
          <h2 className="font-semibold mb-2">Waiting for your approval ({pending.data!.length})</h2>
          <ul className="space-y-1">
            {pending.data!.map((p) => (
              <li key={p.thread_id}>
                <Link className="text-accent hover:underline" href={p.kind === "bid" ? `/studio/${p.thread_id}` : `/messages?run=${p.thread_id}`}>
                  {p.title || p.subject}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {loading && <Loading label="Loading jobs" />}
      {error && <ErrorBox error={error} retry={reload} />}
      {!loading && !error && items.length === 0 && <Empty title="No jobs found" hint="Try a different search, or add a saved search in Settings." />}
      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((j) => (
          <li key={j.job_id} className="card flex flex-col gap-2">
            <Link href={`/jobs/${j.job_id}`} className="font-medium hover:underline">{j.title}</Link>
            <p className="text-sm text-muted">{pay(j)} · {j.category ?? "other"} · {j.connects_required ?? "?"} Connects · {j.applicants ?? "?"} applicants</p>
            {j.skills?.length ? <p className="text-xs text-muted">{j.skills.slice(0, 6).join(" · ")}</p> : null}
            <div className="flex items-center gap-2 mt-auto">
              <Badge value={j.decision?.action} />
              <Badge value={j.run?.status} />
              <Link href={`/jobs/${j.job_id}`} className="btn ml-auto">Open</Link>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
