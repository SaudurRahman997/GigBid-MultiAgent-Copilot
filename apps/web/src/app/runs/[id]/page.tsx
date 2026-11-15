"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { api, useApi } from "@/lib/api/client";
import { useRunEvents } from "@/lib/sse";
import type { RunState } from "@/lib/types";
import { RunTimeline } from "@/components/RunTimeline";
import { Badge, ErrorBox, Loading } from "@/components/States";

/** One thread's run: live node-by-node timeline (SSE) and the checkpointed state. */
export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi(() => api.GET("/runs/{thread_id}", { params: { path: { thread_id: id } } }), [id]);
  const { events, ended } = useRunEvents(id);
  useEffect(() => { if (ended) void reload(); }, [ended, reload]);

  if (loading && !data) return <Loading label="Loading run" />;
  if (error || !data) return <ErrorBox error={error ?? { status: 404, message: "not found" }} retry={reload} />;
  const s = data.state as RunState;
  const total = (s.trace ?? []).reduce((a, t) => a + (t.ms ?? 0), 0);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold mr-auto">Run {id}</h1>
        <Badge value={data.status} />
        {data.status === "awaiting_approval" && data.kind === "bid" && <Link className="btn btn-primary" href={`/studio/${id}`}>Review &amp; approve</Link>}
        {data.status === "awaiting_approval" && data.kind === "conversation" && <Link className="btn btn-primary" href={`/messages?run=${id}`}>Review reply</Link>}
      </div>
      <p className="text-sm text-muted">{data.kind} · {data.subject} · {data.steps} steps · {data.tokens} tokens · {Math.round(total)} ms in nodes{data.next?.length ? ` · next: ${data.next.join(", ")}` : ""}</p>
      {s.attention_reason && <p role="status" className="text-sm rounded border border-line bg-panel2 p-2">{s.attention_reason}</p>}
      {s.errors?.length ? <ul className="text-sm text-bad list-disc ml-5">{s.errors.map((e) => <li key={e}>{e}</li>)}</ul> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="card"><h2 className="font-semibold mb-3">Timeline</h2><RunTimeline events={events} trace={s.trace} /></section>
        <section className="card"><h2 className="font-semibold mb-3">State</h2>
          <pre className="text-xs overflow-x-auto max-h-[60vh]">{JSON.stringify({ ...s, trace: undefined, job: s.job ? { title: s.job.title } : undefined }, null, 2)}</pre>
        </section>
      </div>
    </div>
  );
}
