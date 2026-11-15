"""Judge calibration: Cohen's kappa between the claim judge and YOUR labels on 30 proposals.

Step 1 (once):  uv run python -m evals.runners.judge_calibration --make-sheet
                -> evals/labels/claims_to_label.csv (30 proposals, 3 claims each, with the
                   portfolio evidence needed to decide). Fill the `human_label` column with
                   supported | partial | unsupported. This is the student's job, not the AI's.
Step 2:         uv run python -m evals.runners.judge_calibration
                -> evals/results/verify/judge_calibration.json: kappa (3-class and binary
                   unsupported-vs-rest), confusion matrix, per judge.
The labels by construction are kept in a separate file and only used to report how often the
human agreed with the construction (a sanity check), never shown in the sheet.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

from evals.metrics import cohen_kappa
from evals.runners.verify_eval import LABELS, build_claims, confusion
from rag.variants import CONTEXT_VARIANTS
from rag.variants.base import default_context
from rag.verify import config, default_judge, gather_evidence

ROOT = Path(__file__).resolve().parents[2]
LABEL_DIR = ROOT / "evals" / "labels"
SHEET = LABEL_DIR / "claims_to_label.csv"
CONSTRUCTION = LABEL_DIR / "claims_construction_labels.json"
OUT = ROOT / "evals" / "results" / "verify" / "judge_calibration.json"
SEED = 7
N_PROPOSALS, CLAIMS_PER_PROPOSAL = 30, 3


def make_sheet() -> None:
    r = random.Random(SEED)
    personas = ["ai_ml", "fullstack", "data_analyst"]
    drafts = [d for p in personas for d in build_claims(p, N_PROPOSALS // len(personas), r)]
    cfg = config()
    rows, construction = [], {}
    for i, d in enumerate(drafts, start=1):
        retriever = CONTEXT_VARIANTS[cfg["retrieval_variant"]](default_context(d["persona"]))
        for j, c in enumerate(r.sample(d["claims"], CLAIMS_PER_PROPOSAL), start=1):
            item = f"P{i:02d}-C{j}"
            ev = gather_evidence(c["text"], [], retriever, 3)
            rows.append(
                {
                    "item": item,
                    "persona": d["persona"],
                    "claim": c["text"],
                    "evidence": " || ".join(f"{eid}: {txt[:350]}" for eid, txt in ev),
                    "human_label": "",
                }
            )
            construction[item] = c["label"]
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item", "persona", "claim", "evidence", "human_label"])
        w.writeheader()
        w.writerows(rows)
    CONSTRUCTION.write_text(
        json.dumps(construction, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"wrote {SHEET.relative_to(ROOT)} ({len(rows)} claims from {len(drafts)} proposals). "
        "Fill human_label with supported | partial | unsupported."
    )


def calibrate(judges: list[str]) -> int:
    rows = list(csv.DictReader(SHEET.open(encoding="utf-8")))
    labelled = [r for r in rows if r["human_label"].strip().lower() in LABELS]
    if len(labelled) < len(rows):
        print(
            f"{len(rows) - len(labelled)} of {len(rows)} claims have no valid human_label yet "
            "(supported | partial | unsupported). Label them first."
        )
        if not labelled:
            return 1
    human = [r["human_label"].strip().lower() for r in labelled]
    construction = (
        json.loads(CONSTRUCTION.read_text(encoding="utf-8")) if CONSTRUCTION.exists() else {}
    )
    cfg = config()
    out = {
        "runner": "evals/runners/judge_calibration.py",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "claims_labelled": len(labelled),
        "proposals": len({r["item"].split("-")[0] for r in labelled}),
        "human_vs_construction_agreement": round(
            sum(construction.get(r["item"]) == h for r, h in zip(labelled, human, strict=True))
            / len(human),
            4,
        )
        if construction
        else None,
        "judges": {},
    }
    for name in judges:
        judge = default_judge(name)
        preds = []
        for r in labelled:
            retriever = CONTEXT_VARIANTS[cfg["retrieval_variant"]](default_context(r["persona"]))
            preds.append(
                judge.judge(r["claim"], gather_evidence(r["claim"], [], retriever, cfg["k"])).status
            )
        binary_h = ["unsupported" if h == "unsupported" else "ok" for h in human]
        binary_p = ["unsupported" if p == "unsupported" else "ok" for p in preds]
        out["judges"][name] = {
            "kappa_3class": round(cohen_kappa(human, preds), 4),
            "kappa_unsupported_vs_rest": round(cohen_kappa(binary_h, binary_p), 4),
            "accuracy": round(
                sum(h == p for h, p in zip(human, preds, strict=True)) / len(human), 4
            ),
            "confusion_human_rows": confusion(list(zip(human, preds, strict=True))),
        }
        print(
            f"{name}: kappa={out['judges'][name]['kappa_3class']:.3f} "
            f"(binary {out['judges'][name]['kappa_unsupported_vs_rest']:.3f})"
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-sheet", action="store_true")
    ap.add_argument("--judges", nargs="+", default=["rerank"])
    args = ap.parse_args(argv)
    if args.make_sheet:
        make_sheet()
        return 0
    if not SHEET.exists():
        print("no label sheet yet: run with --make-sheet, then fill human_label")
        return 1
    return calibrate(args.judges)


if __name__ == "__main__":
    sys.exit(main())
