"""Decide -> Pricing -> Writer -> Verify claims -> Critic (loop <= N) -> Compliance."""

from __future__ import annotations

import re

from agent.handoffs import (
    BidDecision,
    Claim,
    ComplianceVerdict,
    Critique,
    FitReport,
    PriceQuote,
    ProposalDraft,
)
from agent.memory.store import style_rules
from agent.nodes.analysis import _coverage
from agent.prompt_loader import render
from agent.runtime import Deps, ask, node, parse_json, untrusted
from rag.verify import ClaimCheck, repair

CITE = re.compile(r"\[[a-z_]+:[a-z_]+:[A-Za-z0-9_\-]+\]|\[[a-z_]+:cv\]")

# ----------------------------------------------------------------------------- decide


@node("decide")
async def decide(state: dict, deps: Deps) -> dict:
    """Reconcile the parallel analyses into skip | watch | bid (thresholds in config.decision)."""
    spec, risk, fit, profile = state["spec"], state["risk"], state["fit"], state["profile"]
    cfg = deps.config["decision"]
    score, gaps = _coverage(spec.requirements, set(profile["skills"]))  # analyst's must-haves win
    fit = FitReport(score=score, matrix=fit.matrix, gaps=gaps, reasons=fit.reasons + [f"reconciled with JobSpec: {score:.2f}"])
    b, floors = spec.budget, profile["floors"]
    reasons: list[str] = []
    if risk.verdict == "block":
        action, reasons = "skip", [f"risk: {', '.join(f for f in risk.flags if f != 'injection')}"]
    elif gaps:
        action, reasons = "skip", [f"missing must-have skills: {', '.join(gaps)}"]
    elif b.pay_type == "fixed" and (b.amount or 0) < floors["fixed"]:
        action, reasons = "skip", [f"budget {b.amount} below floor {floors['fixed']}"]
    elif b.pay_type == "hourly" and (b.hourly_high or 0) < floors["hourly"]:
        action, reasons = "skip", [f"hourly max {b.hourly_high} below floor {floors['hourly']}"]
    elif risk.client_score < cfg["min_client_score"]:
        action, reasons = "skip", [f"client score {risk.client_score} below {cfg['min_client_score']}"]
    elif score < cfg["watch_min_fit"]:
        action, reasons = "skip", [f"fit {score:.2f} below {cfg['watch_min_fit']}"]
    elif score < cfg["min_fit_to_bid"]:
        action, reasons = "watch", [f"fit {score:.2f} below bid threshold {cfg['min_fit_to_bid']}"]
    else:
        action, reasons = "bid", [f"fit {score:.2f}, client {risk.client_score}, risk {risk.verdict}"]
    auto = action == "skip" and score < deps.config["autonomy"]["auto_skip_below_fit"]
    status = {"skip": "skipped", "watch": "watch", "bid": "running"}[action]
    return {"decision": BidDecision(action=action, reasons=reasons, auto=auto), "fit": fit, "status": status,
            "_note": f"{action}: {reasons[0]}"}  # fmt: skip


# ----------------------------------------------------------------------------- pricing


@node("pricing")
async def pricing(state: dict, deps: Deps) -> dict:
    spec, profile = state["spec"], state["profile"]
    b = spec.budget
    skills = [r.skill for r in spec.requirements if r.skill][:10]
    band = await deps.mcp.call("pricing", "get_market_rates", {"category": spec.category, "pay_type": b.pay_type, "skills": skills})
    cfg = deps.config["pricing"]
    lo, hi = band["low"], band["high"]
    if b.pay_type == "hourly":
        target = cfg["hourly_target_weight"] * profile["target_rate"] + (1 - cfg["hourly_target_weight"]) * band["median"]
        amount = max(profile["floors"]["hourly"], target)
        if b.hourly_high:
            amount = min(amount, b.hourly_high)  # stay inside the client's posted range
        amount = round(amount, 1)
    else:
        amount = max(profile["floors"]["fixed"], band["median"])
        if b.amount:
            amount = min(max(amount, b.amount * 0.9), b.amount * cfg["fixed_cap_over_budget"])
        amount = float(round(amount, -1 if amount > 100 else 0))
    cost = int(spec.connects_required or 8)
    worth = cost <= deps.config["decision"]["max_connects"] and state["fit"].score >= deps.config["decision"]["min_fit_to_bid"]
    in_band = "inside" if lo <= amount <= hi else ("below" if amount < lo else "above")
    quote = PriceQuote(amount=amount, kind=b.pay_type, band=(lo, hi), connects_cost=cost, worth_it=worth,
                       rationale=f"{band['source']} band {lo}-{hi} (n={band['n']}); quote {amount} is {in_band} the band")  # fmt: skip
    return {"price": quote, "_note": quote.rationale}


