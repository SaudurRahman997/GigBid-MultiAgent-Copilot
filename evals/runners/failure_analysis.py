"""Failure analysis: group failed dev jobs into the BUILD_SPEC taxonomy and measure fixes.

Taxonomy: missed evidence, wrong skip, mispriced, unsupported claim, generic opening, compliance miss,
injection, tool error.

Sources (every row is a dev job; nothing is hand-labelled):
  graph       the bid graph in rules mode on all 600 dev jobs (in-process tools), run here
  injection   evals/results/injection/asr.jobs.jsonl  (letters where the planted instruction succeeded
              with prompt defences only, i.e. before the output filter)
  llm graph   evals/results/multiagent/graph.jobs.jsonl  (tool / runtime errors with the local model)

Fixes are config overrides re-run on the same 600 jobs, so "did it work" is measured, not argued:
  clamp_price_to_band   pricing.clamp_to_band = true                       (targets: mispriced)
  lower_client_floor    decision.min_client_score 0.35 -> 0.30             (targets: wrong skip, poor client)
  more_evidence         evidence sentences in the letter 3 -> 4 (writer.letter_evidence)  (targets: missed evidence)

Writes evals/results/failures/failures.json (+ failures.jobs.jsonl).
Usage: uv run python -m evals.runners.failure_analysis
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "failures"
PERSONAS = ("ai_ml", "fullstack", "data_analyst")
FIXES = {
    "clamp_price_to_band": {"pricing": {"clamp_to_band": True}},
    "lower_client_floor": {"decision": {"min_client_score": 0.30}},
    "more_evidence": {"writer": {"letter_evidence": 4}},
}
TARGETS = {
    "clamp_price_to_band": "mispriced",
    "lower_client_floor": "wrong_skip",
    "more_evidence": "missed_evidence",
}
GENERIC = yaml.safe_load((ROOT / "gigsim" / "config.yaml").read_text(encoding="utf-8"))[
    "generic_opening_patterns"
]


def merged(cfg: dict, override: dict) -> dict:
    out = copy.deepcopy(cfg)
    for section, values in override.items():
        out.setdefault(section, {}).update(values)
    return out


async def collect(cfg: dict) -> list[dict]:
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.nodes.proposal import check_compliance
    from agent.runtime import Deps
    from evals.inprocess_mcp import FakeMCP
    from evals.runners.rag_eval import read_jobs

    graph = build_bid_graph(cfg, checkpointer=InMemorySaver())
    rows = []
    for p in PERSONAS:
        mcp = FakeMCP(p)
        deps = Deps(mcp=mcp, config=cfg, user=p)
        for j in read_jobs("dev", p):
            tid = f"fail:{j['job_id']}"
            out = await graph.ainvoke(
                {"job_id": j["job_id"], "thread_id": tid, "user": p},
                {"configurable": {"thread_id": tid}},
                context=deps,
            )
            g, d = j["_gold"], out.get("decision")
            letter = (
                out["__interrupt__"][0].value["draft"]["cover_letter"]
                if out.get("__interrupt__")
                else ""
            )
            price = out["price"].amount if out.get("price") else None
            rep = out.get("verify_report") or {}
            rows.append({
                "job_id": j["job_id"], "persona": p, "gold_bid": g["bid"], "gold_reason": g["skip_reason"],
                "pred_bid": "bid" if d and d.action == "bid" else "skip", "reason": (d.reasons[0] if d and d.reasons else ""),
                "price": price, "band": [g["price_band"]["low"], g["price_band"]["high"]],
                "in_band": None if price is None or g["bid"] != "bid" else g["price_band"]["low"] <= price <= g["price_band"]["high"],
                "gold_evidence": g.get("evidence_ids") or [], "cited": sorted(set(re.findall(r"\[([^\]\s]+:[^\]\s]+)\]", letter))),
                "unsupported_before": rep.get("unsupported_before", 0), "claims": rep.get("claims_before", 0),
                "generic_opening": bool(letter) and any(re.search(pt, "\n".join(letter.splitlines()[:2])) for pt in GENERIC),
                "violations": check_compliance(letter, deps.policy, []).violations if letter else [],
                "errors": [str(e)[:200] for e in (out.get("errors") or [])], "letter": letter,
            })  # fmt: skip
    return rows


def categorize(r: dict) -> list[str]:
    cats = []
    if r["gold_bid"] != r["pred_bid"]:
        cats.append("wrong_skip")
    if r["gold_bid"] == "bid" and r["pred_bid"] == "bid":
        if r["in_band"] is False:
            cats.append("mispriced")
        if r["gold_evidence"] and not set(r["cited"]) & set(r["gold_evidence"]):
            cats.append("missed_evidence")
    if r["unsupported_before"]:
        cats.append("unsupported_claim")
    if r["generic_opening"]:
        cats.append("generic_opening")
    if r["violations"]:
        cats.append("compliance_miss")
    if r["errors"]:
        cats.append("tool_error")
    return cats


def metrics(rows: list[dict]) -> dict:
    from evals.runners.decision_eval import metrics as dm

    m = dm([{"gold_bid": r["gold_bid"], "pred_bid": r["pred_bid"], "gold_scam": False, "pred_scam": False,
             "gold_reason": r["gold_reason"], "pred_reason": None, "in_band": r["in_band"]} for r in rows])  # fmt: skip
    counts = {}
    for r in rows:
        for c in categorize(r):
            counts[c] = counts.get(c, 0) + 1
    return {
        "bid_skip_macro_f1": m["bid_skip_macro_f1"],
        "price_in_band": m["price_in_band"],
        "failures": counts,
    }


def main(argv: list[str] | None = None) -> int:
    from agent.marketplace_port import load_config
    from evals.runners.rag_eval import git_sha

    cfg = load_config()
    base_rows = asyncio.run(collect(cfg))
    base = metrics(base_rows)
    print("base", json.dumps(base), flush=True)

    inj = [json.loads(x) for x in (ROOT / "evals/results/injection/asr.jobs.jsonl").read_text(encoding="utf-8").splitlines() if x] \
        if (ROOT / "evals/results/injection/asr.jobs.jsonl").exists() else []  # fmt: skip
    llm = [
        json.loads(x)
        for x in (ROOT / "evals/results/multiagent/graph.jobs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x
    ]
    base["failures"]["injection"] = sum(r["prompt_success"] for r in inj)
    base["failures"]["tool_error"] = base["failures"].get("tool_error", 0) + sum(
        bool(r.get("error")) for r in llm
    )

    fixes = {}
    for name, override in FIXES.items():
        m = metrics(asyncio.run(collect(merged(cfg, override))))
        target = TARGETS[name]
        before, after = base["failures"].get(target, 0), m["failures"].get(target, 0)
        fixes[name] = {"override": override, "target": target, "target_failures_before": before, "target_failures_after": after,
                       "bid_skip_macro_f1": [base["bid_skip_macro_f1"], m["bid_skip_macro_f1"]],
                       "price_in_band": [base["price_in_band"], m["price_in_band"]],
                       "worked": after < before and m["bid_skip_macro_f1"] >= base["bid_skip_macro_f1"] - 0.005}  # fmt: skip
        print(name, json.dumps(fixes[name]), flush=True)

    examples = []
    for r in base_rows:  # up to 3 examples per category, so at least 10 failed jobs are shown
        for c in categorize(r):
            if sum(e["category"] == c for e in examples) < 3:
                examples.append({"category": c, "job_id": r["job_id"], "persona": r["persona"], "gold": r["gold_bid"],
                                 "pred": r["pred_bid"], "reason": r["reason"], "price": r["price"], "band": r["band"],
                                 "gold_evidence": r["gold_evidence"], "cited": r["cited"]})  # fmt: skip
    for r in [r for r in inj if r["prompt_success"]][:3]:
        examples.append({"category": "injection", "job_id": r["job_id"], "persona": r["persona"], "attack": r["attack"],
                         "blocked_by_output_filter": r["full_blocked"]})  # fmt: skip
    for r in [r for r in llm if r.get("error")][:3]:
        examples.append(
            {
                "category": "tool_error",
                "job_id": r["job_id"],
                "persona": r["persona"],
                "error": r["error"],
            }
        )
    summary = {"runner": "evals/runners/failure_analysis.py", "git_sha": git_sha(), "split": "dev",
               "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "jobs": len(base_rows),
               "base": base, "fixes": fixes, "examples": examples}  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "failures.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with (OUT / "failures.jobs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in base_rows:
            if categorize(r):
                f.write(
                    json.dumps(
                        {
                            **{k: v for k, v in r.items() if k != "letter"},
                            "categories": categorize(r),
                        }
                    )
                    + "\n"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
