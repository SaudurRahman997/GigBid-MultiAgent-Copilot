"""Explicit promotion rules for long-term memory (R7). Nothing enters long-term memory except
through these functions.

Style memory  (namespace ("style", user)):
  An edit the human makes to an approved draft is reduced to word-level patterns
  (remove "X" / add "Y" / replace "X" -> "Y"). A pattern is a CANDIDATE until the same pattern
  has appeared in >= memory.style_min_drafts approved drafts from DIFFERENT threads; only then is
  it promoted to a style rule the Writer follows.

Outcome memory (namespace ("outcome", user)):
  Promoted ONLY from a terminal marketplace outcome event (replied / interview / hired / lost)
  whose source is the marketplace events feed - never from raw tool output, a draft, or a model's
  opinion. Facts are aggregated per job category ("what won per category").
"""

from __future__ import annotations

import difflib
import re
from typing import Literal

from pydantic import BaseModel, field_validator

WORD = re.compile(r"[A-Za-z0-9'$%.,!?-]+")


class EditPattern(BaseModel):
    op: Literal["remove", "add", "replace"]
    old: str = ""
    new: str = ""

    @property
    def key(self) -> str:
        return f"{self.op}|{self.old}|{self.new}"

    def rule(self) -> str:
        if self.op == "remove":
            return f'Avoid the phrase "{self.old}".'
        if self.op == "add":
            return f'Include "{self.new}" where it fits.'
        return f'Write "{self.new}" instead of "{self.old}".'


def _norm(words: list[str]) -> str:
    return " ".join(w.strip(".,!?").lower() for w in words).strip()


def extract_patterns(old: str, new: str, max_words: int = 8) -> list[EditPattern]:
    """Word-level diff -> edit patterns worth remembering (short, non-trivial phrases)."""
    a, b = WORD.findall(old), WORD.findall(new)
    out: list[EditPattern] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        old_p, new_p = _norm(a[i1:i2]), _norm(b[j1:j2])
        if tag == "delete" and 1 <= i2 - i1 <= max_words and len(old_p) >= 4:
            out.append(EditPattern(op="remove", old=old_p))
        elif tag == "insert" and 1 <= j2 - j1 <= max_words and len(new_p) >= 4:
            out.append(EditPattern(op="add", new=new_p))
        elif tag == "replace" and i2 - i1 <= max_words and j2 - j1 <= max_words and old_p != new_p:
            out.append(EditPattern(op="replace", old=old_p, new=new_p))
    return out


def should_promote_style(threads: set[str], min_drafts: int) -> bool:
    """A pattern is promoted once it was seen in at least `min_drafts` distinct threads."""
    return len(threads) >= min_drafts


class OutcomeEvent(BaseModel):
    """A terminal outcome from the marketplace events feed (the only source outcome memory accepts)."""

    source: Literal["marketplace_events"]
    type: str
    proposal_id: str
    category: str
    features: dict = {}

    @field_validator("type")
    @classmethod
    def terminal(cls, v: str) -> str:
        if v not in {"replied", "interview", "hired", "lost"}:
            raise ValueError(f"not a terminal outcome event: {v!r}")
        return v


def merge_outcome(current: dict | None, event: OutcomeEvent) -> dict:
    """Aggregate per category: counts by outcome, reply rate, recent example proposal ids."""
    agg = dict(current or {"category": event.category, "replied": 0, "interview": 0, "hired": 0, "lost": 0,
                           "examples": []})  # fmt: skip
    agg[event.type] = agg.get(event.type, 0) + 1
    if event.type in {"replied", "interview", "hired"} and event.proposal_id not in agg["examples"]:
        agg["examples"] = (agg["examples"] + [event.proposal_id])[-10:]
    total = agg["replied"] + agg["interview"] + agg["hired"] + agg["lost"]
    agg["positive_rate"] = round((agg["replied"] + agg["interview"] + agg["hired"]) / total, 4) if total else 0.0
    return agg
