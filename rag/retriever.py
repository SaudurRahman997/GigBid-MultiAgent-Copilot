"""Retriever interface used by the Portfolio MCP server. The variant comes from config.

    get_retriever(persona) -> Retriever  (variant = agent/config.yaml rag.variant)
    retriever.search(requirement, k, filters) -> list[Hit]

Variants live in rag/variants/ and register themselves in VARIANTS. Phase 4 adds V0-V8 and the
deployed choice is made by evals/runners/rag_eval.py, never by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, Field

from rag.corpus import DATA, Document, load_corpus

CONFIG = Path(__file__).resolve().parents[1] / "agent" / "config.yaml"
EvidenceType = Literal["case_study", "review", "readme", "code", "cv", "proposal"]


class EvidenceFilters(BaseModel):
    types: list[EvidenceType] | None = Field(None, description="Only these evidence types")
    outcomes: list[str] | None = Field(
        None, description="e.g. won, replied (proposals) - substring match"
    )
    date_from: str | None = Field(None, description="ISO date; only evidence on/after it")
    skills: list[str] | None = Field(None, description="Keep items tagged with any of these skills")


@dataclass(frozen=True)
class Hit:
    doc: Document
    score: float
    snippet: str


class Retriever(Protocol):
    variant: str

    def search(
        self, requirement: str, k: int = 5, filters: EvidenceFilters | None = None
    ) -> list[Hit]: ...


def passes(doc: Document, f: EvidenceFilters | None) -> bool:
    if f is None:
        return True
    if f.types and doc.type not in f.types:
        return False
    if f.outcomes and not any(o.lower() in (doc.outcome or "").lower() for o in f.outcomes):
        return False
    if f.date_from and (doc.date or "") < f.date_from:
        return False
    return not (f.skills and not set(s.lower() for s in f.skills) & set(doc.skills))


def configured_variant(path: Path = CONFIG) -> str:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["rag"]["variant"]


@lru_cache(maxsize=32)
def get_retriever(persona: str, variant: str | None = None, data_dir: str = str(DATA)) -> Retriever:
    from rag.variants import CONTEXT_VARIANTS, VARIANTS
    from rag.variants.base import default_context

    name = variant or configured_variant()
    if name not in VARIANTS:
        raise ValueError(f"unknown RAG variant {name!r}; available: {sorted(VARIANTS)}")
    if name in CONTEXT_VARIANTS:
        return CONTEXT_VARIANTS[name](default_context(persona))
    return VARIANTS[name](load_corpus(persona, data_dir))


def retriever_for(
    persona: str, tenant: str | None = None, variant: str | None = None, data_dir: str = str(DATA)
) -> Retriever:
    """The configured retriever over the persona's portfolio plus this user's uploads."""
    from rag import uploads

    prints = uploads.fingerprint(persona, tenant)
    if not prints:
        return get_retriever(persona, variant, data_dir)
    root = str(uploads.upload_root())
    return _with_uploads(persona, tenant, variant, data_dir, root, prints)


@lru_cache(maxsize=64)
def _with_uploads(
    persona: str,
    tenant: str,
    variant: str | None,
    data_dir: str,
    root: str,
    prints: tuple[str, ...],  # part of the cache key: a changed upload set builds a new index
) -> Retriever:
    from rag import uploads
    from rag.variants import CONTEXT_VARIANTS, VARIANTS

    name = variant or configured_variant()
    if name not in VARIANTS:
        raise ValueError(f"unknown RAG variant {name!r}; available: {sorted(VARIANTS)}")
    if name in CONTEXT_VARIANTS:
        from rag.ingest.loaders import Document as LoadedDocument
        from rag.variants.base import build_context, default_context

        base = default_context(persona)
        docs = (*base.docs, *uploads.documents(persona, tenant, LoadedDocument))
        return CONTEXT_VARIANTS[name](
            build_context(persona, base.embedder, base.reranker, base.cfg, docs=docs)
        )
    added = uploads.documents(persona, tenant, Document)
    return VARIANTS[name]((*load_corpus(persona, data_dir), *added))
