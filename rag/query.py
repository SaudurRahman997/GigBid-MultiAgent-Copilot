"""Retrieval queries. A job becomes one whole-post query (V0) or several requirement queries (V1+).

In the agent, requirements come from the Job Analyst's JobSpec. For offline evaluation they are
extracted deterministically from the job text so every variant sees exactly the same inputs:
  * the opening "need" sentence,
  * each requirement bullet, cleaned of filler ("Strong ... skills", "(must have)"),
  * vague bullets ("You have shipped something like this before") are replaced by
    "experience delivering: <need>" - the resolution an LLM Job Analyst would make,
  * short requirements (<= 4 words) get the job title as context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MUST = re.compile(r"\s*\((must have)\)\s*$", re.I)
FILLER = re.compile(r"^(strong|proven|experience with|nice to have:?)\s+", re.I)
VAGUE = re.compile(r"something like this|tell us about it|similar (project|work) before", re.I)
MAX_SUBQUERIES = 8


@dataclass(frozen=True)
class RetrievalQuery:
    text: str  # the whole post (or the single requirement)
    requirements: tuple[str, ...] = field(default_factory=tuple)
    title: str = ""

    @classmethod
    def single(cls, requirement: str) -> RetrievalQuery:
        return cls(text=requirement, requirements=(requirement,))

    def sub_queries(self) -> list[str]:
        return list(self.requirements) or [self.text]


def clean_requirement(line: str) -> str:
    line = MUST.sub("", line.strip("-• ").strip())
    line = FILLER.sub("", line)
    return re.sub(r"\s+skills?$", "", line).strip()


def from_job(title: str, description: str, skills: list[str] | None = None) -> RetrievalQuery:
    lines = description.split("\n")
    first = next((ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith(("-", "•"))), "")
    need = re.split(r"(?<=[.!?])\s+", first)[0] if first else title
    bullets = [clean_requirement(b) for b in lines if b.strip().startswith(("-", "•"))]
    reqs: list[str] = []
    for q in [need, *bullets, *(skills or [])]:
        if not q or len(q) < 3:
            continue
        if VAGUE.search(q):
            q = f"experience delivering: {need}"
        elif len(q.split()) <= 4:
            q = f"{q} ({title})"
        if q.lower() not in {r.lower() for r in reqs}:
            reqs.append(q)
    return RetrievalQuery(
        text=f"{title}\n\n{description}", requirements=tuple(reqs[:MAX_SUBQUERIES]), title=title
    )
