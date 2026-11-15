"""GraphService: starts, streams, resumes and inspects bid / conversation threads for one tenant.

Pending approvals are read back from the checkpointer (`aget_state(...).interrupts`), so a page
refresh or an API restart never loses them. With the Postgres checkpointer, runs that were mid-flight
when the process died are resumed on startup (`recover()`); the idempotency keys make the submit
step exactly-once even if it was interrupted halfway.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.types import Command
from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.runtime import Deps
from apps.api import db
from apps.api.streaming import Broker, jsonable, update_event

BID_STAGE = {"submitted": "submitted", "awaiting_approval": "drafted"}


class ThreadNotFound(LookupError):
    pass


class NotAwaitingApproval(RuntimeError):
    pass


def summarize(kind: str, values: dict, interrupts: list) -> dict:
    """Compact, JSON-safe view of a thread's state for the UI."""
    v = jsonable(values)
    keep = ("status", "attention_reason", "decision", "price", "risk", "fit", "spec", "draft", "critique",
            "compliance", "submission", "claims", "intent", "slots", "pipeline_stage", "sent_message_id",
            "job", "errors", "last_client_message")  # fmt: skip
    out = {k: v[k] for k in keep if k in v}
    out["trace"] = v.get("trace", [])
    out["approval_request"] = jsonable(interrupts[0].value) if interrupts else None
    return out


