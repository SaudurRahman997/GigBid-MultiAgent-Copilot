"""Claim-verification evaluation with labels BY CONSTRUCTION, plus unsupported-rate before/after.

Claims are built from generator-side project facts (data/personas/<p>/_meta/projects.json):
  supported    "I <approach> for <client type>, and we <metric>."   (exact portfolio facts)
  partial      the same claim with its number changed               (inflated result)
  unsupported  a claim about work the persona never did (persona_specs `lacks`)
Each draft = 2 supported + 1 partial + 1-2 unsupported claims, so the true unsupported rate is
known. The judge then labels every claim; `repair` removes what it calls unsupported.

Outputs evals/results/verify/verify_eval.json:
  accuracy, macro-F1, confusion matrix per judge; threshold sweep for the rerank judge (dev);
  unsupported-claim rate before (true) and after repair (true labels of the claims kept).

Usage: uv run python -m evals.runners.verify_eval [--judges rerank llm] [--jobs 15]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from evals.metrics import f1, mean
from rag.models import default_reranker
from rag.variants import CONTEXT_VARIANTS
from rag.variants.base import default_context
from rag.verify import ClaimCheck, RerankJudge, config, default_judge, gather_evidence

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "verify"
LABELS = ("supported", "partial", "unsupported")
SEED = 20261115


def specs() -> dict:
    return yaml.safe_load(
        (ROOT / "data" / "generators" / "persona_specs.yaml").read_text(encoding="utf-8")
    )


def inflate(metric: str, r: random.Random) -> str:
    def bump(m: re.Match) -> str:
        n = int(m.group(0))
        return str(n * 2 + r.randint(3, 9))

    out = re.sub(r"\d+", bump, metric, count=1)
    return out if out != metric else metric + " and doubled revenue"


def build_claims(persona: str, n_projects: int, r: random.Random) -> list[dict]:
    spec = specs()["personas"][persona]
    archetypes = {a["key"]: a for a in spec["archetypes"]}
    projects = json.loads(
        (ROOT / "data" / "personas" / persona / "_meta" / "projects.json").read_text(
            encoding="utf-8"
        )
    )
    lacks = [s for s in spec["lacks"] if s in specs()["lack_needs"]]
    drafts = []
    for i, p in enumerate(r.sample(projects, min(n_projects, len(projects)))):
        arch = archetypes[p["archetype"]]
        approach = arch["approach"][0].format(
            client=p["client"], noun=p["industry_noun"], **p["numbers"]
        )
        other = r.choice([q for q in projects if q["project_id"] != p["project_id"]])
        o_arch = archetypes[other["archetype"]]
        o_approach = o_arch["approach"][1].format(
            client=other["client"], noun=other["industry_noun"], **other["numbers"]
        )
        lack = r.choice(lacks)
        claims = [
            {
                "text": f"I {approach} for a {p['industry_noun']}, and we {p['metric']}.",
                "label": "supported",
            },
            {"text": f"For a {other['industry_noun']} I {o_approach}.", "label": "supported"},
            {
                "text": f"I {approach} for a {p['industry_noun']}, and we {inflate(p['metric'], r)}.",
                "label": "partial",
            },
            {
                "text": f"I have delivered several {lack} projects, including work as "
                f"{specs()['lack_needs'][lack].split(' to ')[0].removeprefix('a ').removeprefix('an ')}.",
                "label": "unsupported",
            },
        ]
        if i % 2 == 0:
            claims.append(
                {
                    "text": f"I have eight years of {r.choice(lacks)} experience with Fortune 500 clients.",
                    "label": "unsupported",
                }
            )
        drafts.append({"persona": persona, "project_id": p["project_id"], "claims": claims})
    return drafts


def confusion(pairs: list[tuple[str, str]]) -> dict:
    c = Counter(pairs)
    return {t: {p: c[(t, p)] for p in LABELS} for t in LABELS}


def macro_f1(pairs: list[tuple[str, str]]) -> float:
    scores = []
    for lab in LABELS:
        tp = sum(t == lab and p == lab for t, p in pairs)
        fp = sum(t != lab and p == lab for t, p in pairs)
        fn = sum(t == lab and p != lab for t, p in pairs)
        scores.append(f1(tp, fp, fn))
    return mean(scores)


def run_judge(judge, drafts: list[dict], evidence_cache: dict) -> list[tuple[str, str, ClaimCheck]]:
    out = []
    for d in drafts:
        for c in d["claims"]:
            check = judge.judge(c["text"], evidence_cache[(d["persona"], c["text"])])
            out.append((c["label"], check.status, check))
    return out


def before_after(drafts: list[dict], results: list[tuple[str, str, ClaimCheck]]) -> dict:
    it = iter(results)
    before, after = [], []
    for d in drafts:
        labs = [next(it) for _ in d["claims"]]
        before.append(sum(t == "unsupported" for t, _, _ in labs) / len(labs))
        kept = [t for t, p, _ in labs if p != "unsupported"]
        after.append(sum(t == "unsupported" for t in kept) / len(kept) if kept else 0.0)
    return {
        "unsupported_rate_before": round(mean(before), 4),
        "unsupported_rate_after": round(mean(after), 4),
        "drafts": len(drafts),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judges", nargs="+", default=["rerank"])
    ap.add_argument("--projects", type=int, default=12, help="projects (=drafts) per persona")
    ap.add_argument("--personas", nargs="+", default=["ai_ml", "fullstack", "data_analyst"])
    args = ap.parse_args(argv)
    cfg = config()
    r = random.Random(SEED)
    drafts = [d for p in args.personas for d in build_claims(p, args.projects, r)]
    evidence_cache = {}
    for p in args.personas:
        retriever = CONTEXT_VARIANTS[cfg["retrieval_variant"]](default_context(p))
        for d in (d for d in drafts if d["persona"] == p):
            for c in d["claims"]:
                evidence_cache[(p, c["text"])] = gather_evidence(c["text"], [], retriever, cfg["k"])
    n_claims = sum(len(d["claims"]) for d in drafts)
    print(f"{len(drafts)} drafts, {n_claims} claims", flush=True)

    result: dict = {
        "runner": "evals/runners/verify_eval.py",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "claims": n_claims,
        "label_counts": Counter(c["label"] for d in drafts for c in d["claims"]),
        "retrieval_variant": cfg["retrieval_variant"],
        "judges": {},
    }

    for name in args.judges:
        judge = default_judge(name)
        res = run_judge(judge, drafts, evidence_cache)
        pairs = [(t, p) for t, p, _ in res]
        entry = {
            "accuracy": round(mean([float(t == p) for t, p in pairs]), 4),
            "macro_f1": round(macro_f1(pairs), 4),
            "confusion": confusion(pairs),
            **before_after(drafts, res),
        }
        if name == "rerank":
            entry["thresholds"] = {
                "support_logit": cfg["support_logit"],
                "partial_logit": cfg["partial_logit"],
            }
            # threshold sweep (dev): best macro-F1 on this constructed set, reported not auto-applied
            scores = [(t, ch.score if ch.score is not None else -99.0, ch) for t, _, ch in res]
            sweep = []
            for hi in [-1.0, 0.0, 1.0, 2.0, 3.0, 4.0]:
                for lo in [-6.0, -5.0, -4.0, -3.0, -2.0, -1.0]:
                    if lo >= hi:
                        continue
                    sj = RerankJudge(default_reranker(), hi, lo, cfg["numbers_must_match"])
                    pp = [
                        (t, sj.judge(ch.text, evidence_cache[(d["persona"], ch.text)]).status)
                        for (t, _, ch), d in zip(
                            scores, [d for d in drafts for _ in d["claims"]], strict=True
                        )
                    ]
                    sweep.append(
                        {
                            "support_logit": hi,
                            "partial_logit": lo,
                            "macro_f1": round(macro_f1(pp), 4),
                        }
                    )
            entry["threshold_sweep_top5"] = sorted(sweep, key=lambda x: -x["macro_f1"])[:5]
            default_reranker().flush()
        result["judges"][name] = entry
        print(
            f"{name:<7} acc={entry['accuracy']:.3f} macroF1={entry['macro_f1']:.3f} "
            f"unsupported before={entry['unsupported_rate_before']:.3f} after={entry['unsupported_rate_after']:.3f}"
        )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verify_eval.json").write_text(
        json.dumps(result, indent=2, default=dict) + "\n", encoding="utf-8", newline="\n"
    )
    print("-> evals/results/verify/verify_eval.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
