"""Needs `make up`: pgvector index is incremental and ranks like the in-memory index."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag.chunking import chunk_documents
from rag.index import MemoryDenseIndex, PgVectorIndex
from rag.ingest.loaders import load_persona
from rag.models import HashEmbedder
from rag.variants.base import rag_config

pytestmark = pytest.mark.integration


def db_url() -> str:
    env = dict(
        line.split("=", 1)
        for line in Path(".env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )
    user, pw, db = (
        env.get("POSTGRES_USER", "gigbid"),
        env.get("POSTGRES_PASSWORD", "gigbid"),
        env.get("POSTGRES_DB", "gigbid"),
    )
    return f"postgresql+psycopg://{user}:{pw}@localhost:5432/{db}"


def test_incremental_sync_and_parity():
    emb = HashEmbedder(dim=64)
    chunks = chunk_documents(load_persona("data_analyst"), "structured", rag_config()["chunking"])
    idx = PgVectorIndex(db_url(), emb, "it_test_persona", "structured")
    idx.sync([])  # clean slate for this test persona
    first = idx.sync(chunks)
    assert first["upserted"] == len(chunks) and first["deleted"] == 0
    again = idx.sync(chunks)
    assert again == {"upserted": 0, "deleted": 0, "unchanged": len(chunks)}
    fewer = idx.sync(chunks[:-3])
    assert fewer["deleted"] == 3 and fewer["upserted"] == 0
    mem = MemoryDenseIndex(chunks[:-3], emb)
    q = "Power BI sales dashboard filtered by region"
    pg_ids = [c.chunk_id for c, _ in idx.search(q, 5)]
    mem_ids = [c.chunk_id for c, _ in mem.search(q, 5)]
    assert pg_ids[:3] == mem_ids[:3]
    idx.sync([])
