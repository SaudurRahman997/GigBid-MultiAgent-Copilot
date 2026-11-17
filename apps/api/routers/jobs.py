from __future__ import annotations

from fastapi import APIRouter, Query

from apps.api.deps import Service, User
from apps.api.routers._mcp import mcp_read
from apps.api.schemas import Started

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(query: str | None = Query(None, max_length=200), category: str | None = Query(None, max_length=40),
                    limit: int = Query(20, ge=1, le=50), user: dict = User, svc=Service) -> dict:  # fmt: skip
    """Inbox: jobs from the marketplace (via the Scout's MCP allowlist) + any existing run per job."""
    res = await mcp_read(
        svc, user, "scout", "search_jobs", {"query": query, "category": category, "limit": limit}
    )
    runs = {r["subject"]: r for r in svc.list_runs(user, "bid", limit=500)}
    for item in res.get("items", []):
        run = runs.get(item["job_id"])
        item["run"] = {k: run[k] for k in ("thread_id", "status", "stage")} if run else None
        item["decision"] = ((run or {}).get("summary") or {}).get("decision")
    return res


@router.get("/{job_id}")
async def get_job(job_id: str, user: dict = User, svc=Service) -> dict:
    job = await mcp_read(svc, user, "scout", "get_job", {"job_id": job_id})
    runs = [r for r in svc.list_runs(user, "bid", limit=500) if r["subject"] == job_id]
    return {"job": job, "runs": runs}


@router.post("/{job_id}/analyze", response_model=Started, status_code=202)
async def analyze(job_id: str, user: dict = User, svc=Service) -> Started:
    """Start a bid thread for this job: analysis -> decision -> (draft -> approval interrupt)."""
    job = await mcp_read(svc, user, "scout", "get_job", {"job_id": job_id})
    thread_id = await svc.start(user, "bid", job_id, job.get("title", ""))
    return Started(thread_id=thread_id, events_url=f"/runs/{thread_id}/events")