class GraphService:
    def __init__(self, engine: Engine, config: dict, mcp_factory: Callable[[str, str], Any],
                 llm: Callable[[str], Any] | None = None, checkpointer=None, store=None):  # fmt: skip
        self.engine = engine
        self.config = config
        self.mcp_factory = mcp_factory  # (persona, trace_id) -> object with async call(agent, tool, args)
        self.llm = llm
        self.store = store
        self.graphs = {
            "bid": build_bid_graph(config, checkpointer=checkpointer, store=store),
            "conversation": build_conversation_graph(config, checkpointer=checkpointer, store=store),
        }
        self.broker = Broker()
        self.tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------ helpers
    def deps(self, user: dict, trace_id: str) -> Deps:
        return Deps(mcp=self.mcp_factory(user["persona"], trace_id), config=self.config, user=user["id"],
                    llm=self.llm, store=self.store)  # fmt: skip

    def mcp(self, user: dict) -> Any:
        return self.mcp_factory(user["persona"], uuid.uuid4().hex)

    def run_row(self, user: dict, thread_id: str) -> dict:
        with self.engine.connect() as c:
            row = c.execute(select(db.runs).where(db.runs.c.thread_id == thread_id,
                                                  db.runs.c.tenant_id == user["id"])).mappings().first()  # fmt: skip
        if row is None:  # other tenants' threads look exactly like missing ones
            raise ThreadNotFound(thread_id)
        return dict(row)

    def _set(self, thread_id: str, **fields) -> None:
        with self.engine.begin() as c:
            c.execute(update(db.runs).where(db.runs.c.thread_id == thread_id).values(**fields))

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # ------------------------------------------------------------------ lifecycle
    async def start(self, user: dict, kind: str, subject: str, title: str = "") -> str:
        thread_id = f"{kind[:3]}-{uuid.uuid4().hex[:12]}"
        with self.engine.begin() as c:
            c.execute(db.runs.insert().values(thread_id=thread_id, tenant_id=user["id"], kind=kind, subject=subject,
                                              title=title[:200], status="queued", summary={}))  # fmt: skip
        if kind == "bid":
            payload: Any = {"job_id": subject, "thread_id": thread_id, "user": user["id"]}
        else:
            payload = {"thread_id": subject, "user": user["id"]}
        self._spawn(self._drive(user, thread_id, kind, payload))
        return thread_id

    async def resume(self, user: dict, thread_id: str, decision: dict) -> None:
        row = self.run_row(user, thread_id)
        state = await self.graphs[row["kind"]].aget_state({"configurable": {"thread_id": thread_id}})
        if not state.interrupts:
            raise NotAwaitingApproval(thread_id)
        self._set(thread_id, status="resuming")
        self._spawn(self._drive(user, thread_id, row["kind"], Command(resume=decision)))

    async def _drive(self, user: dict, thread_id: str, kind: str, payload: Any) -> None:
        graph = self.graphs[kind]
        cfg = {"configurable": {"thread_id": thread_id}}
        trace_id = uuid.uuid4().hex
        self._set(thread_id, status="running")
        await self.broker.publish(thread_id, {"type": "status", "status": "running", "trace_id": trace_id})
        error = None
        try:
            async for mode, chunk in graph.astream(payload, cfg, context=self.deps(user, trace_id),
                                                   stream_mode=["updates", "custom"]):  # fmt: skip
                if mode == "updates":
                    await self.broker.publish(thread_id, update_event(chunk))
                else:
                    await self.broker.publish(thread_id, {"type": "custom", "data": jsonable(chunk)})
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI and stored on the run
            error = f"{type(exc).__name__}: {exc}"
        snap = await graph.aget_state(cfg)
        summary = summarize(kind, snap.values, list(snap.interrupts))
        status = "awaiting_approval" if snap.interrupts else (summary.get("status") or "done")
        if error:
            status, summary["attention_reason"] = "error", error
        stage = BID_STAGE.get(status) if kind == "bid" else summary.get("pipeline_stage")
        fields = {"status": status, "stage": stage, "summary": summary, "steps": len(summary["trace"]),
                  "tokens": int(snap.values.get("tokens") or 0)}  # fmt: skip
        if title := (summary.get("job") or {}).get("title"):
            fields["title"] = title[:200]
        self._set(thread_id, **fields)
        await self.broker.publish(thread_id, {"type": "end", "status": status})

    async def recover(self, user_lookup: Callable[[str], dict | None]) -> int:
        """Resume runs that were mid-flight when the process stopped (needs a durable checkpointer)."""
        with self.engine.connect() as c:
            rows = c.execute(select(db.runs).where(db.runs.c.status.in_(["running", "resuming", "queued"]))).mappings().all()
        n = 0
        for row in rows:
            user = user_lookup(row["tenant_id"])
            state = await self.graphs[row["kind"]].aget_state({"configurable": {"thread_id": row["thread_id"]}})
            if user is None or not state.next:
                continue
            self._spawn(self._drive(user, row["thread_id"], row["kind"], None))
            n += 1
        return n

    # ------------------------------------------------------------------ reads
    async def state(self, user: dict, thread_id: str) -> dict:
        row = self.run_row(user, thread_id)
        snap = await self.graphs[row["kind"]].aget_state({"configurable": {"thread_id": thread_id}})
        return {**_public(row), "state": summarize(row["kind"], snap.values or {}, list(snap.interrupts)),
                "next": list(snap.next)}  # fmt: skip

    async def pending_approvals(self, user: dict) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(select(db.runs).where(db.runs.c.tenant_id == user["id"],
                                                   db.runs.c.status == "awaiting_approval")
                             .order_by(db.runs.c.updated_at.desc())).mappings().all()  # fmt: skip
        out = []
        for row in rows:
            snap = await self.graphs[row["kind"]].aget_state({"configurable": {"thread_id": row["thread_id"]}})
            if snap.interrupts:  # source of truth is the checkpoint, not the runs table
                out.append({**_public(row), "request": jsonable(snap.interrupts[0].value)})
        return out

    def list_runs(self, user: dict, kind: str | None = None, limit: int = 100) -> list[dict]:
        q = select(db.runs).where(db.runs.c.tenant_id == user["id"])
        if kind:
            q = q.where(db.runs.c.kind == kind)
        with self.engine.connect() as c:
            rows = c.execute(q.order_by(db.runs.c.created_at.desc()).limit(limit)).mappings().all()
        return [_public(r) for r in rows]

    async def wait_idle(self) -> None:
        """Test helper: wait for all background runs to finish."""
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)


def _public(row) -> dict:
    r = dict(row)
    r.pop("tenant_id", None)
    for k in ("created_at", "updated_at"):
        if r.get(k) is not None:
            r[k] = r[k].isoformat()
    return r
