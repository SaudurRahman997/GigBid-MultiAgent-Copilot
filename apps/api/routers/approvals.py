from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.api.deps import Service, User
from apps.api.schemas import Decision, PendingApproval, Started
from apps.api.service import NotAwaitingApproval, ThreadNotFound

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[PendingApproval])
async def pending(user: dict = User, svc=Service) -> list[dict]:
    """Every thread paused at an approval interrupt, read from the checkpoints (refresh-safe)."""
    return await svc.pending_approvals(user)


@router.post("/{thread_id}", response_model=Started, status_code=202)
async def decide(thread_id: str, body: Decision, user: dict = User, svc=Service) -> Started:
    """Resume the interrupted graph with the human's decision (approve / edit / reject)."""
    if body.action == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "edit needs edited_text")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "reject needs a reason")
    try:
        await svc.resume(user, thread_id, body.model_dump(exclude_none=True))
    except ThreadNotFound:
        raise HTTPException(404, "thread not found") from None
    except NotAwaitingApproval:
        raise HTTPException(409, "thread is not waiting for approval") from None
    return Started(thread_id=thread_id, events_url=f"/runs/{thread_id}/events")
