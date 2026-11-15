"""V4 - outcome-aware ranking: V3 scores boosted by what actually worked.

Evidence from won/replied proposals, rehired clients and top-rated reviews is boosted; evidence
from ignored proposals is damped (multipliers in agent/config.yaml rag.outcome_boost).
"""

import re

from rag.variants.v3_rerank import V3Rerank


def outcome_multiplier(doc, boost: dict) -> float:
    o = (doc.outcome or "").lower()
    m = 1.0
    if doc.type == "proposal":
        m *= boost.get(o, 1.0)
    if "rehired" in o:
        m *= boost["rehired"]
    rating = re.search(r"(\d\.\d)/5", o)
    if rating and float(rating.group(1)) >= 4.8:
        m *= boost["high_rating"]
    return m


class V4Outcome(V3Rerank):
    variant = "v4_outcome"
    description = "V3 + boost evidence from won/replied proposals and happy clients"

    def ranked_chunks(self, query):
        boost = self.cfg["outcome_boost"]
        scored = [(c, s * outcome_multiplier(c.doc, boost)) for c, s in super().ranked_chunks(query)]
        return sorted(scored, key=lambda cs: (-cs[1], cs[0].chunk_id))
