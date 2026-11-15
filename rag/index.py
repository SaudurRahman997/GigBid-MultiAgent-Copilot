"""Chunk indexes: dense (cosine) + lexical (BM25), in memory or in Postgres/pgvector.

Both dense indexes expose the same `dense_search(query_vec, k, chunk_ids=None)`; the memory one
is used for fast, deterministic evals and tests, pgvector in deployment (same cosine metric).
Incremental indexing: chunks are keyed by chunk_id with a content hash, so re-indexing only
embeds new or changed chunks and deletes chunks whose document disappeared.
"""

from __future__ import annotations

import json
import re

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from rag.chunking import Chunk
from rag.models import Embedder

TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")


def tokenize(t: str) -> list[str]:
    return [w.strip(".") for w in TOKEN.findall(t.lower()) if w.strip(".")]


class LexicalIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c.text) for c in chunks]) if chunks else None

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        order = np.argsort(-scores, kind="stable")[:k]
        return [(self.chunks[i], float(scores[i])) for i in order if scores[i] > 0]


class MemoryDenseIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder):
        self.chunks = chunks
        self.embedder = embedder
        self.matrix = (
            embedder.embed_documents([c.text for c in chunks])
            if chunks
            else np.zeros((0, embedder.dim))
        )

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        q = self.embedder.embed_query(query)
        sims = self.matrix @ q
        order = np.argsort(-sims, kind="stable")[:k]
        return [(self.chunks[i], float(sims[i])) for i in order]


# ----------------------------------------------------------------------------- pgvector

pg_meta = MetaData(schema="gigbid")


def chunk_table(dim: int) -> Table:
    from pgvector.sqlalchemy import Vector

    return Table(
        "rag_chunks",
        pg_meta,
        Column("chunk_id", String, primary_key=True),
        Column("persona", String, index=True, nullable=False),
        Column("strategy", String, index=True, nullable=False),
        Column("doc_id", String, index=True, nullable=False),
        Column("idx", Integer, nullable=False),
        Column("content_hash", String, nullable=False),
        Column("text", Text, nullable=False),
        Column("metadata", JSONB, nullable=False),
        Column("embedding", Vector(dim), nullable=False),
        extend_existing=True,
    )


class PgVectorIndex:
    """Dense index in Postgres (pgvector, cosine distance, HNSW index). Incremental upserts."""

    def __init__(self, url: str, embedder: Embedder, persona: str, strategy: str):
        self.engine = create_engine(url, pool_pre_ping=True)
        self.embedder, self.persona, self.strategy = embedder, persona, strategy
        self.table = chunk_table(embedder.dim)
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS gigbid"))
        pg_meta.create_all(self.engine, tables=[self.table])
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS rag_chunks_hnsw ON gigbid.rag_chunks "
                    "USING hnsw (embedding vector_cosine_ops)"
                )
            )
        self._by_id: dict[str, Chunk] = {}

    def sync(self, chunks: list[Chunk]) -> dict:
        """Upsert new/changed chunks, delete stale ones. Returns counts (incremental re-index)."""
        self._by_id = {c.chunk_id: c for c in chunks}
        t = self.table
        scope = (t.c.persona == self.persona) & (t.c.strategy == self.strategy)
        with self.engine.begin() as conn:
            existing = dict(conn.execute(select(t.c.chunk_id, t.c.content_hash).where(scope)).all())
        changed = [c for c in chunks if existing.get(c.chunk_id) != c.content_hash]
        stale = sorted(set(existing) - set(self._by_id))
        vecs = self.embedder.embed_documents([c.text for c in changed]) if changed else []
        with self.engine.begin() as conn:
            if stale:
                conn.execute(delete(t).where(t.c.chunk_id.in_(stale)))
            for c, v in zip(changed, vecs, strict=True):
                conn.execute(delete(t).where(t.c.chunk_id == c.chunk_id))
                conn.execute(
                    t.insert().values(
                        chunk_id=c.chunk_id,
                        persona=self.persona,
                        strategy=self.strategy,
                        doc_id=c.doc_id,
                        idx=c.index,
                        content_hash=c.content_hash,
                        text=c.text,
                        metadata=json.loads(json.dumps(c.doc.metadata)),
                        embedding=v.tolist(),
                    )
                )
        return {
            "upserted": len(changed),
            "deleted": len(stale),
            "unchanged": len(chunks) - len(changed),
        }

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        q = self.embedder.embed_query(query).tolist()
        t = self.table
        dist = t.c.embedding.cosine_distance(q)
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(t.c.chunk_id, (1 - dist).label("sim"))
                .where(t.c.persona == self.persona, t.c.strategy == self.strategy)
                .order_by(dist, t.c.chunk_id)
                .limit(k)
            ).all()
        return [(self._by_id[cid], float(sim)) for cid, sim in rows if cid in self._by_id]
