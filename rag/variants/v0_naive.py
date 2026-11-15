"""V0 - naive dense retrieval: fixed ~200-word chunks, one query = the whole job post."""

from rag.variants.base import Variant


class V0Naive(Variant):
    variant = "v0_naive"
    description = "Dense, fixed chunks, top-k on the whole post"

    def ranked_chunks(self, query):
        return self.ctx.dense_fixed.search(query.text, self.cfg["candidates"] * 2)
