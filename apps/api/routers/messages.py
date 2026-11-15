from __future__ import annotations

from fastapi import APIRouter

from apps.api.deps import Service, User
from apps.api.routers._mcp import mcp_read
from apps.api.schemas import Started

router = APIRouter(prefix="/messages", tags=["messages"])


def _tid(t) -> str:
    return t["thread_id"] if isinstance(t, dict) else str(t)


@router.get("/threads")
async def threads(user: dict = User, svc=Service) -> dict:
    res = await mcp_read(svc, user, "liaison", "list_messages", {})
    runs: dict[str, dict] = {}
    for r in svc.list_runs(user, "conversation", limit=500):
        runs.setdefault(r["subject"], r)
    items = res.get("threads") or []
    return {"threads": [{**(t if isinstance(t, dict) else {"thread_id": t}), "run": runs.get(_tid(t))} for t in items]}


@router.get("/threads/{thread_id}")
async def thread(thread_id: str, user: dict = User, svc=Service) -> dict:
    res = await mcp_read(svc, user, "liaison", "list_messages", {"thread_id": thread_id})
    runs = [r for r in svc.list_runs(user, "conversation", limit=500) if r["subject"] == thread_id]
    return {"thread_id": thread_id, "messages": res.get("messages") or [], "runs": runs}


@router.post("/threads/{thread_id}/reply", response_model=Started, status_code=202)
async def reply(thread_id: str, user: dict = User, svc=Service) -> Started:
    """Start the conversation graph: classify -> draft reply -> compliance -> approval interrupt."""
    await mcp_read(svc, user, "liaison", "list_messages", {"thread_id": thread_id})  # 404 if unknown
    run_id = await svc.start(user, "conversation", thread_id, f"Reply in {thread_id}")
    return Started(thread_id=run_id, events_url=f"/runs/{run_id}/events")
