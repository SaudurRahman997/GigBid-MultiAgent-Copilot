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
    full = a["overall"][a.get("base", "full")]
    lines += [
        f"Best pipeline ({a.get('base')}): Recall@5 {fmt(full['recall@5'])}, MRR {fmt(full['mrr'])}, nDCG@10 {fmt(full['ndcg@10'])}.",
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


def multiagent_section() -> list[str]:
    d = load(RES / "multiagent" / "summary.json")
    if not d:
        return []
    lines = [
        "## R&D C - single agent vs supervisor vs graph (50 dev jobs)",
        "",
        "| System | Model | bid/skip macro-F1 | Scam P / R | Price in band | Letters | Reply rate | Tokens/job | Latency mean / p95 s | Parse errors |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in d["systems"].items():
        m = s["decisions"]
        lines.append(
            f"| {name} | {s['model']} | {fmt(m['bid_skip_macro_f1'])} | {fmt(m['scam_precision'], 2)} / {fmt(m['scam_recall'], 2)} | "
            f"{fmt(m['price_in_band'])} | {s['letters']} | {fmt(s['reply_rate'])} | {s['tokens_per_job']} | "
            f"{s['latency_mean_s']} / {s['latency_p95_s']} | {s['parse_errors']} |"
        )
    return lines + ["", "Source: `multiagent/*.json`", ""]


def tools_section() -> list[str]:
    d = load(RES / "tools" / "granularity.json")
    if not d:
        return []
    lines = [
        f"## R&D A - tool granularity ({d['tasks']} tasks, {d['model']})",
        "",
        "| Tool set | Tools | Tool selection | Argument accuracy | Args given right tool | No tool call | Tokens/task |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in d["toolsets"].items():
        lines.append(
            f"| {name} | {d['tools_per_set'][name]} | {fmt(s['tool_selection_accuracy'])} | {fmt(s['argument_accuracy'])} | "
            f"{fmt(s['argument_accuracy_given_right_tool'])} | {s['no_tool_call']} | {s['tokens_per_task']} |"
        )
    return lines + ["", "Source: `tools/granularity.json`", ""]


def models_section() -> list[str]:
    d = load(RES / "models" / "summary.json")
    if not d:
        return []
    lines = [
        f"## Model comparison (bid graph, {d['jobs']} dev jobs; hardware: {d['hardware']})",
        "",
        "| Model | bid/skip macro-F1 | Price in band | Reply rate | Tokens/job | Tokens/s | Latency mean / p95 s | USD/job |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, s in d["models"].items():
        m = s["decisions"]
        lines.append(
            f"| {name} | {fmt(m['bid_skip_macro_f1'])} | {fmt(m['price_in_band'])} | {fmt(s['reply_rate'])} | {s['tokens_per_job']} | "
            f"{s['tokens_per_s']} | {s['latency_mean_s']} / {s['latency_p95_s']} | {d['usd_per_job']} |"
        )
    return lines + ["", "Source: `models/summary.json`", ""]


def injection_section() -> list[str]:
    d = load(RES / "injection" / "asr.json")
    if not d:
        return []
    a = d["asr"]
    lines = [
        f"## Injection attack success rate ({d['injected_jobs']} planted-injection dev jobs, {d['model']})",
        "",
        "| Defences | ASR |",
        "|---|---|",
        f"| none | {fmt(a['none'])} |",
        f"| untrusted delimiters + writer rules | {fmt(a['prompt'])} |",
        f"| + compliance output filter (full) | {fmt(a['full'])} |",
        "",
        "| Attack | Jobs | none | prompt | full |",
        "|---|---|---|---|---|",
    ]
    for name, b in d["by_attack"].items():
        lines.append(f"| {name} | {b['jobs']} | {b['none']} | {b['prompt']} | {b['full']} |")
    return lines + ["", "Source: `injection/asr.json`", ""]


def budgets_section() -> list[str]:
    d = load(RES / "budgets" / "budgets.json")
    if not d:
        return []
    dec = d["declared"]
    lines = [
        f"## Budgets (declared p95 {dec['p95_latency_s']['job']} s/job, {dec['p95_latency_s']['proposal']} s/proposal; {d['hardware']})",
        "",
        "| Configuration | Jobs | Proposals | p95 s/job | p95 s/proposal | Tokens/job | USD/job | Within latency budget |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, c in d["configurations"].items():
        ok = c["within_budget"]["latency_job"] and c["within_budget"]["latency_proposal"]
        lines.append(
            f"| {name} | {c['jobs']} | {c['proposals']} | {c['p95_latency_s']['job']} | {c['p95_latency_s']['proposal']} | "
            f"{c['mean_tokens']['job']} | {c['usd']['job']} | {'yes' if ok else 'no'} |"
        )
    return lines + ["", "Source: `budgets/budgets.json`", ""]


def extension_section() -> list[str]:
    d = load(RES / "extension" / "ab.json")
    if not d:
        return []
    return [
        "## Extension X2 - proposal strategy A/B (paired, GigSim)",
        "",
        "| Arm | Strategy | Pairs | Reply rate | Interview rate |",
        "|---|---|---|---|---|",
        f"| A | {d['arms']['A']} | {d['pairs']} | {fmt(d['reply_rate_A'])} | {fmt(d['interview_rate_A'])} |",
        f"| B | {d['arms']['B']} | {d['pairs']} | {fmt(d['reply_rate_B'])} | {fmt(d['interview_rate_B'])} |",
        "",
        f"Difference B - A {fmt(d['difference_B_minus_A'])} (95% CI {fmt(d['difference_ci95'][0])} to {fmt(d['difference_ci95'][1])}); "
        f"exact McNemar p = {d['mcnemar_exact_p']}.",
        "",
        "Source: `extension/ab.json`",
        "",
    ]


def failures_section() -> list[str]:
    d = load(RES / "failures" / "failures.json")
    if not d:
        return []
    lines = [
        f"## Failure analysis ({d['jobs']} dev jobs, rules mode; injection and tool errors from the LLM runs)",
        "",
        "| Category | Failed jobs |",
        "|---|---|",
    ]
    for name, n in sorted(d["base"]["failures"].items(), key=lambda x: -x[1]):
        lines.append(f"| {name} | {n} |")
    lines += [
        "",
        "| Fix (config override) | Target | Before | After | bid/skip F1 | Price in band | Worked |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, f in d["fixes"].items():
        lines.append(
            f"| {name} | {f['target']} | {f['target_failures_before']} | {f['target_failures_after']} | "
            f"{fmt(f['bid_skip_macro_f1'][0])} -> {fmt(f['bid_skip_macro_f1'][1])} | {fmt(f['price_in_band'][0])} -> {fmt(f['price_in_band'][1])} | "
            f"{'yes' if f['worked'] else 'no'} |"
        )
    return lines + ["", "Source: `failures/failures.json`", ""]


def smoke_section() -> list[str]:
    d = load(RES / "smoke" / "smoke.json")
    if not d:
        return []
    g = d["gates"]
    return [
        "## CI smoke eval gate",
        "",
        f"{d['jobs']} dev jobs: bid/skip macro-F1 {fmt(g['bid_skip_macro_f1']['value'])} (min {g['bid_skip_macro_f1']['min']}), "
        f"unsupported claims per proposal {fmt(g['unsupported_claims_per_proposal']['value'])} (max {g['unsupported_claims_per_proposal']['max']}); "
        f"passed: {d['passed']}.",
        "",
        "Source: `smoke/smoke.json`",
        "",
    ]


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
        + multiagent_section()
        + tools_section()
        + models_section()
        + injection_section()
        + budgets_section()
        + extension_section()
        + failures_section()
        + smoke_section()
    )
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
