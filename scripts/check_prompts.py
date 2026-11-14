"""Fail if prompt-like text is hard-coded in Python instead of agent/prompts/*.md.

Heuristic (AST based, so comments are ignored): a string literal is flagged when it
is long and reads like an instruction to a model. Docstrings are skipped.
Silence a deliberate exception with a trailing `# prompt-ok` comment on the line.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["agent", "mcp_servers", "rag", "gigsim", "apps/api", "evals", "data/generators"]
MIN_LEN = 120
PROMPT_MARKERS = re.compile(
    r"\b(you are (an?|the)\b|your task is|respond (only )?(with|in) json|"
    r"as an ai|system prompt|ignore (all )?previous instructions|step by step)",
    re.IGNORECASE,
)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def scan_file(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [f"{path}: cannot parse ({exc})"]
    lines = src.splitlines()
    skip = _docstring_nodes(tree)
    problems = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip or len(node.value) < MIN_LEN:
            continue
        if not PROMPT_MARKERS.search(node.value):
            continue
        if "# prompt-ok" in lines[node.lineno - 1]:
            continue
        rel = path.relative_to(ROOT).as_posix()
        problems.append(f"{rel}:{node.lineno}: prompt-like string; move it to agent/prompts/")
    return problems


def main(argv: list[str] | None = None) -> int:
    targets = [Path(a) for a in (argv or [])] or [ROOT / d for d in SCAN_DIRS]
    files = []
    for t in targets:
        files.extend([t] if t.is_file() else sorted(t.rglob("*.py")) if t.exists() else [])
    problems = [p for f in files for p in scan_file(f)]
    for p in problems:
        print(p)
    print(f"check_prompts: scanned {len(files)} files, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
