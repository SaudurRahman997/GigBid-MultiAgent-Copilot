"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, toError, useApi, type ApiError } from "@/lib/api/client";
import { useRunEvents } from "@/lib/sse";
import type { RunState } from "@/lib/types";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { Badge, Empty, ErrorBox, Loading } from "@/components/States";

type Msg = { id: string; sender: string; text: string };

function Conversation({ threadId, initialRun }: { threadId: string; initialRun?: string }) {
  const msgs = useApi(() => api.GET("/messages/threads/{thread_id}", { params: { path: { thread_id: threadId } } }), [threadId]);
  const [run, setRun] = useState<string | undefined>(initialRun);
  const [gen, setGen] = useState(0);
  const [err, setErr] = useState<ApiError>();
  const state = useApi(() => (run ? api.GET("/runs/{thread_id}", { params: { path: { thread_id: run } } }) : Promise.resolve({ data: undefined, response: new Response(null, { status: 200 }) })), [run, gen]);
  const { ended } = useRunEvents(run, gen);
  useEffect(() => { if (ended) { void state.reload(); void msgs.reload(); } }, [ended]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = ((msgs.data as { messages?: Msg[] } | undefined)?.messages ?? []);
  const s = (state.data as { state?: RunState; status?: string } | undefined);
  async function draft() {
    const r = await api.POST("/messages/threads/{thread_id}/reply", { params: { path: { thread_id: threadId } } });
    if (r.error || !r.response.ok) setErr(toError(r.response.status, r.error));
    else { setRun(r.data!.thread_id); setGen((g) => g + 1); }
  }
  return (
    <section className="space-y-3" aria-label={`Conversation ${threadId}`}>
      {msgs.loading && <Loading />}
      {msgs.error && <ErrorBox error={msgs.error} retry={msgs.reload} />}
      <ol className="space-y-2">
        {list.map((m) => (
          <li key={m.id} className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${m.sender === "client" ? "bg-panel2" : "bg-accent/15 ml-auto"}`}>
            <span className="block text-xs text-muted">{m.sender}</span>{m.text}
          </li>
        ))}
      </ol>
      {s?.state?.intent && <p className="text-sm">Intent: <Badge value={s.state.intent.intent} /> {s.state.intent.injection_spans.length > 0 && <span className="text-warn">· injection attempt ignored</span>}</p>}
      {s?.state?.approval_request ? (
        <ApprovalPanel request={s.state.approval_request} index={{}} onDone={() => setGen((g) => g + 1)} />
      ) : (
        <div className="flex items-center gap-2">
          <button className="btn btn-primary" onClick={draft}>Draft a reply</button>
          {s?.status && <Badge value={s.status} />}
        </div>
      )}
      {err && <ErrorBox error={err} />}
    </section>
  );
}

function MessagesInner() {
  const params = useSearchParams();
  const runParam = params.get("run") ?? undefined;
  const { data, error, loading, reload } = useApi(() => api.GET("/messages/threads"), []);
  const threads = ((data as { threads?: { thread_id: string; run?: { thread_id: string; status: string } | null }[] } | undefined)?.threads ?? []);
  const [active, setActive] = useState<string>();
  const current = active ?? threads.find((t) => t.run?.thread_id === runParam)?.thread_id ?? threads[0]?.thread_id;
  const currentRun = threads.find((t) => t.thread_id === current)?.run?.thread_id;
  return (
    <div className="grid gap-4 md:grid-cols-[240px_1fr]">
      <nav aria-label="Threads" className="space-y-1">
        <h1 className="text-2xl font-bold mb-2">Messages</h1>
        {loading && <Loading />}
        {error && <ErrorBox error={error} retry={reload} />}
        {!loading && !error && threads.length === 0 && <Empty title="No conversations yet" />}
        {threads.map((t) => (
          <button key={t.thread_id} onClick={() => setActive(t.thread_id)} aria-current={t.thread_id === current}
            className={`w-full text-left rounded px-3 py-2 text-sm ${t.thread_id === current ? "bg-accent/15" : "hover:bg-panel2"}`}>
            {t.thread_id} {t.run && <Badge value={t.run.status} />}
          </button>
        ))}
      </nav>
      {current && <Conversation key={current} threadId={current} initialRun={currentRun} />}
    </div>
  );
}

export default function Messages() {
  return <Suspense fallback={<Loading />}><MessagesInner /></Suspense>;
}
