"""Configurable pipeline for the one-component-at-a-time ablation (evals/runners/ablation.py).

Flags (all on = V4):  decompose  per-requirement queries (else one whole-post query)
                      bm25       add BM25 rankings to the fusion (else dense only)
                      rerank     cross-encoder re-scoring of the fused pool
                      outcome    outcome-aware boosts
                      structured structure-aware chunks (else fixed windows)
"""

from __future__ import annotations

from rag.variants.base import Variant, rrf, sigmoid
from rag.variants.v3_rerank import RERANK_POOL, combined_query
from rag.variants.v4_outcome import outcome_multiplier

COMPONENTS = ("decompose", "bm25", "rerank", "outcome", "structured")


class Pipeline(Variant):
    variant = "pipeline"
    description = "Configurable retrieval pipeline (ablation)"

    def __init__(self, ctx, **flags: bool):
        super().__init__(ctx)
        unknown = set(flags) - set(COMPONENTS)
        if unknown:
            raise ValueError(f"unknown components {unknown}")
        self.flags = {c: flags.get(c, True) for c in COMPONENTS}
        off = [c for c, on in self.flags.items() if not on]
        self.variant = "all_on" if not off else "no_" + "_".join(off)

    def ranked_chunks(self, query):
        f, n = self.flags, self.cfg["candidates"]
        dense = self.ctx.dense_structured if f["structured"] else self.ctx.dense_fixed
        queries = query.sub_queries() if f["decompose"] else [query.text]
        lists = []
        for q in queries:
            lists.append(dense.search(q, n))
            if f["bm25"]:
                lists.append(self.ctx.lexical.search(q, n))
        ranked = rrf(lists, self.cfg["rrf_k"])
        if f["rerank"] and self.ctx.reranker is not None:
            pool, seen = [], set()
            for c, _ in ranked:
                if c.doc_id not in seen:
                    seen.add(c.doc_id)
                    pool.append(c)
                if len(pool) == RERANK_POOL:
                    break
            logits = self.ctx.reranker.score(combined_query(query), [c.text for c in pool])
            ranked = [(c, sigmoid(s)) for c, s in zip(pool, logits, strict=True)]
        if f["outcome"]:
            boost = self.cfg["outcome_boost"]
            ranked = [(c, s * outcome_multiplier(c.doc, boost)) for c, s in ranked]
        return sorted(ranked, key=lambda cs: (-cs[1], cs[0].chunk_id))
