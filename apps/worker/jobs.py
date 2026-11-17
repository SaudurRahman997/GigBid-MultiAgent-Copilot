"""Worker jobs (Arq). Plain async functions over Arq's ctx, so they are testable without Redis.

ctx keys: "redis" (ArqRedis: enqueue_job), "service" (apps.api.service.GraphService, inline runs),
"config" (agent/config.yaml).

Idempotency:
  - a saved search is enqueued at most once per interval slot: job id "search:<user>:<name>:<slot>",
    slot = minutes since epoch // interval. Several schedulers or a restart cannot double-run a slot.
  - a job is analysed at most once per user: Arq job id = dedupe_key(user, job id), and analyze_job
    also skips when a bid run for that job already exists (survives Redis result expiry).
  - a client message starts at most one conversation run: job id "msg:<user>:<thread>:<message id>".
Nothing here sends anything: graph runs stop at the human-approval interrupt.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from apps.api import db


def dedupe_key(user_id: str, job_id: str) -> str:
    return f"analyze:{user_id}:{job_id}"


def interval_minutes(search: dict, config: dict) -> int:
    """The search's own interval, never faster than the marketplace floor in config.scheduling."""
    sched = config["scheduling"]
    floor = (
        sched["live_interval_min"]
        if config.get("marketplace") == "upwork_live"
        else sched["gigsim_interval_min"]
    )
    return max(int(search.get("every_minutes") or 60), int(floor))


def slot(now_s: float, minutes: int) -> int:
    return int(now_s // 60) // minutes


def _users(service) -> list[dict]:
    with service.engine.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                select(db.users.c.id, db.users.c.email, db.users.c.persona)
            ).mappings()
        ]


def _saved_searches(service, user_id: str) -> list[dict]:
    with service.engine.connect() as c:
        row = c.execute(
            select(db.settings.c.value).where(db.settings.c.tenant_id == user_id)
        ).first()
    return list((row[0] or {}).get("saved_searches") or []) if row else []


def _has_run(service, user_id: str, kind: str, subject: str) -> bool:
    q = select(db.runs.c.thread_id).where(
        db.runs.c.tenant_id == user_id, db.runs.c.kind == kind, db.runs.c.subject == subject
    )
    with service.engine.connect() as c:
        return c.execute(q).first() is not None


def _user(service, user_id: str) -> dict:
    return next(u for u in _users(service) if u["id"] == user_id)


async def schedule_saved_searches(ctx: dict, now_s: float | None = None) -> int:
    """Cron (every minute): enqueue each saved search whose interval slot has not run yet."""
    now_s = time.time() if now_s is None else now_s
    enqueued = 0
    for u in _users(ctx["service"]):
        for s in _saved_searches(ctx["service"], u["id"]):
            minutes = interval_minutes(s, ctx["config"])
            job = await ctx["redis"].enqueue_job(
                "run_saved_search",
                u["id"],
                s,
                _job_id=f"search:{u['id']}:{s['name']}:{slot(now_s, minutes)}",
            )
            enqueued += job is not None
    return enqueued


async def run_saved_search(ctx: dict, user_id: str, search: dict) -> int:
    """Search the marketplace (scout MCP tool) and enqueue one analysis per new job."""
    svc = ctx["service"]
    args: dict[str, Any] = {"query": search.get("query") or "", "limit": 20}
    if search.get("category"):
        args["category"] = search["category"]
    res = await svc.mcp(_user(svc, user_id)).call("scout", "search_jobs", args)
    enqueued = 0
    for item in res.get("items", []):
        job = await ctx["redis"].enqueue_job(
            "analyze_job",
            user_id,
            item["job_id"],
            item.get("title") or "",
            _job_id=dedupe_key(user_id, item["job_id"]),
        )
        enqueued += job is not None
    return enqueued


async def analyze_job(ctx: dict, user_id: str, job_id: str, title: str = "") -> str | None:
    """Run the bid graph for one job up to the approval interrupt (idempotent per user + job)."""
    svc = ctx["service"]
    if _has_run(svc, user_id, "bid", job_id):
        return None
    return await svc.start(_user(svc, user_id), "bid", job_id, title)


async def poll_messages(ctx: dict) -> int:
    """Cron: start a conversation run for each thread whose latest client message is new."""
    svc = ctx["service"]
    enqueued = 0
    for u in _users(svc):
        mcp = svc.mcp(u)
        for thread in (await mcp.call("liaison", "list_messages", {})).get("threads", []):
            tid = thread if isinstance(thread, str) else thread.get("thread_id")
            msgs = (await mcp.call("liaison", "list_messages", {"thread_id": tid})).get(
                "messages", []
            )
            last = msgs[-1] if msgs else None
            if last and last.get("sender") == "client":
                job = await ctx["redis"].enqueue_job(
                    "reply_to_thread", u["id"], tid, _job_id=f"msg:{u['id']}:{tid}:{last.get('id')}"
                )
                enqueued += job is not None
    return enqueued


async def reply_to_thread(ctx: dict, user_id: str, thread_id: str) -> str:
    """Run the conversation graph for a thread up to the message-approval interrupt."""
    svc = ctx["service"]
    return await svc.start(_user(svc, user_id), "conversation", thread_id, f"Thread {thread_id}")
