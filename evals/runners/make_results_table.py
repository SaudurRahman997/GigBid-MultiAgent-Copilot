"""Build evals/results/RESULTS.md (the B5 tables) ONLY from JSON files in evals/results/.

Nothing here computes or types a number; it formats what the runners wrote. Missing result files
are shown as "not run yet".
Usage: uv run python -m evals.runners.make_results_table
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals" / "results"
OUT = RES / "RESULTS.md"
ORDER = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v8_corrective"]


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def fmt(x, digits: int = 3) -> str:
    if x is None:
        return "-"
    return f"{x:.{digits}f}" if isinstance(x, float) else str(x)


def rag_section(split: str) -> list[str]:
    lines = [f"## B5 - retrieval variants ({split} set)", ""]
    rows = [(v, load(RES / "rag" / split / f"{v}.json")) for v in ORDER]
    rows = [(v, r) for v, r in rows if r]
    if not rows:
        return lines + ["_not run yet_", ""]
    lines += [
        "| Variant | Personas | Recall@5 | Project recall@5 | MRR | nDCG@10 | Refused (gold jobs) | Correct refusal (no-evidence jobs) | p95 latency ms | Source |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for v, r in rows:
        o = r["overall"]
        lines.append(
            f"| {v} | {', '.join(r['personas'])} | {fmt(o['recall@5'])} | {fmt(o.get('project_recall@5'))} | "
            f"{fmt(o['mrr'])} | {fmt(o['ndcg@10'])} | {fmt(o['refused_with_gold'])} | "
            f"{fmt(o['correct_refusal_rate'])} | {fmt(o['latency_ms_p95'], 0)} | `rag/{split}/{v}.json` |"
        )
    lines += [
        "",
        "Breakdown (Recall@5 / project recall@5):",
        "",
        "| Variant | names every skill | has synonym | has implied requirement | two anchor projects |",
        "|---|---|---|---|---|",
    ]
    for v, r in rows:
        b = r["overall"]["breakdowns"]

        def cell(k, b=b):
            return f"{fmt(b[k]['recall@5'])} / {fmt(b[k].get('project_recall@5'))} (n={b[k]['n']})"

        lines.append(
            f"| {v} | {cell('names_every_skill')} | {cell('has_synonym_requirement')} | "
            f"{cell('has_implied_requirement')} | {cell('two_anchor_projects')} |"
        )
    personas = sorted({p for _, r in rows for p in r["per_persona"]})
    lines += [
        "",
        "Per persona (Recall@5 / MRR):",
        "",
        "| Variant | " + " | ".join(personas) + " |",
        "|---|" + "---|" * len(personas),
    ]
    for v, r in rows:
        cells = [
            f"{fmt(r['per_persona'][p]['recall@5'])} / {fmt(r['per_persona'][p]['mrr'])}"
            if p in r["per_persona"]
            else "-"
            for p in personas
        ]
        lines.append(f"| {v} | " + " | ".join(cells) + " |")
    return lines + [""]


def ablation_section(split: str) -> list[str]:
    a = load(RES / "rag" / split / "ablation.json")
    lines = ["## Ablation (one component off at a time)", ""]
    if not a:
        return lines + ["_not run yet_", ""]
    full = a["overall"]["full"]
    lines += [
        f"Full pipeline: Recall@5 {fmt(full['recall@5'])}, MRR {fmt(full['mrr'])}, nDCG@10 {fmt(full['ndcg@10'])}.",
        "",
        "| Removed | dRecall@5 | dProject recall@5 | dMRR | dnDCG@10 |",
        "|---|---|---|---|---|",
    ]
    for name, d in a["delta_vs_full"].items():
        lines.append(
            f"| {name.removeprefix('no_')} | {d['recall@5']:+.3f} | {d['project_recall@5']:+.3f} | {d['mrr']:+.3f} | {d['ndcg@10']:+.3f} |"
        )
    return lines + ["", "Source: `rag/dev/ablation.json`", ""]


def verify_section() -> list[str]:
    v = load(RES / "verify" / "verify_eval.json")
    k = load(RES / "verify" / "judge_calibration.json")
    lines = ["## Claim verification (R5)", ""]
    if v:
        lines += [
            "| Judge | Accuracy | Macro-F1 | Unsupported-claim rate before | after repair |",
            "|---|---|---|---|---|",
        ]
        for name, j in v["judges"].items():
            lines.append(
                f"| {name} | {fmt(j['accuracy'])} | {fmt(j['macro_f1'])} | {fmt(j['unsupported_rate_before'])} | "
                f"{fmt(j['unsupported_rate_after'])} |"
            )
        lines += [
            "",
            f"{v['claims']} claims with labels by construction. Source: `verify/verify_eval.json`",
            "",
        ]
    else:
        lines += ["_verify_eval not run yet_", ""]
    if k:
        for name, j in k["judges"].items():
            lines.append(
                f"- Judge `{name}` vs human labels ({k['claims_labelled']} claims, {k['proposals']} proposals): "
                f"Cohen's kappa **{fmt(j['kappa_3class'])}** (unsupported-vs-rest {fmt(j['kappa_unsupported_vs_rest'])})."
            )
        lines += ["", "Source: `verify/judge_calibration.json`", ""]
    else:
        lines += [
            "- Judge calibration: _waiting for the 30 human-labelled proposals_ (`evals/labels/claims_to_label.csv`).",
            "",
        ]
    return lines


def decision_section() -> list[str]:
    lines = ["## Decisions", ""]
    files = sorted((RES / "decision").glob("*.json")) if (RES / "decision").exists() else []
    if not files:
        return lines + ["_not run yet_", ""]
    lines += [
        "| Decider | bid/skip macro-F1 | accuracy | scam precision | scam recall | price in band | Source |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in files:
        o = load(f)["overall"]
        lines.append(
            f"| {f.stem} | {fmt(o['bid_skip_macro_f1'])} | {fmt(o['accuracy'])} | {fmt(o['scam_precision'])} | "
            f"{fmt(o['scam_recall'])} | {fmt(o['price_in_band'])} | `decision/{f.name}` |"
        )
    return lines + [""]


def gigsim_section() -> list[str]:
    g = load(RES / "gigsim" / "outcomes.json")
    lines = ["## GigSim outcomes on a fixed job set", ""]
    if not g:
        return lines + ["_not run yet_", ""]
    lines += [
        f"{g['jobs_per_persona']} bid-worthy dev jobs per persona; writer: {g['writer']}.",
        "",
        "| Proposal source | Reply rate | Interview rate | Hire rate | Must-have coverage |",
        "|---|---|---|---|---|",
    ]
    for name, o in g["overall"].items():
        lines.append(
            f"| {name} | {fmt(o['reply_rate'])} | {fmt(o['interview_rate'])} | {fmt(o['hire_rate'])} | {fmt(o['mean_must_have_coverage'], 2)} |"
        )
    return lines + ["", "Source: `gigsim/outcomes.json`", ""]


def main() -> int:
    parts = [
        "# GigBid results",
        "",
        "> Generated by `evals/runners/make_results_table.py` from `evals/results/*.json`. "
        "Do not edit by hand.",
        "",
    ]
    parts += (
        rag_section("dev")
        + ablation_section("dev")
        + verify_section()
        + decision_section()
        + gigsim_section()
    )
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
