"""Assemble the GigBid API as a Vercel Python (FastAPI) project in var/vercel-api/.

The function runs the API in single-process demo mode (see docs/DEPLOY.md):
  GIGBID_MCP_MODE=inprocess   tools served in-process from the synthetic data (same names/shapes as MCP)
  GIGBID_INLINE_RUNS=1        start/approve drive the graph to its next stop inside the request
  GIGBID_AGENT_MODE=rules     deterministic nodes (no model keys needed)
  API_DATABASE_URL            sqlite in /tmp unless a Postgres URL is set in the Vercel project

Only the packages the API imports are installed, pinned to the versions in uv.lock; pandas reads the
one small parquet file with fastparquet instead of pyarrow to stay under the function size limit.

Usage:  uv run python -m scripts.build_vercel_api  &&  cd var/vercel-api && npx vercel deploy --prod
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "var" / "vercel-api"

PACKAGES = ("agent", "rag", "mcp_servers", "apps/api")
FILES = ("apps/__init__.py", "evals/__init__.py", "evals/inprocess_mcp.py", "evals/metrics.py", ".python-version")
DATA = ("data/devset", "data/personas", "data/policy_pack", "data/synthetic", "evals/results/decision")
DATA_FILES = ("data/processed/pricing_stats.parquet", "data/processed/skill_taxonomy.json")
REQUIREMENTS = ("fastapi", "langgraph", "langgraph-checkpoint-postgres", "psycopg", "psycopg-binary", "langchain-mcp-adapters", "mcp",
                "pandas", "numpy", "rank-bm25", "pypdf", "sqlalchemy", "sse-starlette", "pyjwt", "cryptography",
                "pyyaml", "pydantic-settings", "httpx", "python-multipart", "fpdf2")  # fmt: skip
EXTRA = ("fastparquet==2024.11.0",)  # replaces pyarrow (parquet engine only)

ENTRY = '''"""Vercel entrypoint: the GigBid API in single-process demo mode (built by scripts/build_vercel_api.py)."""

import os

for key, value in {"GIGBID_MCP_MODE": "inprocess", "GIGBID_INLINE_RUNS": "1", "GIGBID_AGENT_MODE": "rules",
                   "API_DATABASE_URL": "sqlite:////tmp/gigbid-api.db"}.items():
    os.environ.setdefault(key, value)

from apps.api.main import app  # noqa: E402

__all__ = ["app"]
'''


def pins() -> list[str]:
    out = subprocess.run(["uv", "export", "--no-dev", "--no-hashes", "--no-emit-project", "--format", "requirements-txt"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout  # fmt: skip
    found = {}
    for line in out.splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]+\])?==([^\s;]+)", line)
        if m:
            found[m.group(1).lower()] = f"{m.group(1)}{m.group(2) or ''}=={m.group(3)}"
    missing = [r for r in REQUIREMENTS if r not in found]
    if missing:
        raise SystemExit(f"not in uv.lock: {missing}")
    return [found[r] for r in REQUIREMENTS] + list(EXTRA)


def build() -> Path:
    if OUT.exists():
        for child in OUT.iterdir():  # keep .vercel/ (the project link)
            if child.name not in (".vercel", ".env.local"):
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "Dockerfile*", "openapi.json")
    for d in PACKAGES + DATA:
        shutil.copytree(ROOT / d, OUT / d, ignore=ignore, dirs_exist_ok=True)
    for f in FILES + DATA_FILES:
        (OUT / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, OUT / f)
    (OUT / "app.py").write_text(ENTRY, encoding="utf-8")
    (OUT / "requirements.txt").write_text("\n".join(pins()) + "\n", encoding="utf-8")
    (OUT / ".vercelignore").write_text("__pycache__\n*.pyc\n.env*\n", encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(f"built {build()}")
