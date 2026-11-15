"""Interim lexical baseline (BM25 over title + text). Phase 4 adds V0-V8 for comparison."""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from rag.corpus import Document
from rag.retriever import EvidenceFilters, Hit, passes

TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")
SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def tokenize(text: str) -> list[str]:
    return [t.strip(".") for t in TOKEN.findall(text.lower()) if t.strip(".")]


def best_snippet(text: str, query_terms: set[str], width: int = 300) -> str:
    sentences = [
        s.strip() for s in SENT.split(text) if s.strip() and not s.startswith(("---", "#"))
    ]
    if not sentences:
        return text[:width]
    best = max(sentences, key=lambda s: len(query_terms & set(tokenize(s))))
    return best if len(best) <= width else best[: width - 1] + "…"


class BM25Retriever:
    variant = "bm25_baseline"

    def __init__(self, docs: tuple[Document, ...]):
        self.docs = docs
        self.bm25 = BM25Okapi([tokenize(f"{d.title} {d.text}") for d in docs]) if docs else None

    def search(
        self, requirement: str, k: int = 5, filters: EvidenceFilters | None = None
    ) -> list[Hit]:
        if not self.bm25:
            return []
        q = tokenize(requirement)
        scores = self.bm25.get_scores(q)
        order = sorted(range(len(self.docs)), key=lambda i: (-scores[i], self.docs[i].id))
        hits = []
        for i in order:
            d = self.docs[i]
            if scores[i] <= 0 or not passes(d, filters):
                continue
            hits.append(
                Hit(doc=d, score=round(float(scores[i]), 4), snippet=best_snippet(d.text, set(q)))
            )
            if len(hits) == k:
                break
        return hits
