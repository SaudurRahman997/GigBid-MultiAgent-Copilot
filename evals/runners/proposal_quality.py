"""B5 proposal columns per retrieval variant: unsupported claims per proposal, LLM rubric score,
simulated reply rate, latency and USD cost, all on the same letters.

For each persona the first N dev jobs whose gold decision is "bid" are used. Letters come from the
same deterministic writer as gigsim_outcomes.py (one retrieval per job, top 3), so only the
retriever changes. Claims are checked with the configured claim judge BEFORE any repair. The rubric
judge is a local model reading agent/prompts/proposal_rubric.v1.md. It is UNCALIBRATED until
human labels exist (evals/runners/judge_calibration.py).

Writes evals/results/rag/<split>/proposal_quality.json (+ .jobs.jsonl).
Usage: uv run python -m evals.runners.proposal_quality [--jobs 10] [--judge-model llama3.2:3b]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime

from agent.prompt_loader import render
from agent.runtime import parse_json, untrusted
from evals.metrics import mean, percentile
from evals.runners import gigsim_outcomes
from evals.runners.rag_eval import OUT, git_sha, read_jobs
from rag.models import default_reranker
from rag.query import from_job
from rag.variants import CONTEXT_VARIANTS
from rag.variants.base import default_context
from rag.verify import config as verify_config
from rag.verify import default_judge, verify

VARIANTS = ["bm25_baseline", *CONTEXT_VARIANTS]
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]
CRITERIA = ("relevance", "specificity", "personalisation", "clarity")


def parse_scores(text: str) -> dict[str, int] | None:
    """The judge's four scores, or None if the reply is unusable (never guessed)."""
    try:
        data = parse_json(text)
        scores = {c: int(data[c]) for c in CRITERIA}
    except (ValueError, KeyError, TypeError):
        return None
    return scores if all(1 <= v <= 5 for v in scores.values()) else None


def summarize(rows: list[dict]) -> dict:
    judged = [r["judge_score"] for r in rows if r["judge_score"] is not None]
    latency = [r["retrieval_ms"] for r in rows]
    claims = sum(r["claims"] for r in rows)
    return {
        "proposals": len(rows),
        "unsupported_claims_per_proposal": round(mean([r["unsupported"] for r in rows]), 4),
        "unsupported_claim_rate": round(sum(r["unsupported"] for r in rows) / claims, 4)
        if claims
        else 0.0,
        "judge_score_mean": round(mean(judged), 4) if judged else None,
        "judge_parse_failures": len(rows) - len(judged),
        "retrieval_ms_p50": round(percentile(latency, 50), 1),
        "retrieval_ms_p95": round(percentile(latency, 95), 1),
        "usd_per_proposal": 0.0,
    }


def make_letters(variant: str, persona: str, n_jobs: int) -> list[dict]:
    from rag.retriever import get_retriever

    if variant in CONTEXT_VARIANTS:
        retriever = CONTEXT_VARIANTS[variant](default_context(persona))
    else:
        retriever = get_retriever(persona, variant)
    jobs = [j for j in read_jobs("dev", persona) if j["_gold"]["bid"] == "bid"][:n_jobs]
    rows = []
    for job in jobs:
        query = from_job(job["title"], job["description"], job.get("skills"))
        start = time.perf_counter()
        if variant in CONTEXT_VARIANTS:
            hits = retriever.retrieve(query, 3)
        else:  # the lexical baseline takes one string
            hits = retriever.search(" ".join(query.sub_queries()), 3)
        ms = (time.perf_counter() - start) * 1000
        text = gigsim_outcomes.letter(job, hits) if hits else gigsim_outcomes.GENERIC
        rows.append({"variant": variant, "persona": persona, "job": job, "letter": text,
                     "retrieval_ms": round(ms, 1)})  # fmt: skip
    return rows


def main(argv: list[str] | None = None) -> int:
    from langchain_ollama import ChatOllama

    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=VARIANTS)
    ap.add_argument("--jobs", type=int, default=10, help="bid jobs per persona")
    ap.add_argument("--judge-model", default="llama3.2:3b")
    args = ap.parse_args(argv)
    model = ChatOllama(model=args.judge_model, temperature=0.0, num_predict=120,
                       client_kwargs={"timeout": 180})  # fmt: skip
    claim_judge, cfg = default_judge(), verify_config()
    checkers = {p: CONTEXT_VARIANTS[cfg["retrieval_variant"]](default_context(p)) for p in PERSONAS}
    results, all_rows = {}, []
    for variant in args.variants:
        rows = [r for p in PERSONAS for r in make_letters(variant, p, args.jobs)]
        for i, row in enumerate(rows, start=1):
            checks = verify(row["letter"], checkers[row["persona"]], claim_judge, cfg["k"])
            row["claims"] = len(checks)
            row["unsupported"] = sum(c.status == "unsupported" for c in checks)
            job = row.pop("job")
            row["job_id"] = job["job_id"]
            prompt = render(
                "proposal_rubric",
                job=untrusted("JOB", f"{job['title']}\n\n{job['description']}"),
                proposal=untrusted("PROPOSAL", row["letter"]),
            )
            try:
                scores = parse_scores(str(model.invoke(prompt).content))
            except Exception as exc:  # noqa: BLE001 - counted as a parse failure, not scored
                print(f"  judge error: {type(exc).__name__}: {exc}"[:300], flush=True)
                scores = None
            row["judge_scores"] = scores
            row["judge_score"] = mean(list(scores.values())) if scores else None
            if i % 10 == 0:
                print(f"  {variant} {i}/{len(rows)}", flush=True)
        if hasattr(default_reranker(), "flush"):
            default_reranker().flush()
        results[variant] = {
            "overall": summarize(rows),
            "per_persona": {p: summarize([r for r in rows if r["persona"] == p]) for p in PERSONAS},
        }
        all_rows += rows
        print(variant, results[variant]["overall"], flush=True)
        write(args, claim_judge.name, results, all_rows)  # keep partial results if interrupted
    return 0


def write(args, claim_judge: str, results: dict, rows: list[dict]) -> None:
    out = {
        "runner": "evals/runners/proposal_quality.py",
        "git_sha": git_sha(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jobs_per_persona": args.jobs,
        "writer": "deterministic template (gigsim_outcomes.letter, one retrieval per job, top 3)",
        "claim_judge": claim_judge,
        "rubric_judge": f"ollama:{args.judge_model}",
        "rubric_judge_calibrated": False,
        "variants": results,
    }
    folder = OUT / "dev"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "proposal_quality.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with (folder / "proposal_quality.jobs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


if __name__ == "__main__":
    sys.exit(main())
