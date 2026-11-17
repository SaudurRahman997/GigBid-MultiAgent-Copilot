"""Decision evaluation: bid/skip F1, scam precision/recall, price-in-band.

Deciders are pluggable. `keyword` is a deliberately naive baseline (scam keywords from the
policy pack, persona budget floors, must-have skills detected in the text vs the persona's
evidenced skills; no client-history check). Phase 5 adds `graph` (the LangGraph bid graph).

Gold: data/devset (bid/skip by the written rule, planted scams, real-price bands).
Writes evals/results/decision/<decider>.json.
Usage: uv run python -m evals.runners.decision_eval [--decider keyword]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from evals.metrics import f1, mean
from evals.runners.rag_eval import git_sha, read_jobs
from rag.ingest.loaders import detect_skills

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "decision"
SCAM_PATTERNS = [
    r"whats\s?app|telegram|outside the platform|off[- ]platform|bank transfer|your (email|phone|number)",
    r"deposit|registration fee|starter kit|training materials|refundable",
    r"usdt|bitcoin|\bbtc\b|crypto|wallet",
    r"unpaid|sample (project|task)|trial task|pay the winner",
    r"budget is not a problem|details will be shared|simple work, high pay|confidential project",
]


def keyword_decider(job: dict, profile: dict) -> dict:
    text = f"{job['title']}\n{job['description']}".lower()
    if any(re.search(p, text) for p in SCAM_PATTERNS):
        return {"bid": "skip", "reason": "scam", "is_scam": True, "price": None}
    must_lines = [ln for ln in job["description"].split("\n") if "(must have)" in ln.lower()]
    must = set(detect_skills(" ".join(must_lines))) if must_lines else set()
    if must - set(profile["skills"]):
        return {"bid": "skip", "reason": "missing_skill", "is_scam": False, "price": None}
    floors = profile["floors"]
    if job["pay_type"] == "fixed" and (job.get("budget_usd") or 0) < floors["fixed"]:
        return {"bid": "skip", "reason": "low_budget", "is_scam": False, "price": None}
    if job["pay_type"] == "hourly" and (job.get("hourly_high") or 0) < floors["hourly"]:
        return {"bid": "skip", "reason": "low_budget", "is_scam": False, "price": None}
    price = job.get("budget_usd") if job["pay_type"] == "fixed" else job.get("hourly_low")
    return {"bid": "bid", "reason": None, "is_scam": False, "price": price}


def graph_decider_factory():
    """The real bid graph (rules mode) up to its decision, over an in-process tool layer."""
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.marketplace_port import load_config
    from agent.runtime import Deps
    from evals.inprocess_mcp import FakeMCP

    cfg = load_config()
    graph = build_bid_graph(cfg, checkpointer=InMemorySaver())
    tools: dict[str, FakeMCP] = {}

    def decide(job: dict, profile: dict) -> dict:
        persona = profile["persona"]
        mcp = tools.setdefault(persona, FakeMCP(persona))
        deps = Deps(mcp=mcp, config=cfg, user=persona, llm=None)
        tid = f"eval:{job['job_id']}"
        out = asyncio.run(graph.ainvoke({"job_id": job["job_id"], "thread_id": tid, "user": persona},
                                        {"configurable": {"thread_id": tid}}, context=deps))  # fmt: skip
        d = out.get("decision")
        action = d.action if d else "skip"
        risk = out.get("risk")
        scam = bool(risk and risk.verdict == "block")
        reason = None
        if action != "bid":
            r = (d.reasons[0] if d and d.reasons else "").lower()
            reason = ("scam" if scam else "missing_skill" if "missing" in r else "low_budget" if "below floor" in r
                      else "poor_client" if "client" in r else "low_fit")  # fmt: skip
        price = out["price"].amount if out.get("price") else None
        return {
            "bid": "bid" if action == "bid" else "skip",
            "reason": reason,
            "is_scam": scam,
            "price": price,
        }

    return decide


DECIDERS = {"keyword": keyword_decider, "graph": None}


def evaluate(decider: str, personas: list[str], split: str) -> dict:
    per, all_rows = {}, []
    fn = graph_decider_factory() if decider == "graph" else DECIDERS[decider]
    for persona in personas:
        profile = json.loads(
            (ROOT / "data" / "personas" / persona / "profile.json").read_text(encoding="utf-8")
        )
        rows = []
        for job in read_jobs(split, persona):
            d = fn(job, profile)
            g = job["_gold"]
            band = g["price_band"]
            rows.append(
                {
                    "gold_bid": g["bid"],
                    "pred_bid": d["bid"],
                    "gold_scam": g["is_scam"],
                    "pred_scam": d["is_scam"],
                    "gold_reason": g["skip_reason"],
                    "pred_reason": d["reason"],
                    "in_band": None
                    if d["price"] is None or g["bid"] != "bid"
                    else band["low"] <= d["price"] <= band["high"],
                }
            )
        per[persona] = metrics(rows)
        all_rows += rows
    return {"overall": metrics(all_rows), "per_persona": per}


def metrics(rows: list[dict]) -> dict:
    def prf(pos_gold, pos_pred):
        tp = sum(pos_gold(r) and pos_pred(r) for r in rows)
        fp = sum(not pos_gold(r) and pos_pred(r) for r in rows)
        fn = sum(pos_gold(r) and not pos_pred(r) for r in rows)
        return tp, fp, fn

    tp, fp, fn = prf(lambda r: r["gold_bid"] == "bid", lambda r: r["pred_bid"] == "bid")
    stp, sfp, sfn = prf(lambda r: r["gold_bid"] == "skip", lambda r: r["pred_bid"] == "skip")
    ctp, cfp, cfn = prf(lambda r: r["gold_scam"], lambda r: r["pred_scam"])
    priced = [r["in_band"] for r in rows if r["in_band"] is not None]
    return {
        "jobs": len(rows),
        "bid_f1": round(f1(tp, fp, fn), 4),
        "skip_f1": round(f1(stp, sfp, sfn), 4),
        "bid_skip_macro_f1": round((f1(tp, fp, fn) + f1(stp, sfp, sfn)) / 2, 4),
        "accuracy": round(mean([float(r["gold_bid"] == r["pred_bid"]) for r in rows]), 4),
        "scam_precision": round(ctp / (ctp + cfp), 4) if ctp + cfp else 0.0,
        "scam_recall": round(ctp / (ctp + cfn), 4) if ctp + cfn else 0.0,
        "price_in_band": round(mean([float(x) for x in priced]), 4) if priced else None,
        "skip_reason_accuracy": round(
            mean(
                [
                    float(r["gold_reason"] == r["pred_reason"])
                    for r in rows
                    if r["gold_bid"] == "skip"
                ]
            ),
            4,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decider", choices=sorted(DECIDERS), default="keyword")
    ap.add_argument("--personas", nargs="+", default=["ai_ml", "fullstack", "data_analyst"])
    ap.add_argument("--split", default="dev")
    args = ap.parse_args(argv)
    res = evaluate(args.decider, args.personas, args.split)
    out = {
        "runner": "evals/runners/decision_eval.py",
        "decider": args.decider,
        "split": args.split,
        "git_sha": git_sha(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **res,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.decider}.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    o = res["overall"]
    print(
        f"{args.decider}: bid/skip macro-F1={o['bid_skip_macro_f1']:.3f} scam P={o['scam_precision']:.3f} "
        f"R={o['scam_recall']:.3f} price-in-band={o['price_in_band']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
