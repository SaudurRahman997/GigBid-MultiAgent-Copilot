"""Which retriever should `search_evidence` serve? Measured on the path the app really runs.

rag_eval.py scores each variant as one retrieval per job. The app does something else: the Fit
Matcher calls `search_evidence` once per requirement (first MAX_REQUIREMENTS, k=PER_REQUIREMENT
each) and the Writer keeps the first unique items (agent.nodes.proposal.evidence_list); the
rules-mode letter then cites the first `writer.letter_evidence` non-proposal items. This runner
replays exactly that for every candidate `rag.variant` and writes

  evals/results/rag/<split>/app_path.json

  writer_recall      share of gold evidence among the items handed to the Writer
  writer_mrr         reciprocal rank of the first gold item in that list
  letter_hit         share of jobs whose cited items contain at least one gold item
  letter_precision   share of cited items that are gold or related evidence
  latency_ms_*       time for all of a job's search calls

Usage: uv run python -m evals.runners.app_path_eval [--variants ...] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime

import yaml

from agent.handoffs import EvidenceRef, FitReport
from agent.nodes.proposal import evidence_list
from evals.metrics import mean, mrr, percentile, recall_at_k
from evals.runners.rag_eval import OUT, ROOT, SPLIT_DIRS, git_sha, read_jobs
from rag.query import from_job
from rag.retriever import get_retriever

MAX_REQUIREMENTS, PER_REQUIREMENT = 6, 3  # same as agent/nodes/analysis.py fit_matcher
DEFAULT_VARIANTS = ["bm25_baseline", "v0_naive", "v1_decompose", "v2_hybrid"]
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]
METRICS = ("writer_recall", "writer_mrr", "letter_hit", "letter_precision")


def writer_evidence(retriever, job: dict) -> list[str]:
    """Evidence ids the Writer receives for this job, produced by the app's own functions."""
    query = from_job(job["title"], job["description"], job.get("skills"))
    matrix = {}
    for requirement in query.requirements[:MAX_REQUIREMENTS]:
        hits = retriever.search(requirement[:500], PER_REQUIREMENT)
        matrix[requirement] = [
            EvidenceRef(evidence_id=h.doc.id, snippet=h.snippet, score=h.score) for h in hits
        ]
    return [e["id"] for e in evidence_list(FitReport(score=1.0, matrix=matrix))]


def score_job(ids: list[str], gold: set[str], related: set[str], letter_n: int) -> dict:
    cited = [i for i in ids if i.split(":")[1] != "proposal"][:letter_n]
    return {
        "writer_recall": recall_at_k(ids, gold, len(ids) or 1),
        "writer_mrr": mrr(ids, gold),
        "letter_hit": float(bool(set(cited) & gold)),
        "letter_precision": len(set(cited) & (gold | related)) / len(cited) if cited else 0.0,
    }


def summarize(rows: list[dict]) -> dict:
    latency = [r["latency_ms"] for r in rows]
    return {
        "jobs_with_gold": len(rows),
        **{m: round(mean([r[m] for r in rows]), 4) for m in METRICS},
        "latency_ms_p50": round(percentile(latency, 50), 1),
        "latency_ms_p95": round(percentile(latency, 95), 1),
    }


def evaluate(variant: str, split: str, limit: int | None, letter_n: int) -> dict:
    per_persona, all_rows = {}, []
    for persona in PERSONAS:
        retriever = get_retriever(persona, variant)
        retriever.search("warm up the index before timing", 1)
        rows = []
        for job in read_jobs(split, persona)[:limit]:
            gold = job["_gold"]
            if not gold["evidence_ids"]:
                continue
            start = time.perf_counter()
            ids = writer_evidence(retriever, job)
            ms = (time.perf_counter() - start) * 1000
            row = score_job(
                ids, set(gold["evidence_ids"]), set(gold["related_evidence_ids"]), letter_n
            )
            rows.append({**row, "latency_ms": ms})
        per_persona[persona] = summarize(rows)
        all_rows += rows
        print(f"  {variant:<14} {persona:<13} {per_persona[persona]}", flush=True)
    return {"overall": summarize(all_rows), "per_persona": per_persona}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=DEFAULT_VARIANTS)
    ap.add_argument("--split", choices=sorted(SPLIT_DIRS), default="dev")
    ap.add_argument("--limit", type=int, default=None, help="first N jobs per persona")
    ap.add_argument("--out", default="app_path.json")
    args = ap.parse_args(argv)
    config = yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))
    letter_n = int(config["writer"].get("letter_evidence", 3))
    result = {
        "runner": "evals/runners/app_path_eval.py",
        "split": args.split,
        "limit": args.limit,
        "max_requirements": MAX_REQUIREMENTS,
        "per_requirement": PER_REQUIREMENT,
        "letter_evidence": letter_n,
        "git_sha": git_sha(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "variants": {v: evaluate(v, args.split, args.limit, letter_n) for v in args.variants},
    }
    out = OUT / args.split / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name, res in result["variants"].items():
        print(f"{name:<14} {res['overall']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
