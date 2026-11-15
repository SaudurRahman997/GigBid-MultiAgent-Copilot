"""GigSim reply/hire rate on a FIXED job set, per retrieval variant (R&D B: does better
retrieval raise reply rate?).

For each persona the first N dev jobs whose gold decision is "bid" are used. For each variant a
deterministic writer turns the top-3 retrieved evidence items into a proposal (restated need,
evidence sentences with ids, skills that the retrieved evidence actually shows, a bid at the
client's budget). A "generic" letter with no retrieval is the floor. Proposals are submitted to
an in-process GigSim (fresh SQLite DB, chaos off), simulated time is advanced 30 days, and the
simulated clients' outcomes are counted.

Writes evals/results/gigsim/outcomes.json.
Usage: uv run python -m evals.runners.gigsim_outcomes [--variants v0_naive v2_hybrid ...] [--jobs 30]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import update

from evals.metrics import mean
from evals.runners.rag_eval import git_sha, read_jobs
from gigsim import db
from gigsim.app import create_app
from gigsim.settings import Settings
from rag.ingest.loaders import detect_skills
from rag.query import from_job
from rag.variants import CONTEXT_VARIANTS
from rag.variants.base import default_context

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "gigsim"
TOKENS = {
    "ai_ml": "dev-token-ai-ml",
    "fullstack": "dev-token-fullstack",
    "data_analyst": "dev-token-data-analyst",
}
ADMIN = {"Authorization": "Bearer dev-admin-token"}
ANSWERED = {"replied", "interview", "hired"}
GENERIC = (
    "Dear Hiring Manager, I am very interested in your job posting. I have many years of "
    "experience and always deliver high quality work on time. I can start immediately."
)


def first_sentence(text: str) -> str:
    body = text.split("\n", 1)[-1] if text.startswith(("#", "CV")) else text
    s = body.replace("\n", " ").strip().split(". ")[0].strip()
    return s if s.endswith(".") else s + "."


def letter(job: dict, hits: list) -> str:
    q = from_job(job["title"], job["description"], job.get("skills"))
    need = q.requirements[0] if q.requirements else job["title"]
    job_skills = set(detect_skills(job["title"] + " " + job["description"])) | set(
        job.get("skills") or []
    )
    shown = (
        sorted({s for h in hits for s in h.doc.skills} & job_skills)
        or sorted({s for h in hits for s in h.doc.skills})[:4]
    )
    lines = [f"You described the goal as: {need.rstrip('.')}."]
    lines += [f"{first_sentence(h.snippet)} [{h.doc.id}]" for h in hits[:3]]
    if shown:
        lines.append(f"Tools I have used on that work: {', '.join(shown)}.")
    lines.append("Happy to share a short plan here on the platform.")
    return "\n\n".join(lines)


def run(variants: list[str], personas: list[str], n_jobs: int) -> dict:
    tmp = Path(tempfile.mkdtemp())
    settings = Settings(
        database_url=f"sqlite:///{(tmp / 'gs.db').as_posix()}",
        error_rate=0.0,
        time_scale=0.0,
        include_heldout=False,
        rate_limit_per_min=1_000_000,
        release_interval_min=10_000,
    )
    results: dict = {}
    with TestClient(create_app(settings)) as c:
        with c.app.state.engine.begin() as conn:
            conn.execute(update(db.users).values(connects=10_000_000))
        submitted: dict[str, list[str]] = {}
        for persona in personas:
            h = {"Authorization": f"Bearer {TOKENS[persona]}"}
            jobs = [j for j in read_jobs("dev", persona) if j["_gold"]["bid"] == "bid"][:n_jobs]
            for name in ["generic", *variants]:
                retriever = (
                    None if name == "generic" else CONTEXT_VARIANTS[name](default_context(persona))
                )
                for j in jobs:
                    if retriever is None:
                        text = GENERIC
                    else:
                        hits = retriever.retrieve(
                            from_job(j["title"], j["description"], j.get("skills")), 3
                        )
                        text = letter(j, hits) if hits else GENERIC
                    bid = float(j["budget_usd"] or j["hourly_low"] or 30)
                    p = c.post(
                        "/proposals",
                        headers=h,
                        json={
                            "job_id": j["job_id"],
                            "cover_letter": text[:5000],
                            "bid_amount": bid,
                        },
                    ).json()
                    c.post(
                        f"/proposals/{p['proposal_id']}/submit",
                        headers={**h, "Idempotency-Key": f"{name}:{j['job_id']}"},
                    )
                    submitted.setdefault(f"{name}|{persona}", []).append(p["proposal_id"])
        c.post("/admin/tick", headers=ADMIN, params={"minutes": 60 * 24 * 30})
        decisions = {
            d["proposal_id"]: d for d in c.get("/admin/decisions", headers=ADMIN).json()["items"]
        }
    for key, ids in submitted.items():
        name, persona = key.split("|")
        ds = [decisions[i] for i in ids]
        results.setdefault(name, {})[persona] = {
            "proposals": len(ds),
            "reply_rate": round(mean([float(d["outcome"] in ANSWERED) for d in ds]), 4),
            "interview_rate": round(
                mean([float(d["outcome"] in {"interview", "hired"}) for d in ds]), 4
            ),
            "hire_rate": round(mean([float(d["outcome"] == "hired") for d in ds]), 4),
            "mean_p": round(mean([d["features"]["p"] for d in ds]), 4),
            "mean_must_have_coverage": round(
                mean([d["features"].get("coverage", 0) for d in ds]), 4
            ),
        }
    overall = {
        name: {
            m: round(mean([p[m] for p in per.values()]), 4)
            for m in (
                "reply_rate",
                "interview_rate",
                "hire_rate",
                "mean_p",
                "mean_must_have_coverage",
            )
        }
        for name, per in results.items()
    }
    return {"overall": overall, "per_persona": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=list(CONTEXT_VARIANTS))
    ap.add_argument("--personas", nargs="+", default=["ai_ml", "fullstack", "data_analyst"])
    ap.add_argument("--jobs", type=int, default=30)
    args = ap.parse_args(argv)
    res = run(args.variants, args.personas, args.jobs)
    out = {
        "runner": "evals/runners/gigsim_outcomes.py",
        "jobs_per_persona": args.jobs,
        "git_sha": git_sha(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "writer": "deterministic template (top-3 evidence)",
        **res,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "outcomes.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    for name, o in res["overall"].items():
        print(
            f"{name:<14} reply={o['reply_rate']:.3f} interview={o['interview_rate']:.3f} hire={o['hire_rate']:.3f} "
            f"coverage={o['mean_must_have_coverage']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
