"""Portfolio corpus loader: every evidence item + past proposal of one persona as a Document."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Document:
    id: str
    persona: str
    type: str  # case_study | review | readme | code | cv | proposal
    title: str
    text: str
    source: str  # path inside the persona folder
    date: str | None = None
    outcome: str | None = None
    project_id: str | None = None
    client_industry: str | None = None
    skills: tuple[str, ...] = field(default_factory=tuple)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x]


@lru_cache(maxsize=16)
def load_corpus(persona: str, data_dir: str = str(DATA)) -> tuple[Document, ...]:
    root = Path(data_dir) / "personas" / persona
    docs = [
        Document(
            id=e["id"],
            persona=persona,
            type=e["type"],
            title=e["title"],
            text=e["text"],
            source=e["path"],
            date=e.get("date"),
            outcome=e.get("outcome"),
            project_id=e.get("project_id"),
            client_industry=e.get("client_industry"),
            skills=tuple(e.get("skills") or ()),
        )
        for e in _read_jsonl(root / "evidence.jsonl")
    ]
    docs += [
        Document(
            id=p["id"],
            persona=persona,
            type="proposal",
            title=p["job_title"],
            text=p["text"],
            source="proposals.jsonl",
            date=p.get("date"),
            outcome=p.get("outcome"),
            skills=tuple(p.get("skills") or ()),
        )
        for p in _read_jsonl(root / "proposals.jsonl")
    ]
    return tuple(docs)


def personas(data_dir: str = str(DATA)) -> list[str]:
    root = Path(data_dir) / "personas"
    return (
        sorted(p.name for p in root.iterdir() if (p / "evidence.jsonl").exists())
        if root.exists()
        else []
    )
