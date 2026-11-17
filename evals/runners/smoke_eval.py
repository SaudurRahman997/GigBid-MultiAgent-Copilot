"""CI eval gate: a 30-job smoke eval of the bid graph (rules mode, in-process tools; no model keys).

30 dev jobs (10 per persona, seeded sample). Gates from agent/config.yaml `ci_thresholds`:
  bid/skip macro-F1                      >= min_bid_skip_f1
  unsupported claims per proposal        <= max_unsupported_claims_per_proposal
     (share of the writer's claims the verifier marks unsupported, before repair, mean over proposals)
Exit code 1 when a gate fails, so .github/workflows/eval.yml fails the PR.

Writes evals/results/smoke/smoke.json.
Usage: uv run python -m evals.runners.smoke_eval [--jobs 30]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "smoke"
PERSONAS = ("ai_ml", "fullstack", "data_analyst")
SEED = 20261115


async def run(n: int) -> list[dict]:
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.marketplace_port import load_config
    from agent.runtime import Deps
    from evals.inprocess_mcp import FakeMCP
    from evals.runners.rag_eval import read_jobs

    cfg = load_config()
    graph = build_bid_graph(cfg, checkpointer=InMemorySaver())
    rng = random.Random(SEED)
    rows = []
    for p in PERSONAS:
        mcp = FakeMCP(p)
        for j in rng.sample(read_jobs("dev", p), n // len(PERSONAS)):
            tid = f"smoke:{j['job_id']}"
            out = await graph.ainvoke({"job_id": j["job_id"], "thread_id": tid, "user": p}, {"configurable": {"thread_id": tid}},
                                      context=Deps(mcp=mcp, config=cfg, user=p))  # fmt: skip
            d, risk, rep = out.get("decision"), out.get("risk"), out.get("verify_report") or {}
            g = j["_gold"]
            rows.append({"gold_bid": g["bid"], "pred_bid": "bid" if d and d.action == "bid" else "skip",
                         "gold_scam": g["is_scam"], "pred_scam": bool(risk and risk.verdict == "block"),
                         "gold_reason": g["skip_reason"], "pred_reason": None, "in_band": None,
                         "unsupported_rate": (rep["unsupported_before"] / rep["claims_before"]) if rep.get("claims_before") else None})  # fmt: skip
    return rows


def main(argv: list[str] | None = None) -> int:
    from agent.marketplace_port import load_config
    from evals.runners.decision_eval import metrics
    from evals.runners.rag_eval import git_sha

    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=30)
    a = ap.parse_args(argv)
    gates = load_config()["ci_thresholds"]
    rows = asyncio.run(run(a.jobs))
    f1 = metrics(rows)["bid_skip_macro_f1"]
    rates = [r["unsupported_rate"] for r in rows if r["unsupported_rate"] is not None]
    unsupported = round(sum(rates) / len(rates), 4) if rates else 0.0
    checks = {"bid_skip_macro_f1": {"value": f1, "min": gates["min_bid_skip_f1"], "ok": f1 >= gates["min_bid_skip_f1"]},
              "unsupported_claims_per_proposal": {"value": unsupported, "max": gates["max_unsupported_claims_per_proposal"],
                                                  "ok": unsupported <= gates["max_unsupported_claims_per_proposal"]}}  # fmt: skip
    summary = {"runner": "evals/runners/smoke_eval.py", "git_sha": git_sha(), "seed": SEED, "jobs": len(rows),
               "proposals": len(rates), "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "gates": checks, "passed": all(c["ok"] for c in checks.values())}  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "smoke.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary["gates"]))
    if not summary["passed"]:
        print("EVAL GATE FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
