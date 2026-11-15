"""Fail if gigsim/ changed without updating gigsim/FROZEN.sha256.

GigSim is frozen after Phase 2 (it plays the role of the "provided, do not modify" simulator).
A deliberate change must: update the hash (`--update`), and record why in docs/adr/.

Hash = sha256 over sorted "<relative path>\0<file bytes with LF endings>\0" for every file
under gigsim/ except FROZEN.sha256, caches and local databases.

Usage: uv run python scripts/check_gigsim_frozen.py [--update]
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIGSIM = ROOT / "gigsim"
FROZEN = GIGSIM / "FROZEN.sha256"
SKIP_PARTS = {"__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".db", ".db-wal", ".db-shm"}


def tree_hash(root: Path = GIGSIM) -> str:
    h = hashlib.sha256()
    files = sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and p != root / FROZEN.name
        and not SKIP_PARTS & set(p.parts)
        and p.suffix not in SKIP_SUFFIXES
    )
    for f in files:
        h.update(f.relative_to(root).as_posix().encode() + b"\0")
        h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def main(argv: list[str]) -> int:
    current = tree_hash()
    if "--update" in argv:
        FROZEN.write_text(current + "\n", encoding="utf-8", newline="\n")
        print(f"gigsim frozen hash updated: {current}")
        return 0
    recorded = FROZEN.read_text(encoding="utf-8").strip() if FROZEN.exists() else ""
    if current != recorded:
        print("gigsim/ changed but gigsim/FROZEN.sha256 was not updated.")
        print(f"  recorded {recorded or '(missing)'}\n  current  {current}")
        print("If the change is deliberate: run with --update and add an ADR in docs/adr/.")
        return 1
    print(f"gigsim frozen hash OK: {current[:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