# ----------------------------------------------------------------------------- writer


def evidence_list(fit: FitReport, limit: int = 8) -> list[dict]:
    seen, out = set(), []
    for req, refs in fit.matrix.items():
        for r in refs:
            if r.evidence_id not in seen:
                seen.add(r.evidence_id)
                out.append({"id": r.evidence_id, "snippet": r.snippet, "requirement": req, "outcome": r.outcome})
    return out[:limit]


def template_letter(spec, evidence: list[dict], price: PriceQuote) -> str:
    """Rules-mode writer: restated need, cited evidence sentences, must-have skills, price."""
    need = next((r.text for r in spec.requirements if r.kind != "constraint"), spec.title)
    lines = [f"You need {need[0].lower() + need[1:]} for {spec.title.lower()}." if need else spec.title]
    for e in [e for e in evidence if e["id"].split(":")[1] != "proposal"][:3]:
        sent = e["snippet"].replace("\n", " ").split(". ")[0].rstrip(".")
        lines.append(f"{sent}. [{e['id']}]")
    musts = [r.skill for r in spec.requirements if r.must_have and r.skill]
    if musts:
        lines.append(f"I work hands-on with {', '.join(musts)}.")
    unit = "/hour" if price.kind == "hourly" else " fixed"
    lines.append(f"My price for this is ${price.amount:,.0f}{unit}. Happy to agree a first milestone here on the platform.")
    return "\n\n".join(lines)


@node("writer")
async def writer(state: dict, deps: Deps) -> dict:
    spec, price = state["spec"], state["price"]
    evidence = evidence_list(state["fit"])
    version = (state["draft"].version + 1) if state.get("draft") else 1
    issues = state["critique"].issues if state.get("critique") and not state["critique"].approve else []
    rules = style_rules(deps.store, deps.user)
    if deps.mode("writer") != "llm":
        letter = template_letter(spec, evidence, price)
        return {"draft": ProposalDraft(version=version, cover_letter=letter), "evidence": evidence, "_note": f"template v{version}"}
    prompt = render(
        "writer", max_words=str(deps.config["writer"]["max_words"]),
        price=f"{price.amount} ({price.kind})", style_rules="\n".join(f"- {r}" for r in rules) or "- (none yet)",
        critique_issues="\n".join(f"- {i}" for i in issues) or "- (first draft)",
        spec=untrusted("JOB SPEC", spec.model_dump_json(include={"title", "requirements", "screening_questions", "hidden_needs"})),
        evidence="\n".join(f"- {e['id']}: {e['snippet']}" for e in evidence),
    )  # fmt: skip
    try:
        text, tokens = await ask(deps, "writer", prompt)
        out = parse_json(text)
        draft = ProposalDraft(version=version, cover_letter=str(out["cover_letter"]).strip(),
                              screening_answers={str(k): str(v) for k, v in (out.get("screening_answers") or {}).items()})  # fmt: skip
        return {"draft": draft, "evidence": evidence, "tokens": tokens, "_note": f"llm v{version}"}
    except Exception as exc:  # noqa: BLE001
        if not deps.config.get("agents", {}).get("fallback_to_rules_on_llm_error", True):
            raise
        letter = template_letter(spec, evidence, price)
        return {"draft": ProposalDraft(version=version, cover_letter=letter), "evidence": evidence,
                "errors": [f"writer llm fallback: {exc}"], "_note": f"template v{version} (llm failed)"}  # fmt: skip


# ----------------------------------------------------------------------------- verify claims


