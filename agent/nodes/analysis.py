"""Scout + the three parallel analysts (Job Analyst || Risk Assessor || Fit Matcher).

Each analyst writes only its own state key (spec / risk / fit), so the parallel branches never
conflict. All outside data arrives through MCP tools on the node's allowlist.
"""

from __future__ import annotations

import math
import re

from agent.handoffs import Budget, EvidenceRef, FitReport, JobSpec, Requirement, RiskReport
from agent.prompt_loader import render
from agent.runtime import Deps, ask, node, parse_json, untrusted
from rag.ingest.loaders import detect_skills
from rag.query import VAGUE, clean_requirement, from_job

# ----------------------------------------------------------------------------- scout


@node("scout_in")
async def scout_in(state: dict, deps: Deps) -> dict:
    job = await deps.mcp.call("scout", "get_job", {"job_id": state["job_id"]})
    return {"job": job, "status": "running", "_note": job["title"][:80]}


# ----------------------------------------------------------------------------- job analyst


def rules_spec(job: dict) -> JobSpec:
    """Deterministic JobSpec: requirement bullets (+ named skills), must-have markers, budget."""
    reqs: list[Requirement] = []
    for line in job["description"].split("\n"):
        if not line.strip().startswith(("-", "•")):
            continue
        raw = line.strip("-• ").strip()
        must = "(must have)" in raw.lower() or bool(
            re.search(r"\b(must|required|essential)\b", raw, re.I)
        )
        text = clean_requirement(raw)
        if VAGUE.search(raw):
            reqs.append(Requirement(text=text, kind="constraint", must_have=False))
            continue
        skills = detect_skills(text)
        reqs.append(
            Requirement(
                text=text, kind="skill", must_have=must, skill=skills[0] if skills else None
            )
        )
    named = {r.skill for r in reqs if r.skill}
    # "<Skill> expert needed ..." - a skill named in the title is a must-have
    for sk in detect_skills(job["title"]):
        if sk not in named:
            reqs.append(Requirement(text=sk, kind="skill", must_have=True, skill=sk))
            named.add(sk)
    for sk in job.get("skills") or []:
        if sk not in named:
            reqs.append(Requirement(text=sk, kind="skill", must_have=False, skill=sk))
    return JobSpec(
        job_id=job["job_id"], title=job["title"], requirements=reqs, budget=_budget(job),
        screening_questions=job.get("screening_questions") or [], category=job.get("category") or "other",
        client_id=job.get("client_id"), connects_required=job.get("connects_required"), applicants=job.get("applicants"),
    )  # fmt: skip


def _budget(job: dict) -> Budget:
    pay = job.get("pay_type") if job.get("pay_type") in ("fixed", "hourly") else "fixed"
    return Budget(pay_type=pay, amount=job.get("budget_usd"), hourly_low=job.get("hourly_low"),
                  hourly_high=job.get("hourly_high"))  # fmt: skip


@node("job_analyst")
async def job_analyst(state: dict, deps: Deps) -> dict:
    job = state["job"]
    base = rules_spec(job)
    if deps.mode("job_analyst") != "llm":
        return {"spec": base, "_note": f"rules: {len(base.requirements)} requirements"}
    try:
        text, tokens = await ask(
            deps,
            "job_analyst",
            render("job_analyst", job=untrusted("JOB", f"{job['title']}\n\n{job['description']}")),
        )
        out = parse_json(text)
        reqs = [Requirement.model_validate(r) for r in out.get("requirements", [])][:15]
        spec = base.model_copy(update={"requirements": reqs or base.requirements, "timeline": out.get("timeline"),
                                       "hidden_needs": list(out.get("hidden_needs") or [])[:3],
                                       "screening_questions": base.screening_questions or list(out.get("screening_questions") or [])})  # fmt: skip
        return {
            "spec": spec,
            "tokens": tokens,
            "_note": f"llm: {len(spec.requirements)} requirements",
        }
    except Exception as exc:  # noqa: BLE001 - fall back, but say so
        if not deps.config.get("agents", {}).get("fallback_to_rules_on_llm_error", True):
            raise
        return {
            "spec": base,
            "errors": [f"job_analyst llm fallback: {exc}"],
            "_note": "rules (llm failed)",
        }


# ----------------------------------------------------------------------------- risk assessor


def client_score(hist: dict, weights: dict) -> float:
    rating = hist.get("rating")
    r = 0.5 if rating is None else max(0.0, min(1.0, (rating - 3.0) / 2.0))
    hire = float(hist.get("hire_rate") or 0.0)
    jobs_posted = hist.get("jobs_posted") or 0
    hire_part = 0.5 if jobs_posted < 3 else min(1.0, hire / 0.6)  # little history: neutral
    spend = min(1.0, math.log10(1 + float(hist.get("total_spent_usd") or 0)) / 4)
    score = (weights["payment_verified"] * float(bool(hist.get("payment_verified"))) + weights["rating"] * r
             + weights["hire_rate"] * hire_part + weights["spend"] * spend)  # fmt: skip
    return round(max(0.0, min(1.0, score)), 3)


