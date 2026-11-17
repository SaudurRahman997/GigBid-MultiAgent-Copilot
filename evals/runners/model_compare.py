"""Model comparison: the bid graph with every node on one local open model, per configuration.

Same 50 dev jobs and the same scoring as R&D C (evals/runners/multiagent_eval.py, system "graph").
Quality: bid/skip macro-F1, scam P/R, price in band, reply rate in a fresh GigSim. Latency: mean and
p95 per job. Cost: local models have no API charge, so cost is tokens/job and throughput (tokens/s)
on the stated hardware.

The llama3.2:3b row is the R&D C graph run (evals/results/multiagent/graph.json), produced by the
same code on the same jobs; other models are run here.

Writes evals/results/models/<model>.json and evals/results/models/summary.json.
Usage: uv run python -m evals.runners.model_compare --models qwen2.5:3b qwen2.5:1.5b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "models"
KEEP = (
    "model",
    "decisions",
    "letters",
    "reply_rate",
    "tokens_per_job",
    "latency_mean_s",
    "latency_p95_s",
    "errors",
    "parse_errors",
    "git_sha",
)


def slug(model: str) -> str:
    return model.replace(":", "_").replace("/", "_")


def tokens_per_s(path: Path) -> float | None:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    t, s = sum(r["tokens"] for r in rows), sum(r["latency_s"] for r in rows)
    return round(t / s, 1) if s else None


def main(argv: list[str] | None = None) -> int:
    from evals.runners.budgets import hardware
    from evals.runners.multiagent_eval import run_system, sample_jobs, summarize

    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen2.5:3b", "qwen2.5:1.5b"])
    ap.add_argument("--jobs", type=int, default=50)
    ap.add_argument("--timeout", type=float, default=300)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = sample_jobs(a.jobs)
    for m in a.models:
        for role in ("STRONG", "SMALL", "FALLBACK_SMALL"):
            os.environ[f"GIGBID_{role}_PROVIDER"], os.environ[f"GIGBID_{role}_MODEL"] = "ollama", m
        from agent.llm import chat_model

        model = chat_model("strong")
        d = OUT / slug(m)
        d.mkdir(exist_ok=True)
        rows = asyncio.run(run_system("graph", jobs, model, a.timeout, out_dir=d))
        s = summarize("graph", rows, f"ollama:{m}")
        s["tokens_per_s"] = tokens_per_s(d / "graph.jobs.jsonl")
        (OUT / f"{slug(m)}.json").write_text(
            json.dumps(s, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(
            m,
            json.dumps(
                {
                    k: s[k]
                    for k in (
                        "decisions",
                        "reply_rate",
                        "tokens_per_job",
                        "latency_p95_s",
                        "tokens_per_s",
                    )
                }
            ),
            flush=True,
        )

    rows = {}
    base = json.loads((ROOT / "evals/results/multiagent/graph.json").read_text(encoding="utf-8"))
    base["tokens_per_s"] = tokens_per_s(ROOT / "evals/results/multiagent/graph.jobs.jsonl")
    base["source"] = "evals/results/multiagent/graph.json"
    rows[base["model"]] = {k: base.get(k) for k in (*KEEP, "tokens_per_s", "source")}
    for f in sorted(OUT.glob("*.json")):
        if f.name != "summary.json":
            s = json.loads(f.read_text(encoding="utf-8"))
            rows[s["model"]] = {k: s.get(k) for k in (*KEEP, "tokens_per_s")}
    summary = {
        "runner": "evals/runners/model_compare.py",
        "jobs": a.jobs,
        "hardware": hardware(),
        "usd_per_job": 0.0,
        "models": rows,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
