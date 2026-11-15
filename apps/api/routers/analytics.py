from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from fastapi import APIRouter

from apps.api.deps import Service, User

router = APIRouter(prefix="/analytics", tags=["analytics"])
RESULTS = Path(__file__).resolve().parents[3] / "evals" / "results"


def eval_summary() -> dict:
    """Headline numbers exactly as the eval runners wrote them (read, never recomputed here)."""
    out = {}
    for f in sorted((RESULTS / "decision").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out[f"decision/{f.stem}"] = {"overall": d.get("overall"), "git_sha": d.get("git_sha")}
        except (OSError, ValueError, AttributeError):
            continue
    return out


@router.get("")
def analytics(user: dict = User, svc=Service) -> dict:
    runs = svc.list_runs(user, limit=1000)
    bids = [r for r in runs if r["kind"] == "bid"]
    decisions = Counter(((r.get("summary") or {}).get("decision") or {}).get("action", "n/a") for r in bids)
    return {
        "runs": len(runs),
        "by_status": dict(Counter(r["status"] for r in runs)),
        "by_stage": dict(Counter(r["stage"] for r in runs if r.get("stage"))),
        "decisions": dict(decisions),
        "tokens": sum(r.get("tokens") or 0 for r in runs),
        "avg_steps": round(sum(r.get("steps") or 0 for r in runs) / len(runs), 1) if runs else 0,
        "submitted": sum(r["status"] == "submitted" for r in bids),
        "evals": eval_summary(),
    }