def client_red_flags(hist: dict, rules: dict) -> list[str]:
    flags = []
    if hist.get("rating") is not None and hist["rating"] < rules["min_rating"]:
        flags.append(f"rating {hist['rating']} < {rules['min_rating']}")
    if (hist.get("jobs_posted") or 0) >= rules["low_hire_min_posts"] and (
        hist.get("hire_rate") or 0
    ) < rules["low_hire_rate"]:
        flags.append(f"hire rate {hist.get('hire_rate')} over {hist.get('jobs_posted')} posts")
    if (
        not hist.get("payment_verified")
        and not hist.get("total_spent_usd")
        and (hist.get("jobs_posted") or 0) >= rules["unverified_ghost_posts"]
    ):
        flags.append(f"unverified, $0 spent, {hist.get('jobs_posted')} posts")
    return flags


def injection_spans(text: str, patterns: list[str]) -> list[str]:
    spans = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if any(re.search(p, sentence) for p in patterns):
            spans.append(sentence.strip()[:300])
    return spans


@node("risk_assessor")
async def risk_assessor(state: dict, deps: Deps) -> dict:
    job = state["job"]
    pol = deps.policy
    text = f"{job['title']}\n{job['description']}"
    flags: list[str] = []
    reasons: list[str] = []
    for name, pat in pol["scam_signals"].items():
        if re.search(pat, text, re.I):
            flag = "off_platform" if name == "crypto" else name
            if flag not in flags:
                flags.append(flag)
            reasons.append(f"scam signal: {name}")
    spans = injection_spans(text, pol["injection_patterns"])
    if spans:
        flags.append("injection")
        reasons.append(f"prompt injection detected ({len(spans)} span(s)); treated as data")
    hist = await deps.mcp.call(
        "risk_assessor", "get_client_history", {"client_id": job["client_id"]}
    )
    score = client_score(hist, pol["client_score"])
    red = client_red_flags(hist, pol["client_red_flags"])
    reasons.append(f"client score {score}" + (f"; red flags: {'; '.join(red)}" if red else ""))
    floor = deps.config["decision"]["min_client_score"]
    score = (
        min(score, floor - 0.01) if red else max(score, floor)
    )  # red flags decide; score is for display
    scam = [f for f in flags if f not in ("injection", "duplicate")]
    verdict = "block" if scam else ("caution" if spans or red else "ok")
    risk = RiskReport(
        client_score=score, flags=flags, injection_spans=spans, verdict=verdict, reasons=reasons
    )
    return {"risk": risk, "_note": f"{verdict} {flags}"}


# ----------------------------------------------------------------------------- fit matcher


@node("fit_matcher")
async def fit_matcher(state: dict, deps: Deps) -> dict:
    """Retrieves evidence per requirement (rules decomposition: runs in parallel with the analyst)."""
    job = state["job"]
    profile = await deps.mcp.call("fit_matcher", "get_profile", {})
    q = from_job(job["title"], job["description"], job.get("skills"))
    matrix: dict[str, list[EvidenceRef]] = {}
    for req in q.requirements[:6]:
        res = await deps.mcp.call(
            "fit_matcher", "search_evidence", {"requirement": req[:500], "k": 3}
        )
        matrix[req] = [EvidenceRef(evidence_id=h["id"], snippet=h["snippet"], score=h["score"], outcome=h.get("outcome"))
                       for h in res["items"]]  # fmt: skip
    spec = rules_spec(job)
    covered, gaps = _coverage(spec.requirements, set(profile["skills"]))
    fit = FitReport(score=covered, matrix=matrix, gaps=gaps,
                    reasons=[f"profile skills cover {covered:.2f} of weighted requirements"])  # fmt: skip
    return {"fit": fit, "profile": profile, "_note": f"fit {covered:.2f} gaps {gaps}"}


def _coverage(reqs: list[Requirement], skills: set[str]) -> tuple[float, list[str]]:
    """Weighted skill coverage: must-haves weigh 0.7, nice-to-haves 0.3. Unknown-skill must-haves
    count as covered only if a profile skill appears in their text."""
    must = [r for r in reqs if r.kind == "skill" and r.must_have]
    nice = [r for r in reqs if r.kind == "skill" and not r.must_have]

    def ok(r: Requirement) -> bool:
        if r.skill:
            return r.skill in skills
        low = r.text.lower()
        return any(re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", low) for s in skills)

    gaps = [r.skill or r.text for r in must if not ok(r)]
    m = sum(ok(r) for r in must) / len(must) if must else 1.0
    n = sum(ok(r) for r in nice) / len(nice) if nice else 1.0
    return round(0.7 * m + 0.3 * n, 3), gaps
