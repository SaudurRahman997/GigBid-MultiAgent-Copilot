"""Long-term memory on the LangGraph store (InMemoryStore in tests, PostgresStore deployed).

Namespaces per user:
  ("style_candidates", user)  edit patterns not yet promoted (with the threads they came from)
  ("style", user)             promoted style rules the Writer follows
  ("outcome", user)           promoted outcome facts per job category
Everything goes through agent/memory/promotion_rules.py. The UI memory viewer uses
list_memory / delete_memory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from agent.memory.promotion_rules import (
    OutcomeEvent,
    extract_patterns,
    merge_outcome,
    should_promote_style,
)

CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"
KINDS = ("style", "outcome", "style_candidates")


def _cfg() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["memory"]


def _key(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def record_edit(store, user: str, thread_id: str, old: str, new: str) -> list[str]:
    """Count edit patterns from one approved draft; promote those seen in enough threads.
    Returns the rules promoted by this edit."""
    if store is None:
        return []
    cfg = _cfg()
    promoted = []
    for p in extract_patterns(old, new, cfg["style_max_phrase_words"]):
        k = _key(p.key)
        item = store.get(("style_candidates", user), k)
        threads = set(item.value["threads"]) if item else set()
        threads.add(thread_id)
        store.put(
            ("style_candidates", user), k, {"pattern": p.model_dump(), "threads": sorted(threads)}
        )
        if (
            should_promote_style(threads, cfg["style_min_drafts"])
            and store.get(("style", user), k) is None
        ):
            store.put(
                ("style", user),
                k,
                {"rule": p.rule(), "pattern": p.model_dump(), "threads": sorted(threads)},
            )
            promoted.append(p.rule())
    return promoted


def style_rules(store, user: str) -> list[str]:
    if store is None:
        return []
    return [i.value["rule"] for i in store.search(("style", user), limit=50)]


def promote_outcome(store, user: str, event: OutcomeEvent) -> dict:
    """Only terminal marketplace events reach outcome memory (validated by OutcomeEvent)."""
    current = store.get(("outcome", user), event.category)
    agg = merge_outcome(current.value if current else None, event)
    store.put(("outcome", user), event.category, agg)
    return agg


def list_memory(store, user: str, kind: str) -> list[dict]:
    if kind not in KINDS:
        raise ValueError(f"unknown memory kind {kind!r}")
    return [{"key": i.key, **i.value} for i in store.search((kind, user), limit=200)]


def delete_memory(store, user: str, kind: str, key: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown memory kind {kind!r}")
    store.delete((kind, user), key)
