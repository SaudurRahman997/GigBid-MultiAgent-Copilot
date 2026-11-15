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
    from rag.variants import VARIANTS

    name = variant or configured_variant()
    if name not in VARIANTS:
        raise ValueError(f"unknown RAG variant {name!r}; available: {sorted(VARIANTS)}")
    return VARIANTS[name](load_corpus(persona, data_dir))
