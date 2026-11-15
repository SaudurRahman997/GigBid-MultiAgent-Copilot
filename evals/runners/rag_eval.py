"""RAG evaluation: Recall@5, MRR and nDCG@10 per variant and persona, against gold labels built
by construction (data/devset; the held-out set only with --split test).

Writes, per variant:
  evals/results/rag/<split>/<variant>.json        metrics overall, per persona and breakdowns
  evals/results/rag/<split>/<variant>.jobs.jsonl  per-job ranking (for failure analysis)

Relevance: gold evidence_ids = grade 2 (Recall/MRR use these), related_evidence_ids = grade 1
(nDCG only). Jobs without gold evidence (missing-skill, scam) are scored separately as
"no-evidence jobs": the share where the variant returned nothing (correct refusal).

Usage:
  uv run python -m evals.runners.rag_eval --variants v0_naive v2_hybrid --personas ai_ml
  uv run python -m evals.runners.rag_eval --variants all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from evals.metrics import mean, mrr, ndcg_at_k, percentile, recall_at_k
from rag.models import default_embedder, default_reranker
from rag.query import from_job
from rag.variants import CONTEXT_VARIANTS
from rag.variants.base import build_context, rag_config

ROOT = Path(__file__).resolve().parents[2]
SPLIT_DIRS = {"dev": ROOT / "data" / "devset", "test": ROOT / "data" / "heldout"}
OUT = ROOT / "evals" / "results" / "rag"
K_RECALL, K_NDCG = 5, 10


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=ROOT, check=True).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def read_jobs(split: str, persona: str) -> list[dict]:
    path = SPLIT_DIRS[split] / f"{persona}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x]


def project_recall(ranked: list[str], anchors: list[str], project_of: dict, k: int) -> float:
    """Share of the job's anchor projects with at least one evidence item in the top k."""
    found = {project_of.get(d) for d in ranked[:k]}
    return sum(a in found for a in anchors) / len(anchors) if anchors else 0.0


def summarize(rows: list[dict]) -> dict:
    gold = [r for r in rows if r["gold"]]
    none = [r for r in rows if not r["gold"]]
    lat = [r["latency_ms"] for r in rows]
    return {
        "jobs_with_gold": len(gold),
        "recall@5": round(mean([r["recall@5"] for r in gold]), 4),
        "mrr": round(mean([r["mrr"] for r in gold]), 4),
        "ndcg@10": round(mean([r["ndcg@10"] for r in gold]), 4),
        "project_recall@5": round(mean([r["project_recall@5"] for r in gold]), 4),
        "refused_with_gold": round(mean([float(not r["ranked"]) for r in gold]), 4),
        "no_evidence_jobs": len(none),
        "correct_refusal_rate": round(mean([float(not r["ranked"]) for r in none]), 4) if none else None,
        "latency_ms_p50": round(percentile(lat, 50), 1),
        "latency_ms_p95": round(percentile(lat, 95), 1),
    }


def breakdowns(rows: list[dict]) -> dict:
    gold = [r for r in rows if r["gold"]]
    groups = {
        "has_implied_requirement": lambda r: "implied" in r["phrasings"],
        "has_synonym_requirement": lambda r: "synonym" in r["phrasings"],
        "names_every_skill": lambda r: set(r["phrasings"]) == {"name"},
        "two_anchor_projects": lambda r: r["anchors"] == 2,
    }
    out = {}
    for name, pred in groups.items():
        sel = [r for r in gold if pred(r)]
        out[name] = {"n": len(sel), "recall@5": round(mean([r["recall@5"] for r in sel]), 4),
                     "project_recall@5": round(mean([r["project_recall@5"] for r in sel]), 4),
                     "mrr": round(mean([r["mrr"] for r in sel]), 4)}  # fmt: skip
    return out


