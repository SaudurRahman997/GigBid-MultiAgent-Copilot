"""One-component-at-a-time ablation of the full retrieval pipeline (R&D B).

Runs the full pipeline (decompose + bm25 + rerank + outcome + structured chunks) and, for each
component, the pipeline with only that component switched off. Same jobs, same metrics as
rag_eval. Writes evals/results/rag/<split>/ablation.json.

Usage: uv run python -m evals.runners.ablation [--personas ai_ml fullstack data_analyst]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime

from evals.metrics import mean, mrr, ndcg_at_k, recall_at_k
from evals.runners.rag_eval import OUT, git_sha, project_recall, read_jobs
from rag.models import default_embedder, default_reranker
from rag.query import from_job
from rag.variants.base import build_context, rag_config
from rag.variants.pipeline import COMPONENTS, Pipeline


def score(pipe: Pipeline, jobs: list[dict], project_of: dict) -> dict:
    rows = []
    for job in jobs:
        g = job["_gold"]
        gold = set(g["evidence_ids"])
        if not gold:
            continue
        grades = {**dict.fromkeys(g["related_evidence_ids"], 1), **dict.fromkeys(gold, 2)}
        ranked = [
            h.doc.id
            for h in pipe.retrieve(
                from_job(job["title"], job["description"], job.get("skills")), 10
            )
        ]
        rows.append(
            {
                "recall@5": recall_at_k(ranked, gold),
                "mrr": mrr(ranked, gold),
                "ndcg@10": ndcg_at_k(ranked, grades),
                "project_recall@5": project_recall(ranked, g["anchor_project_ids"], project_of, 5),
            }
        )
    return {
        m: round(mean([r[m] for r in rows]), 4)
        for m in ("recall@5", "project_recall@5", "mrr", "ndcg@10")
    } | {"jobs": len(rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", nargs="+", default=["ai_ml", "fullstack", "data_analyst"])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--off-in-base", nargs="*", default=["rerank", "outcome"], help="components absent from the best pipeline")
    args = ap.parse_args(argv)
    cfg = rag_config()
    # Ablate the BEST pipeline from the variant table: V2 hybrid (decompose + bm25 + structured;
    # reranking and outcome boosts did not improve it). Each row switches one component off.
    base = {c: c not in args.off_in_base for c in COMPONENTS}
    configs = [base] + [{**base, c: False} for c in COMPONENTS if base[c]]
    results: dict = {}
    for persona in args.personas:
        ctx = build_context(persona, default_embedder(), default_reranker(), cfg)
        project_of = {d.id: d.project_id for d in ctx.docs if d.type != "proposal" and d.project_id}
        jobs = read_jobs(args.split, persona)
        for flags in configs:
            pipe = Pipeline(ctx, **flags)
            t = time.perf_counter()
            res = score(pipe, jobs, project_of)
            results.setdefault(pipe.variant, {})[persona] = res
            print(
                f"  {pipe.variant:<16} {persona:<13} R@5={res['recall@5']:.3f} MRR={res['mrr']:.3f} "
                f"({time.perf_counter() - t:.0f}s)",
                flush=True,
            )
        default_reranker().flush()
    overall = {
        name: {
            m: round(mean([p[m] for p in per.values()]), 4)
            for m in ("recall@5", "project_recall@5", "mrr", "ndcg@10")
        }
        for name, per in results.items()
    }
    full_name = next(iter(results))  # first config = the best pipeline
    full = overall[full_name]
    delta = {
        name: {m: round(v - full[m], 4) for m, v in vals.items()}
        for name, vals in overall.items()
        if name != full_name
    }
    out = {
        "runner": "evals/runners/ablation.py",
        "split": args.split,
        "personas": args.personas,
        "git_sha": git_sha(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base": full_name, "overall": overall,
        "delta_vs_full": delta,
        "per_persona": results,
    }
    (OUT / args.split).mkdir(parents=True, exist_ok=True)
    (OUT / args.split / "ablation.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    for name, d in delta.items():
        print(f"{name:<16} dR@5={d['recall@5']:+.3f} dMRR={d['mrr']:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
