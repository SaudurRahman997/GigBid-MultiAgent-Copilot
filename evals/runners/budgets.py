"""Budgets: measure p95 latency and cost per job analysed and per proposal against agent/config.yaml.

Two configurations:
  rules  the bid graph in deterministic rules mode on all 600 dev jobs (in-process tools), measured here
  llm    the bid graph with every node on the local model, from the R&D C per-job rows
         (evals/results/multiagent/graph.jobs.jsonl, written by evals/runners/multiagent_eval.py)

"Job analysed" = every job (the graph runs until it skips or stops at approval).
"Proposal"     = jobs on which the graph bids and reaches the approval interrupt with a draft.
Cost: the local model has no per-token API charge, so USD is 0 and the cost is reported as tokens
and throughput (tokens/s) on the stated hardware, as the spec asks for local models.

Writes evals/results/budgets/budgets.json.
Usage: uv run python -m evals.runners.budgets
"""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "budgets"
PERSONAS = ("ai_ml", "fullstack", "data_analyst")


def p95(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(0.95 * len(s)))], 3)


def hardware() -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Processor).Name; (Get-CimInstance Win32_VideoController).Name; "
                              "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)"],
                             capture_output=True, text=True, timeout=30).stdout  # fmt: skip
        lines = [x.strip() for x in out.splitlines() if x.strip()]
        return f"{'; '.join(lines[:-1])}; {lines[-1]} GB RAM" if lines else platform.processor()
    except Exception:  # noqa: BLE001
        return platform.processor()


async def rules_runs() -> list[dict]:
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.marketplace_port import load_config
    from agent.runtime import Deps
    from evals.inprocess_mcp import FakeMCP
    from evals.runners.rag_eval import read_jobs

    cfg = load_config()
    graph = build_bid_graph(cfg, checkpointer=InMemorySaver())
    fakes = {p: FakeMCP(p) for p in PERSONAS}
    rows = []
    for p in PERSONAS:
        for j in read_jobs("dev", p):
            tid = f"budget:{j['job_id']}"
            t0 = time.perf_counter()
            out = await graph.ainvoke({"job_id": j["job_id"], "thread_id": tid, "user": p}, {"configurable": {"thread_id": tid}},
                                      context=Deps(mcp=fakes[p], config=cfg, user=p))  # fmt: skip
            rows.append({"latency_s": time.perf_counter() - t0, "proposal": bool(out.get("__interrupt__")),
                         "steps": out.get("steps", 0), "tokens": out.get("tokens", 0)})  # fmt: skip
    return rows


def summarize(rows: list[dict], budgets: dict) -> dict:
    jobs = [r["latency_s"] for r in rows]
    props = [r["latency_s"] for r in rows if r["proposal"]]
    tok_jobs = [r["tokens"] for r in rows]
    tok_props = [r["tokens"] for r in rows if r["proposal"]]
    out = {
        "jobs": len(rows), "proposals": len(props),
        "p95_latency_s": {"job": p95(jobs), "proposal": p95(props)},
        "mean_tokens": {"job": round(sum(tok_jobs) / len(tok_jobs), 1) if tok_jobs else 0,
                        "proposal": round(sum(tok_props) / len(tok_props), 1) if tok_props else 0},
        "usd": {"job": 0.0, "proposal": 0.0},
    }  # fmt: skip
    out["within_budget"] = {
        "latency_job": out["p95_latency_s"]["job"] is not None and out["p95_latency_s"]["job"] <= budgets["p95_latency_s"]["job"],
        "latency_proposal": out["p95_latency_s"]["proposal"] is not None and out["p95_latency_s"]["proposal"] <= budgets["p95_latency_s"]["proposal"],
        "usd_job": out["usd"]["job"] <= budgets["usd"]["job"],
        "usd_proposal": out["usd"]["proposal"] <= budgets["usd"]["proposal"],
    }  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    from agent.marketplace_port import load_config
    from evals.runners.rag_eval import git_sha

    budgets = load_config()["budgets"]
    rules = summarize(asyncio.run(rules_runs()), budgets)
    llm_rows = [json.loads(x) for x in (ROOT / "evals/results/multiagent/graph.jobs.jsonl").read_text(encoding="utf-8").splitlines() if x]
    llm_src = json.loads((ROOT / "evals/results/multiagent/graph.json").read_text(encoding="utf-8"))
    llm = summarize([{"latency_s": r["latency_s"], "proposal": bool(r["letter"]), "tokens": r["tokens"]} for r in llm_rows], budgets)
    tot_tok, tot_s = sum(r["tokens"] for r in llm_rows), sum(r["latency_s"] for r in llm_rows)
    llm["tokens_per_s"] = round(tot_tok / tot_s, 1) if tot_s else None
    llm["model"] = llm_src["model"]
    llm["source"] = "evals/results/multiagent/graph.jobs.jsonl"
    summary = {
        "runner": "evals/runners/budgets.py", "git_sha": git_sha(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "declared": budgets, "hardware": hardware(),
        "configurations": {"rules": rules, "llm_local": llm},
    }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "budgets.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary["configurations"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
