"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, useApi } from "@/lib/api/client";
import { useRunEvents } from "@/lib/sse";
import { evidenceIndex, type RunState } from "@/lib/types";
import { ApprovalPanel, ClaimText } from "@/components/ApprovalPanel";
import { RunTimeline } from "@/components/RunTimeline";
import { Badge, ErrorBox, Loading } from "@/components/States";

/** Proposal studio: the draft with evidence on every claim, the analysts' reports, and the approval panel. */
export default function Studio() {
  const { id } = useParams<{ id: string }>();
  const [gen, setGen] = useState(0);
  const { data, error, loading, reload } = useApi(() => api.GET("/runs/{thread_id}", { params: { path: { thread_id: id } } }), [id, gen]);
  const { events, ended } = useRunEvents(id, gen);
  useEffect(() => { if (ended) void reload(); }, [ended, reload]);

  if (loading && !data) return <Loading label="Loading draft" />;
  if (error || !data) return <ErrorBox error={error ?? { status: 404, message: "not found" }} retry={reload} />;
  const s = data.state as RunState;
  const index = evidenceIndex(s);
  const running = ["running", "resuming", "queued"].includes(data.status);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-bold mr-auto">{data.title || s.job?.title || data.subject}</h1>
          <Badge value={data.status} />
          <Link href={`/runs/${id}`} className="btn">Run details</Link>
        </div>
        {s.attention_reason && <p role="status" className="text-sm rounded border border-line bg-panel2 p-2">{s.attention_reason}</p>}
        {s.approval_request ? (
          <ApprovalPanel request={s.approval_request} index={index} onDone={() => setGen((g) => g + 1)} />
        ) : s.draft ? (
          <section className="card">
            <h2 className="font-semibold mb-2">Draft v{s.draft.version}</h2>
            <ClaimText text={s.draft.cover_letter ?? s.draft.text ?? ""} claims={s.draft.claims ?? []} index={index} />
          </section>
        ) : running ? <Loading label="Agents are working" /> : <p className="text-sm text-muted">No draft for this job (decision: {s.decision?.action ?? "—"}).</p>}
        {s.submission && (
          <div className="card text-sm" data-testid="submission">
            Submitted <code>{s.submission.proposal_id}</code> · {s.submission.connects_cost} Connects · key <code>{s.submission.idempotency_key}</code>{s.submission.replayed ? " (replayed, not charged twice)" : ""}
          </div>
        )}
      </div>
      <aside className="space-y-4">
        {s.decision && (
          <div className="card text-sm space-y-1"><h2 className="font-semibold">Decision <Badge value={s.decision.action} /></h2>
            <ul className="list-disc ml-4 text-muted">{s.decision.reasons.map((r) => <li key={r}>{r}</li>)}</ul></div>
        )}
        {s.fit && (
          <div className="card text-sm"><h2 className="font-semibold">Fit {Math.round(s.fit.score * 100)}%</h2>
            {s.fit.gaps.length > 0 && <p className="text-bad">Gaps: {s.fit.gaps.join(", ")}</p>}</div>
        )}
        {s.risk && (
          <div className="card text-sm"><h2 className="font-semibold">Risk <Badge value={s.risk.verdict} /></h2>
            <ul className="list-disc ml-4 text-muted">{s.risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            {s.risk.injection_spans.length > 0 && <p className="mt-1 text-warn">Ignored instructions in the post: “{s.risk.injection_spans[0].slice(0, 120)}”</p>}</div>
        )}
        {s.critique && (
          <div className="card text-sm"><h2 className="font-semibold">Critic (round {s.critique.round})</h2>
            {s.critique.issues.length ? <ul className="list-disc ml-4 text-muted">{s.critique.issues.map((i) => <li key={i}>{i}</li>)}</ul> : <p className="text-muted">No issues.</p>}</div>
        )}
        <div className="card"><h2 className="font-semibold mb-2 text-sm">Progress</h2><RunTimeline events={events} trace={s.trace} /></div>
      </aside>
    </div>
  );
}
