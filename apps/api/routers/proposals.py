from __future__ import annotations

from fastapi import APIRouter

from apps.api.deps import Service, User
from apps.api.routers.runs import get_run
from apps.api.schemas import Run, RunDetail

router = APIRouter(prefix="/proposals", tags=["proposals"])
STAGES = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


@router.get("", response_model=list[Run])
def list_proposals(user: dict = User, svc=Service) -> list[dict]:
    return svc.list_runs(user, "bid")


@router.get("/pipeline")
def pipeline(user: dict = User, svc=Service) -> dict:
    """Kanban columns. Bid threads give drafted/submitted; conversation threads move a job further."""
    cols: dict[str, list] = {s: [] for s in STAGES}
    for r in svc.list_runs(user, limit=500):
        if r.get("stage") in cols:
            cols[r["stage"]].append(r)
    return {"columns": [{"stage": s, "items": cols[s]} for s in STAGES]}


@router.get("/{thread_id}", response_model=RunDetail)
async def get_proposal(thread_id: str, user: dict = User, svc=Service) -> dict:
    return await get_run(thread_id, user, svc)
