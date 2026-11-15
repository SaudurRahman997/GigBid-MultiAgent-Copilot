"""V1 - requirement decomposition: one dense query per requirement, merged with RRF."""

from rag.variants.base import Variant, rrf


class V1Decompose(Variant):
    variant = "v1_decompose"
    description = "One dense query per JobSpec requirement (structured chunks), RRF merge"

    def ranked_chunks(self, query):
        n = self.cfg["candidates"]
        lists = [self.ctx.dense_structured.search(q, n) for q in query.sub_queries()]
        return rrf(lists, self.cfg["rrf_k"])
