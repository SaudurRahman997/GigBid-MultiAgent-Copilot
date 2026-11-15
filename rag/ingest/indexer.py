"""Incremental indexing into pgvector (deployment path).

    uv run python -m rag.ingest.indexer --persona ai_ml          # sync one persona
    uv run python -m rag.ingest.indexer --all                    # every persona in data/personas
    uv run python -m rag.ingest.indexer --persona ai_ml --upload path/to/new_case_study.md

Only new or changed chunks are embedded (chunk content hash); chunks of deleted documents are
removed. An upload is copied into the persona's portfolio folder and the persona re-synced.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from rag.chunking import chunk_documents
from rag.index import PgVectorIndex
from rag.ingest.loaders import ROOT, load_folder, load_persona
from rag.models import default_embedder
from rag.variants.base import rag_config

UPLOAD_DIRS = {
    ".md": "case_studies",
    ".pdf": "",
    ".py": "repos/uploads",
    ".ts": "repos/uploads",
    ".sql": "repos/uploads",
}


def database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("MCP_DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not url.startswith("postgresql"):
        raise SystemExit("set DATABASE_URL to the Postgres instance (pgvector)")
    return url


def sync_persona(persona: str, url: str, folder: Path | None = None) -> dict:
    cfg = rag_config()
    docs = load_folder(folder, persona) if folder else list(load_persona(persona))
    out = {}
    for strategy in ("structured", "fixed"):
        idx = PgVectorIndex(url, default_embedder(), persona, strategy)
        out[strategy] = idx.sync(chunk_documents(docs, strategy, cfg["chunking"]))
    return out


def add_upload(persona: str, file: Path) -> Path:
    sub = UPLOAD_DIRS.get(file.suffix.lower())
    if sub is None:
        raise SystemExit(f"unsupported upload type {file.suffix}")
    dest_dir = ROOT / "data" / "personas" / persona / sub
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.name
    shutil.copy2(file, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--upload", type=Path)
    args = ap.parse_args(argv)
    url = database_url()
    personas = (
        sorted(p.name for p in (ROOT / "data" / "personas").iterdir() if p.is_dir())
        if args.all
        else [args.persona]
    )
    if args.upload:
        print(f"added {add_upload(args.persona, args.upload).relative_to(ROOT)}")
        load_persona.cache_clear()
    for p in personas:
        print(p, sync_persona(p, url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
