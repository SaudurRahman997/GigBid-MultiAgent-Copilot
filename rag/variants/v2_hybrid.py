"""V2 - hybrid: per requirement, BM25 + dense rankings, all fused with reciprocal rank fusion.

BM25 catches exact tool names ("Power BI", "LangChain") that dense embeddings blur; dense
catches paraphrases and implied skills that BM25 misses.
"""

from rag.variants.base import Variant, rrf


class V2Hybrid(Variant):
    variant = "v2_hybrid"
    description = "Per requirement: BM25 + dense, reciprocal rank fusion"

    def ranked_chunks(self, query):
        n = self.cfg["candidates"]
        lists = []
        for q in query.sub_queries():
            lists.append(self.ctx.dense_structured.search(q, n))
            lists.append(self.ctx.lexical.search(q, n))
        return rrf(lists, self.cfg["rrf_k"])
