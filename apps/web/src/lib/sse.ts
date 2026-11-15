"use client";
// Live run progress over SSE. EventSource reconnects on its own and sends Last-Event-ID,
// so the API replays whatever was missed.
import { useEffect, useRef, useState } from "react";
import { API_URL } from "./api/client";

export type NodeItem = { node: string; event: string; status?: string | null; note?: string | null };
export type RunEvent =
  | { id: number; type: "node"; items: NodeItem[] }
  | { id: number; type: "status"; status: string }
  | { id: number; type: "end"; status: string }
  | { id: number; type: "custom"; data: unknown };

export function useRunEvents(threadId: string | undefined, generation = 0) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [end, setEnd] = useState<{ key: string; status: string } | null>(null);
  const lastId = useRef(0);
  const key = `${threadId}#${generation}`;
  useEffect(() => {
    if (!threadId) return;
    const after = lastId.current;
    const es = new EventSource(`${API_URL}/runs/${threadId}/events?after=${after}`, { withCredentials: true });
    const onEvent = (e: MessageEvent) => {
      const ev = JSON.parse(e.data) as RunEvent;
      lastId.current = Math.max(lastId.current, ev.id);
      setEvents((prev) => (prev.some((p) => p.id === ev.id) ? prev : [...prev, ev]));
      if (ev.type === "end") {
        setEnd({ key, status: ev.status });
        es.close();
      }
    };
    for (const t of ["node", "status", "end", "custom"]) es.addEventListener(t, onEvent as EventListener);
    return () => es.close();
  }, [threadId, key]);
  return { events, ended: end?.key === key ? end.status : null };
}
