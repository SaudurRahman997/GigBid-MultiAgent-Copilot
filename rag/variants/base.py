"""Shared machinery for retrieval variants: per-persona context, fusion, doc aggregation.

Every variant implements `retrieve(query, k, filters) -> list[Hit]` (document level: one hit per
evidence id, best chunk as snippet) and inherits `search(requirement, k, filters)` used by the
Portfolio MCP server.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from rag.chunking import Chunk, chunk_documents
from rag.index import LexicalIndex, MemoryDenseIndex, PgVectorIndex
from rag.ingest.loaders import Document, load_persona
from rag.models import Embedder, Reranker, default_embedder, default_reranker
from rag.query import RetrievalQuery

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "agent" / "config.yaml"


def rag_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["rag"]


@dataclass(frozen=True)
class Hit:
    doc: Document
    score: float
    snippet: str
    chunk_id: str | None = None


@dataclass
class Context:
    persona: str
    docs: tuple[Document, ...]
    structured: list[Chunk]
    fixed: list[Chunk]
    dense_structured: object  # MemoryDenseIndex | PgVectorIndex
    dense_fixed: object
    lexical: LexicalIndex
    embedder: Embedder
    reranker: Reranker | None
    cfg: dict


def build_context(
    persona: str,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    cfg: dict | None = None,
    docs: tuple[Document, ...] | None = None,
    index: str | None = None,
    db_url: str | None = None,
) -> Context:
    cfg = cfg or rag_config()
    embedder = embedder or default_embedder()
    docs = docs if docs is not None else load_persona(persona)
    structured = chunk_documents(docs, "structured", cfg["chunking"])
    fixed = chunk_documents(docs, "fixed", cfg["chunking"])
    kind = index or cfg.get("index", "memory")
    if kind == "pgvector":
        if not db_url:
            raise ValueError("pgvector index needs db_url")
        ds, df = (
            PgVectorIndex(db_url, embedder, persona, "structured"),
            PgVectorIndex(db_url, embedder, persona, "fixed"),
        )
        ds.sync(structured)
        df.sync(fixed)
    else:
        ds, df = MemoryDenseIndex(structured, embedder), MemoryDenseIndex(fixed, embedder)
    return Context(
        persona, docs, structured, fixed, ds, df, LexicalIndex(structured), embedder, reranker, cfg
    )


@lru_cache(maxsize=8)
def default_context(persona: str) -> Context:
    return build_context(persona, reranker=default_reranker())


def rrf(ranked_lists: list[list[tuple[Chunk, float]]], k: int = 60) -> list[tuple[Chunk, float]]:
    """Reciprocal rank fusion over chunk rankings."""
    scores: dict[str, float] = {}
    by_id: dict[str, Chunk] = {}
    for ranking in ranked_lists:
        for rank, (chunk, _) in enumerate(ranking, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            by_id[chunk.chunk_id] = chunk
    order = sorted(scores, key=lambda cid: (-scores[cid], cid))
    return [(by_id[cid], scores[cid]) for cid in order]


def snippet(text: str, width: int = 300) -> str:
    body = text.split("\n", 1)[-1].strip()  # drop the title prefix line
    return body if len(body) <= width else body[: width - 1] + "…"


def to_hits(ranked: list[tuple[Chunk, float]], k: int, filters=None) -> list[Hit]:
    """Chunk ranking -> document hits (best chunk per evidence id), filters applied."""
    from rag.retriever import passes

    seen: set[str] = set()
    hits = []
    for chunk, score in ranked:
        if chunk.doc_id in seen or not passes(chunk.doc, filters):
            continue
        seen.add(chunk.doc_id)
        hits.append(Hit(chunk.doc, round(float(score), 6), snippet(chunk.text), chunk.chunk_id))
        if len(hits) == k:
            break
    return hits


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, x))))


class Variant:
    variant = "base"
    description = ""

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.cfg = ctx.cfg

    def ranked_chunks(self, query: RetrievalQuery) -> list[tuple[Chunk, float]]:
        raise NotImplementedError

    def retrieve(self, query: RetrievalQuery, k: int = 5, filters=None) -> list[Hit]:
        return to_hits(self.ranked_chunks(query), k, filters)

    def search(self, requirement: str, k: int = 5, filters=None) -> list[Hit]:
        return self.retrieve(RetrievalQuery.single(requirement), k, filters)