@node("verify_claims")
async def verify_claims(state: dict, deps: Deps) -> dict:
    draft = state["draft"]
    text = draft.cover_letter + "\n\n" + "\n".join(draft.screening_answers.values())
    res = await deps.mcp.call("verifier", "verify_claims", {"draft": text[:6000]})
    checks = [ClaimCheck(text=c["text"], status=c["status"], evidence=c["evidence"], cited=c.get("cited", []),
                         reason=c["reason"]) for c in res["checks"]]  # fmt: skip
    cleaned, report = repair(draft.cover_letter, checks)
    claims = [Claim(text=c.text, status=c.status, evidence=c.evidence) for c in checks]
    new = draft.model_copy(update={"cover_letter": cleaned or draft.cover_letter, "claims": claims})
    return {"draft": new, "verify_report": {k: v for k, v in report.items() if k != "checks"},
            "_note": f"unsupported {report['unsupported_before']}/{report['claims_before']} removed"}  # fmt: skip


# ----------------------------------------------------------------------------- critic


def rules_critique(spec, draft: ProposalDraft, price: PriceQuote, max_words: int) -> list[str]:
    text = draft.cover_letter
    issues = []
    if re.match(r"(?i)\s*(dear|hello|hi there|greetings)", text):
        issues.append("Opening is generic; restate the client's problem instead.")
    if len(text.split()) > max_words:
        issues.append(f"Too long ({len(text.split())} words > {max_words}).")
    if len(CITE.findall(text)) < 1:
        issues.append("No claim cites portfolio evidence.")
    for r in spec.requirements:
        if r.must_have and r.skill and r.skill.lower() not in text.lower():
            issues.append(f"Must-have '{r.skill}' is not addressed.")
    if f"{price.amount:,.0f}" not in text and f"{price.amount:g}" not in text:
        issues.append(f"Price {price.amount} is missing or differs from the quote.")
    return issues


@node("critic")
async def critic(state: dict, deps: Deps) -> dict:
    spec, draft, price = state["spec"], state["draft"], state["price"]
    rnd = state.get("critic_round", 0) + 1
    max_words = deps.config["writer"]["max_words"]
    issues = rules_critique(spec, draft, price, max_words)
    tokens = 0
    if deps.mode("critic") == "llm":
        try:
            report = "\n".join(f"- {c.text[:120]} -> {c.status}" for c in draft.claims) or "- (no claims)"
            text, tokens = await ask(deps, "critic", render("critic", max_words=str(max_words), verify_report=report,
                                                            spec=untrusted("JOB SPEC", spec.model_dump_json(include={"title", "requirements"})),
                                                            draft=draft.cover_letter))  # fmt: skip
            out = parse_json(text)
            issues = list(dict.fromkeys(issues + [str(i) for i in out.get("issues", [])]))[:8]
            approve = bool(out.get("approve")) and not issues
        except Exception as exc:  # noqa: BLE001
            approve = not issues
            issues.append(f"(critic llm unavailable: {type(exc).__name__})") if not approve else None
    else:
        approve = not issues
    return {"critique": Critique(approve=approve, issues=issues, round=rnd), "critic_round": rnd, "tokens": tokens,
            "_note": "approve" if approve else f"round {rnd}: {len(issues)} issues"}  # fmt: skip


# ----------------------------------------------------------------------------- compliance


def check_compliance(text: str, policy: dict, claims: list[Claim]) -> ComplianceVerdict:
    violations, warnings = [], []
    for rule in policy["rules"]:
        for name, pat in (rule.get("patterns") or {}).items():
            if re.search(pat, text):
                (violations if rule["severity"] == "block" else warnings).append(f"{rule['id']}:{name}")
    if any(c.status == "unsupported" for c in claims):
        violations.append("no_fabricated_experience:unsupported_claim")
    return ComplianceVerdict(allowed=not violations, violations=violations, redactions=warnings)


@node("compliance")
async def compliance(state: dict, deps: Deps) -> dict:
    draft = state["draft"]
    text = draft.cover_letter + "\n" + "\n".join(draft.screening_answers.values())
    verdict = check_compliance(text, deps.policy, draft.claims)
    out: dict = {"compliance": verdict, "_note": "allowed" if verdict.allowed else f"blocked: {verdict.violations}"}
    if not verdict.allowed:
        out |= {"status": "blocked", "attention_reason": f"compliance: {', '.join(verdict.violations)}"}
    return out


