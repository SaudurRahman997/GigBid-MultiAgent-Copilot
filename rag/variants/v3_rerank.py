"""V3 - V2 candidates re-scored by a cross-encoder (bge-reranker-v2-m3).

The top RERANK_POOL fused chunks are scored against one combined query (need + requirements);
scores are logits -> sigmoid so later boosts (V4) are well-behaved. Scores are cached on disk.
"""

from rag.variants.base import sigmoid
from rag.variants.v2_hybrid import V2Hybrid

RERANK_POOL = 15


def combined_query(query) -> str:
    return " ; ".join(query.sub_queries())[:1000]


class V3Rerank(V2Hybrid):
    variant = "v3_rerank"
    description = "V2 candidates re-scored by a cross-encoder"

    def rerank(self, query, ranked):
        pool = []
        seen_docs = set()
        for chunk, _ in ranked:  # pool of chunks from distinct documents
            if chunk.doc_id not in seen_docs:
                seen_docs.add(chunk.doc_id)
                pool.append(chunk)
            if len(pool) == RERANK_POOL:
                break
        if not pool or self.ctx.reranker is None:
            return ranked
        logits = self.ctx.reranker.score(combined_query(query), [c.text for c in pool])
        rescored = [(c, sigmoid(s)) for c, s in zip(pool, logits, strict=True)]
        return sorted(rescored, key=lambda cs: (-cs[1], cs[0].chunk_id))

    def ranked_chunks(self, query):
        return self.rerank(query, super().ranked_chunks(query))