def evaluate(variant: str, personas: list[str], split: str, limit: int | None, index: str,
             db_url: str | None) -> dict:  # fmt: skip
    cfg = rag_config()
    per_persona, all_rows = {}, []
    for persona in personas:
        ctx = build_context(persona, default_embedder(), default_reranker(), cfg, index=index, db_url=db_url)
        retriever = CONTEXT_VARIANTS[variant](ctx)
        # evidence item -> project (proposals excluded: a past pitch is not proof of delivery)
        project_of = {d.id: d.project_id for d in ctx.docs if d.type != "proposal" and d.project_id}
        rows = []
        for job in read_jobs(split, persona)[:limit]:
            g = job["_gold"]
            gold = set(g["evidence_ids"])
            grades = {**dict.fromkeys(g["related_evidence_ids"], 1), **dict.fromkeys(gold, 2)}
            q = from_job(job["title"], job["description"], job.get("skills"))
            t0 = time.perf_counter()
            hits = retriever.retrieve(q, k=K_NDCG)
            ms = (time.perf_counter() - t0) * 1000
            ranked = [h.doc.id for h in hits]
            rows.append({
                "persona": persona, "job_id": job["job_id"], "job_type": g["job_type"],
                "gold": sorted(gold), "ranked": ranked, "latency_ms": round(ms, 1),
                "recall@5": recall_at_k(ranked, gold, K_RECALL), "mrr": mrr(ranked, gold),
                "ndcg@10": ndcg_at_k(ranked, grades, K_NDCG),
                "project_recall@5": project_recall(ranked, g["anchor_project_ids"], project_of, K_RECALL),
                "phrasings": sorted({r["phrasing"] for r in job.get("requirements", [])}),
                "anchors": len(g["anchor_project_ids"]),
            })  # fmt: skip
        if ctx.reranker is not None and hasattr(ctx.reranker, "flush"):
            ctx.reranker.flush()
        per_persona[persona] = {**summarize(rows), "breakdowns": breakdowns(rows)}
        all_rows += rows
        print(f"  {variant:<14} {persona:<13} R@5={per_persona[persona]['recall@5']:.3f} "
              f"projR@5={per_persona[persona]['project_recall@5']:.3f} "
              f"MRR={per_persona[persona]['mrr']:.3f} nDCG@10={per_persona[persona]['ndcg@10']:.3f}", flush=True)  # fmt: skip

    cfg_hash = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
    result = {
        "runner": "evals/runners/rag_eval.py",
        "variant": variant,
        "description": CONTEXT_VARIANTS[variant].description,
        "split": split,
        "personas": personas,
        "limit": limit,
        "index": index,
        "embedder": default_embedder().name,
        "reranker": default_reranker().name,
        "rag_config_sha": cfg_hash,
        "git_sha": git_sha(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall": {**summarize(all_rows), "breakdowns": breakdowns(all_rows)},
        "per_persona": per_persona,
    }
    out_dir = OUT / split
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{variant}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    with (out_dir / f"{variant}.jobs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in all_rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=["all"])
    ap.add_argument("--personas", nargs="+", default=["ai_ml", "fullstack", "data_analyst"])
    ap.add_argument("--split", choices=sorted(SPLIT_DIRS), default="dev")
    ap.add_argument("--limit", type=int, default=None, help="first N jobs per persona (smoke runs)")
    ap.add_argument("--index", choices=["memory", "pgvector"], default=None)
    ap.add_argument("--db-url", default=None)
    args = ap.parse_args(argv)
    variants = list(CONTEXT_VARIANTS) if args.variants == ["all"] else args.variants
    index = args.index or rag_config().get("index", "memory")
    if args.split == "test":
        print("WARNING: held-out test split - report only, never tune on these numbers", file=sys.stderr)
    for v in variants:
        r = evaluate(v, args.personas, args.split, args.limit, index, args.db_url)
        o = r["overall"]
        print(f"{v:<14} OVERALL R@5={o['recall@5']:.3f} projR@5={o['project_recall@5']:.3f} "
              f"MRR={o['mrr']:.3f} nDCG@10={o['ndcg@10']:.3f} "
              f"p95={o['latency_ms_p95']}ms -> evals/results/rag/{args.split}/{v}.json")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
