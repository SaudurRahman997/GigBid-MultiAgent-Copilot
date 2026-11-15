"""Validate generated data: provenance on every record, dev-set completeness, planted rates.

Checks
  1. every JSON/JSONL record under data/synthetic, data/personas, data/devset (and data/heldout
     if present) has `synthetic` (bool) and a non-empty `provenance`; markdown files carry them
     in front matter or an HTML comment; code files in a header comment
  2. real (Kaggle) records have synthetic=false, provenance "kaggle:<dataset>" and a licence
  3. dev set: ~200 jobs per persona, every gold field present, gold evidence ids exist in the
     persona's evidence index, 2-5 gold items for anchored jobs
  4. job stream: planted scam / injection / duplicate shares within tolerance of the targets
Exit code 1 on any failure.

Usage: uv run python -m data.generators.validate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from data.generators.common import (
    DEVSET,
    HELDOUT,
    PERSONAS,
    SYNTHETIC,
    parse_front_matter,
    read_jsonl,
)

GOLD_FIELDS = ["persona", "job_type", "bid", "skip_reason", "is_scam", "has_injection",
               "evidence_ids", "related_evidence_ids", "price_band", "client_quality",
               "risk_flags", "anchor_project_ids"]  # fmt: skip
STREAM_TARGETS = {"scam": 0.08, "injection": 0.03, "duplicate": 0.05}
TOLERANCE = 0.01
DEV_MIN, DEV_MAX = 180, 220
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".sql", ".php"}
SKIP_FILES = {"MANIFEST.json", "summary.json"}


def _check_record(rec: dict, where: str, errors: list[str]) -> None:
    if not isinstance(rec.get("synthetic"), bool) or not rec.get("provenance"):
        errors.append(f"{where}: missing synthetic/provenance")
        return
    if rec["synthetic"] is False and (
        not str(rec["provenance"]).startswith("kaggle:") or not rec.get("licence")
    ):
        errors.append(f"{where}: real record without kaggle provenance + licence")


def check_files(roots: list[Path], errors: list[str]) -> int:
    n = 0
    for root in roots:
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.name in SKIP_FILES or f.name.startswith("."):
                continue
            rel = f.as_posix()
            if f.suffix == ".jsonl":
                for i, rec in enumerate(read_jsonl(f), start=1):
                    _check_record(rec, f"{rel}:{i}", errors)
                    n += 1
            elif f.suffix == ".json":
                obj = json.loads(f.read_text(encoding="utf-8"))
                for i, rec in enumerate(obj if isinstance(obj, list) else [obj], start=1):
                    _check_record(rec, f"{rel}:{i}", errors)
                    n += 1
            elif f.suffix == ".md":
                text = f.read_text(encoding="utf-8")
                meta, _ = parse_front_matter(text)
                ok = (meta.get("synthetic") is True and meta.get("provenance")) or (
                    "synthetic: true; provenance:" in text
                )
                if not ok:
                    errors.append(f"{rel}: markdown without synthetic/provenance")
                n += 1
            elif f.suffix in CODE_SUFFIXES:
                if "SYNTHETIC" not in f.read_text(encoding="utf-8").split("\n", 1)[0]:
                    errors.append(f"{rel}: code file without SYNTHETIC header")
                n += 1
    return n


def check_devset(errors: list[str], root: Path = DEVSET, personas: Path = PERSONAS) -> dict:
    out = {}
    for f in sorted(root.glob("*.jsonl")):
        pid = f.stem
        jobs = read_jsonl(f)
        evidence = {e["id"] for e in read_jsonl(personas / pid / "evidence.jsonl")}
        if not DEV_MIN <= len(jobs) <= DEV_MAX:
            errors.append(f"devset {pid}: {len(jobs)} jobs (want ~200)")
        for j in jobs:
            g = j.get("_gold", {})
            missing = [k for k in GOLD_FIELDS if k not in g]
            if missing:
                errors.append(f"devset {pid} {j.get('job_id')}: missing gold {missing}")
                continue
            unknown = set(g["evidence_ids"]) - evidence
            if unknown:
                errors.append(f"devset {pid} {j['job_id']}: unknown evidence {sorted(unknown)}")
            if g["anchor_project_ids"] and not 2 <= len(g["evidence_ids"]) <= 5:
                errors.append(f"devset {pid} {j['job_id']}: {len(g['evidence_ids'])} gold items")
        out[pid] = len(jobs)
    if not out:
        errors.append("devset: no files")
    return out


def check_stream(errors: list[str], path: Path = SYNTHETIC / "jobs_stream.jsonl") -> dict:
    jobs = read_jsonl(path)
    kinds = [j["_gold"]["kind"] for j in jobs]
    shares = {k: round(kinds.count(k) / len(jobs), 4) for k in STREAM_TARGETS}
    for k, target in STREAM_TARGETS.items():
        if abs(shares[k] - target) > TOLERANCE:
            errors.append(f"stream: {k} share {shares[k]} vs target {target}")
    return {"jobs": len(jobs), **shares}


def main() -> int:
    errors: list[str] = []
    n = check_files([SYNTHETIC, PERSONAS, DEVSET, HELDOUT], errors)
    dev = check_devset(errors)
    stream = check_stream(errors)
    for e in errors[:50]:
        print("FAIL", e)
    print(
        f"validate: {n} records/files checked; devset {dev}; stream {stream}; {len(errors)} error(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
