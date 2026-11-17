from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from apps.api.deps import Service, User
from apps.api.schemas import Run, RunDetail
from apps.api.service import ThreadNotFound
from apps.api.streaming import sse_format

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[Run])
def list_runs(
    kind: str | None = Query(None, pattern="^(bid|conversation)$"), user: dict = User, svc=Service
) -> list[dict]:
    return svc.list_runs(user, kind)


@router.get("/{thread_id}", response_model=RunDetail)
async def get_run(thread_id: str, user: dict = User, svc=Service) -> dict:
    try:
        return await svc.state(user, thread_id)
    except ThreadNotFound:
        raise HTTPException(404, "thread not found") from None


@router.get("/{thread_id}/events")
async def events(thread_id: str, after: int = Query(0, ge=0), last_event_id: str | None = Header(None),
                 user: dict = User, svc=Service) -> EventSourceResponse:  # fmt: skip
    """Live node-by-node progress (SSE). Reconnect with Last-Event-ID to replay what was missed."""
    try:
        svc.run_row(user, thread_id)
    except ThreadNotFound:
        raise HTTPException(404, "thread not found") from None
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    async def gen():
        async for ev in svc.broker.subscribe(thread_id, start):
            yield sse_format(ev)

    return EventSourceResponse(gen())
