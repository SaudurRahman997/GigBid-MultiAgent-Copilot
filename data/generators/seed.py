"""Run every generator in order, write summary + manifests, then validate.

`make seed` = preprocess (when raw Kaggle data is present) + this module.
Same code + same SEED -> byte-identical outputs (compare the MANIFEST.json files between runs).
"""

from __future__ import annotations

import sys

from data.generators import clients, conversations, devset, jobs, personas, proposals, validate
from data.generators.common import (
    DEVSET,
    PERSONAS,
    SYNTHETIC,
    read_jsonl,
    write_json,
    write_manifest,
)


def _count(items: list, key) -> dict:
    values = [key(x) for x in items]
    return {v: values.count(v) for v in sorted(set(values), key=str)}


def summary() -> dict:
    stream = read_jsonl(SYNTHETIC / "jobs_stream.jsonl")
    out: dict = {
        "stream": {**_count(stream, lambda j: j["_gold"]["kind"]), "total": len(stream)},
        "clients": _count(
            read_jsonl(SYNTHETIC / "clients.jsonl"), lambda c: c["_gold"]["history_quality"]
        ),
        "conversations": len(read_jsonl(SYNTHETIC / "conversations.jsonl")),
        "personas": {},
    }
    for p in sorted(d.name for d in PERSONAS.iterdir() if d.is_dir()):
        dev = read_jsonl(DEVSET / f"{p}.jsonl")
        out["personas"][p] = {
            "evidence_by_type": _count(read_jsonl(PERSONAS / p / "evidence.jsonl"), lambda e: e["type"]),
            "proposals_by_outcome": _count(read_jsonl(PERSONAS / p / "proposals.jsonl"), lambda x: x["outcome"]),
            "dev_jobs": len(dev),
            "dev_by_job_type": _count(dev, lambda j: j["_gold"]["job_type"]),
            "dev_with_injection": sum(j["_gold"]["has_injection"] for j in dev),
        }  # fmt: skip
    return out


def main() -> int:
    for name, step in [("personas", personas.main), ("clients", clients.main), ("jobs", jobs.main),
                       ("proposals", proposals.main), ("conversations", conversations.main),
                       ("devset", devset.main)]:  # fmt: skip
        print(f"[{name}]", flush=True)
        step()
    write_json(SYNTHETIC / "summary.json", summary())
    for root in (SYNTHETIC, PERSONAS, DEVSET):
        write_manifest(root)
    return validate.main()


if __name__ == "__main__":
    sys.exit(main())
