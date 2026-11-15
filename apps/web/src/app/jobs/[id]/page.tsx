"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, toError, useApi, type ApiError } from "@/lib/api/client";
import type { Run } from "@/lib/types";
import { Badge, ErrorBox, Loading } from "@/components/States";

type Job = { job_id: string; title: string; description: string; skills?: string[]; pay_type?: string; budget_usd?: number | null;
  hourly_low?: number | null; hourly_high?: number | null; connects_required?: number | null; screening_questions?: string[] };

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, error, loading, reload } = useApi(() => api.GET("/jobs/{job_id}", { params: { path: { job_id: id } } }), [id]);
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState<ApiError>();
  const d = data as { job: Job; runs: Run[] } | undefined;

  async function analyze() {
    setBusy(true);
    const r = await api.POST("/jobs/{job_id}/analyze", { params: { path: { job_id: id } } });
    setBusy(false);
    if (r.error || !r.response.ok) setStartError(toError(r.response.status, r.error));
    else router.push(`/runs/${r.data!.thread_id}`);
  }

  if (loading) return <Loading label="Loading job" />;
  if (error || !d) return <ErrorBox error={error ?? { status: 0, message: "not found" }} retry={reload} />;
  const { job, runs } = d;
  return (
    <article className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">{job.title}</h1>
        <p className="text-sm text-muted">{job.pay_type === "hourly" ? `$${job.hourly_low ?? "?"}–${job.hourly_high ?? "?"}/h` : `$${job.budget_usd ?? "?"} fixed`} · {job.connects_required ?? "?"} Connects</p>
        <div className="card">
          <p className="text-xs uppercase text-muted mb-2">Job post (untrusted client text)</p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{job.description}</p>
        </div>
        {job.screening_questions?.length ? (
          <div className="card"><h2 className="font-semibold mb-1">Screening questions</h2>
            <ul className="list-disc ml-5 text-sm">{job.screening_questions.map((q) => <li key={q}>{q}</li>)}</ul></div>
        ) : null}
      </div>
      <aside className="space-y-4">
        <div className="card space-y-2">
          <h2 className="font-semibold">Analyse &amp; draft</h2>
          <p className="text-sm text-muted">Runs the Job Analyst, Risk Assessor and Fit Matcher in parallel, decides bid/skip, then drafts a grounded proposal for your approval.</p>
          <button className="btn btn-primary w-full justify-center" onClick={analyze} disabled={busy}>{busy ? "Starting…" : "Analyse this job"}</button>
          {startError && <ErrorBox error={startError} />}
        </div>
        <div className="card">
          <h2 className="font-semibold mb-2">Runs</h2>
          {runs.length === 0 ? <p className="text-sm text-muted">Not analysed yet.</p> : (
            <ul className="space-y-2">{runs.map((r) => (
              <li key={r.thread_id} className="flex items-center gap-2 text-sm">
                <Link className="text-accent hover:underline" href={r.status === "awaiting_approval" ? `/studio/${r.thread_id}` : `/runs/${r.thread_id}`}>{r.thread_id}</Link>
                <Badge value={r.status} />
              </li>))}
            </ul>)}
        </div>
      </aside>
    </article>
  );
}
