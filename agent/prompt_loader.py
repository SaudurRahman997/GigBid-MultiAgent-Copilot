"""Load versioned prompts from agent/prompts/<name>.v<N>.md (YAML front matter + body)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PROMPTS = Path(__file__).with_name("prompts")


@lru_cache(maxsize=64)
def load_prompt(name: str, version: int = 1) -> tuple[dict, str]:
    text = (PROMPTS / f"{name}.v{version}.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    return yaml.safe_load(head) or {}, body.strip()


def render(name: str, version: int = 1, **values: str) -> str:
    """Fill {placeholders} by plain replacement (prompt bodies may contain JSON braces)."""
    _, body = load_prompt(name, version)
    for k, v in values.items():
        body = body.replace("{" + k + "}", v)
    return body
