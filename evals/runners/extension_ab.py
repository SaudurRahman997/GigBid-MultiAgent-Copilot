"""Extension X2 - proposal experiments: an A/B test of two proposal strategies in GigSim.

Arms (agent/config.yaml writer.strategy; rules-mode writer, everything else identical):
  A  evidence_first   restated need -> cited evidence -> skills -> price          (current default)
  B  outcome_first    quantified past result first -> need -> evidence -> price -> scoping question

Design: paired. Every dev job (all personas) on which the bid graph decides to bid is run through
the real graph (in-process tools, rules mode) once per arm, up to the approval interrupt. The
approved draft and price are submitted to a fresh in-process GigSim world per arm (same seed, chaos
off), simulated time advances 30 days, and the simulated client's outcome is read. The two worlds
are identical, so the same job meets the same client with the same hidden preferences; only the
letter differs.

Statistics: reply rate per arm, paired difference with a 95% CI, exact McNemar test on the
discordant pairs (the primary test), and a two-proportion z-test for reference.

Writes evals/results/extension/ab.json (+ ab.jobs.jsonl).
Usage: uv run python -m evals.runners.extension_ab [--jobs-per-persona 200]
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "extension"
PERSONAS = ("ai_ml", "fullstack", "data_analyst")
ARMS = {"A": "evidence_first", "B": "outcome_first"}


async def drafts(strategy: str, jobs: list[dict]) -> dict[str, dict]:
    """job_id -> {letter, price} for the jobs the graph bids on, with the given writer strategy."""
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.marketplace_port import load_config
    from agent.runtime import Deps
    from evals.inprocess_mcp import FakeMCP

    cfg = copy.deepcopy(load_config())
    cfg["writer"]["strategy"] = strategy
    graph = build_bid_graph(cfg, checkpointer=InMemorySaver())
    fakes = {p: FakeMCP(p) for p in PERSONAS}
    out = {}
    for j in jobs:
        tid = f"ab:{strategy}:{j['job_id']}"
        deps = Deps(mcp=fakes[j["_persona"]], config=cfg, user=j["_persona"])
        res = await graph.ainvoke({"job_id": j["job_id"], "thread_id": tid, "user": j["_persona"]},
                                  {"configurable": {"thread_id": tid}}, context=deps)  # fmt: skip
        if res.get("__interrupt__"):
            req = res["__interrupt__"][0].value
            out[j["job_id"]] = {
                "letter": req["draft"]["cover_letter"],
                "price": res["price"].amount,
            }
    return out


def outcomes(jobs: dict[str, dict], letters: dict[str, dict]) -> dict[str, str]:
    """Submit each letter to a fresh GigSim world; return job_id -> outcome after 30 simulated days."""
    from fastapi.testclient import TestClient
    from sqlalchemy import update

    from evals.runners.gigsim_outcomes import ADMIN, TOKENS
    from gigsim import db
    from gigsim.app import create_app
    from gigsim.settings import Settings

    tmp = Path(tempfile.mkdtemp())
    settings = Settings(database_url=f"sqlite:///{(tmp / 'gs.db').as_posix()}", error_rate=0.0, time_scale=0.0,
                        include_heldout=False, rate_limit_per_min=1_000_000, release_interval_min=10_000)  # fmt: skip
    by_proposal = {}
    with TestClient(create_app(settings)) as c:
        with c.app.state.engine.begin() as conn:
            conn.execute(update(db.users).values(connects=10_000_000))
        for job_id, d in letters.items():
            h = {"Authorization": f"Bearer {TOKENS[jobs[job_id]['_persona']]}"}
            p = c.post(
                "/proposals",
                headers=h,
                json={
                    "job_id": job_id,
                    "cover_letter": d["letter"][:5000],
                    "bid_amount": d["price"],
                },
            ).json()
            c.post(
                f"/proposals/{p['proposal_id']}/submit",
                headers={**h, "Idempotency-Key": f"ab:{job_id}"},
            )
            by_proposal[p["proposal_id"]] = job_id
        c.post("/admin/tick", headers=ADMIN, params={"minutes": 60 * 24 * 30})
        decisions = c.get("/admin/decisions", headers=ADMIN).json()["items"]
    return {
        by_proposal[d["proposal_id"]]: d["outcome"]
        for d in decisions
        if d["proposal_id"] in by_proposal
    }


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value (binomial test on the discordant pairs)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else 0.0
    if se == 0:
        return 0.0, 1.0
    z = (x2 / n2 - x1 / n1) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def main(argv: list[str] | None = None) -> int:
    from evals.runners.gigsim_outcomes import ANSWERED
    from evals.runners.rag_eval import git_sha, read_jobs

    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs-per-persona", type=int, default=200)
    a = ap.parse_args(argv)
    jobs = {
        j["job_id"]: {**j, "_persona": p}
        for p in PERSONAS
        for j in read_jobs("dev", p)[: a.jobs_per_persona]
    }

    letters = {arm: asyncio.run(drafts(s, list(jobs.values()))) for arm, s in ARMS.items()}
    common = sorted(
        set(letters["A"]) & set(letters["B"])
    )  # graph decisions do not depend on the writer
    res = {arm: outcomes(jobs, {k: letters[arm][k] for k in common}) for arm in ARMS}
    pairs = [
        (res["A"][k] in ANSWERED, res["B"][k] in ANSWERED)
        for k in common
        if k in res["A"] and k in res["B"]
    ]
    n = len(pairs)
    xa, xb = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
    b = sum(p[0] and not p[1] for p in pairs)  # A replied, B not
    c = sum(p[1] and not p[0] for p in pairs)  # B replied, A not
    diffs = [int(y) - int(x) for x, y in pairs]
    md = sum(diffs) / n
    sd = math.sqrt(sum((d - md) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
    z, pz = two_proportion_z(xa, n, xb, n)
    per_persona = {}
    for persona in PERSONAS:
        ks = [
            k for k in common if jobs[k]["_persona"] == persona and k in res["A"] and k in res["B"]
        ]
        if ks:
            per_persona[persona] = {"pairs": len(ks),
                                    "reply_rate_A": round(sum(res["A"][k] in ANSWERED for k in ks) / len(ks), 4),
                                    "reply_rate_B": round(sum(res["B"][k] in ANSWERED for k in ks) / len(ks), 4)}  # fmt: skip
    summary = {
        "runner": "evals/runners/extension_ab.py", "git_sha": git_sha(), "split": "dev",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arms": ARMS, "design": "paired: same jobs and clients in two identical GigSim worlds; 30 simulated days",
        "jobs_considered": len(jobs), "pairs": n,
        "reply_rate_A": round(xa / n, 4), "reply_rate_B": round(xb / n, 4),
        "difference_B_minus_A": round(md, 4),
        "difference_ci95": [round(md - 1.96 * sd / math.sqrt(n), 4), round(md + 1.96 * sd / math.sqrt(n), 4)],
        "discordant": {"A_only": b, "B_only": c},
        "mcnemar_exact_p": round(mcnemar_exact(b, c), 6),
        "two_proportion_z": round(z, 3), "two_proportion_p": round(pz, 6),
        "interview_rate_A": round(sum(res["A"][k] in {"interview", "hired"} for k in common if k in res["A"]) / n, 4),
        "interview_rate_B": round(sum(res["B"][k] in {"interview", "hired"} for k in common if k in res["B"]) / n, 4),
        "per_persona": per_persona,
    }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ab.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with (OUT / "ab.jobs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for k in common:
            f.write(json.dumps({"job_id": k, "persona": jobs[k]["_persona"], "outcome_A": res["A"].get(k), "outcome_B": res["B"].get(k),
                                "letter_A": letters["A"][k]["letter"], "letter_B": letters["B"][k]["letter"]}) + "\n")  # fmt: skip
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "pairs",
                    "reply_rate_A",
                    "reply_rate_B",
                    "difference_ci95",
                    "mcnemar_exact_p",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
