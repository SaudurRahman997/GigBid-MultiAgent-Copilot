"""V8 - corrective RAG as a small LangGraph loop.

  retrieve -> grade -> (rewrite -> retrieve)* -> answer | refuse


retrieve  V3 (hybrid + cross-encoder) for the current sub-queries
grade     evidence is "good" when its cross-encoder logit >= rag.crag.min_rerank_score
rewrite   expand each sub-query with the canonical skill names and aliases it implies
          (taxonomy), plus the job title - deterministic, no LLM, so evals are reproducible
refuse    after rag.crag.max_rounds without enough good evidence, return NOTHING: the writer
          then cannot ground a claim, which is the honest outcome for jobs outside the portfolio
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from rag.ingest.loaders import ROOT, detect_skills
from rag.query import RetrievalQuery
from rag.variants.base import sigmoid, to_hits
from rag.variants.v3_rerank import V3Rerank


class CragState(TypedDict, total=False):
    query: RetrievalQuery
    round: int
    ranked: list
    good: int
    refused: bool


@lru_cache(maxsize=1)
def _aliases_by_canon() -> dict[str, list[str]]:
    path = ROOT / "data" / "processed" / "skill_taxonomy.json"
    if not path.exists():
        return {}
    out: dict[str, list[str]] = {}
    for alias, canon in json.loads(path.read_text(encoding="utf-8"))["aliases"].items():
        out.setdefault(canon, []).append(alias)
    return out


def expand(query: RetrievalQuery) -> RetrievalQuery:
    subs = []
    for q in query.sub_queries():
        skills = detect_skills(q)
        extra = [a for s in skills for a in [s, *_aliases_by_canon().get(s, [])[:2]]]
        subs.append(" ".join([q, *extra, query.title]).strip())
    return RetrievalQuery(text=query.text, requirements=tuple(subs), title=query.title)


class V8Corrective(V3Rerank):
    variant = "v8_corrective"
    description = "Corrective loop: grade evidence, re-query, refuse when none"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.crag = self.cfg["crag"]
        self.threshold = sigmoid(float(self.crag["min_rerank_score"]))
        self.graph = self._build()

    def _build(self):
        g = StateGraph(CragState)

        def retrieve(s: CragState) -> CragState:
            return {"ranked": V3Rerank.ranked_chunks(self, s["query"])}

        def grade(s: CragState) -> CragState:
            seen, good = set(), 0
            for chunk, score in s["ranked"]:
                if chunk.doc_id not in seen and score >= self.threshold:
                    good += 1
                seen.add(chunk.doc_id)
            return {"good": good}

        def rewrite(s: CragState) -> CragState:
            return {"query": expand(s["query"]), "round": s.get("round", 0) + 1}

        def refuse(_: CragState) -> CragState:
            return {"ranked": [], "refused": True}

        def route(s: CragState) -> str:
            if s["good"] >= self.crag["min_good_hits"]:
                return "done"
            return "rewrite" if s.get("round", 0) < self.crag["max_rounds"] else "refuse"

        g.add_node("retrieve", retrieve)
        g.add_node("grade", grade)
        g.add_node("rewrite", rewrite)
        g.add_node("refuse", refuse)
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges(
            "grade", route, {"done": END, "rewrite": "rewrite", "refuse": "refuse"}
        )
        g.add_edge("rewrite", "retrieve")
        g.add_edge("refuse", END)
        return g.compile()

    def run(self, query: RetrievalQuery) -> CragState:
        return self.graph.invoke({"query": query, "round": 0})

    def ranked_chunks(self, query):
        return self.run(query)["ranked"]

    def retrieve(self, query, k=5, filters=None):
        return to_hits(self.ranked_chunks(query), k, filters)
