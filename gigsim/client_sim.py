"""Simulated client: decides what happens after a proposal is submitted.

decide() combines the client's HIDDEN preferences with features of the proposal and a rubric
score, then draws a seeded outcome and a schedule of events:

  features  must_have_coverage  share of the job's must-have skills the proposal mentions
            price_ok            bid <= posted budget * hidden budget_ceiling_multiplier
            generic_opening     first lines match template-spam patterns
            specific_evidence   concrete past results with numbers ("cut ... by 40%")
  rubric    heuristic (default) or a seeded LLM call (config rubric.kind = llm)
  score     bias + weights . features + rubric_weight * (rubric - 0.5) + noise
  outcome   ignored | viewed | replied | interview | hired   (every non-hire ends with "lost")

The RNG is seeded from (seed, user, job, proposal text, bid), so the same submission always
gets the same outcome. Reasons are stored in `decisions` (visible to evals, never to agents).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import httpx

from gigsim.settings import PKG, Settings

WORD = re.compile(r"[a-z][a-z0-9+#.]{2,}")
STOP = set(
    [
        "the",
        "and",
        "for",
        "with",
        "our",
        "you",
        "your",
        "are",
        "this",
        "that",
        "need",
        "needs",
        "want",
        "looking",
        "from",
        "have",
        "will",
        "who",
        "can",
        "job",
        "project",
        "work",
        "help",
        "team",
        "using",
        "into",
        "about",
        "must",
    ]
)


@dataclass
class Decision:
    outcome: str
    score: float
    p: float
    features: dict
    reasons: list[str]
    events: list[dict] = field(default_factory=list)  # {type, delay_min, payload}
    client_messages: list[dict] = field(default_factory=list)  # {delay_min, text, intent}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@lru_cache(maxsize=4)
def skill_surfaces(data_dir: str) -> dict[str, set[str]]:
    """canonical skill -> lowercase surface forms (name + aliases) from the Phase 1 taxonomy."""
    path = Path(data_dir) / "processed" / "skill_taxonomy.json"
    surfaces: dict[str, set[str]] = {}
    if path.exists():
        tax = json.loads(path.read_text(encoding="utf-8"))
        for alias, canon in tax.get("aliases", {}).items():
            surfaces.setdefault(canon, {canon}).add(alias)
    return surfaces


def mentions(text: str, skill: str, data_dir: str) -> bool:
    low = text.lower()
    forms = skill_surfaces(data_dir).get(skill, set()) | {skill.lower()}
    return any(re.search(rf"(?<![a-z0-9]){re.escape(f)}(?![a-z0-9])", low) for f in forms)


def must_have_skills(job_public: dict, gold: dict) -> list[str]:
    reqs = gold.get("requirements")
    if reqs:
        return [r["skill"] for r in reqs if r.get("must_have")]
    return list(job_public.get("skills") or [])[:2]


def price_ceiling(job_public: dict, hidden: dict) -> float | None:
    mult = float(hidden.get("budget_ceiling_multiplier", 1.0))
    if job_public.get("pay_type") == "fixed" and job_public.get("budget_usd"):
        return float(job_public["budget_usd"]) * mult
    if job_public.get("hourly_high"):
        return float(job_public["hourly_high"]) * mult
    return None


def heuristic_rubric(
    job_public: dict, text: str, generic: bool, specific: bool
) -> tuple[float, list[str]]:
    title_words = {w for w in WORD.findall(job_public.get("title", "").lower()) if w not in STOP}
    body_words = set(WORD.findall(text.lower()))
    overlap = len(title_words & body_words)
    score, why = 0.3, []
    if overlap >= 2:
        score += 0.25
        why.append(f"refers to the job ({overlap} title terms)")
    if specific:
        score += 0.2
        why.append("concrete past results")
    if 300 <= len(text) <= 2500:
        score += 0.1
        why.append("reasonable length")
    if not generic:
        score += 0.15
        why.append("not a template opening")
    if len(text) > 4000:
        score -= 0.2
        why.append("too long")
    return max(0.0, min(1.0, score)), why


class LLMRubric:
    """Seeded OpenAI-compatible chat call (Groq, OpenRouter, Ollama /v1). Cached per input."""

    def __init__(self, settings: Settings):
        cfg = settings.model["rubric"]
        self.model = os.environ.get(cfg["llm_model_env"], "")
        self.base = os.environ.get(cfg["llm_base_url_env"], "")
        self.key = os.environ.get(cfg["llm_api_key_env"], "")
        self.seed = settings.seed
        self.template = (PKG / cfg["prompt_file"]).read_text(encoding="utf-8").split("---", 2)[-1]
        self.cache: dict[str, tuple[float, list[str]]] = {}

    def __call__(self, job_public: dict, hidden: dict, text: str) -> tuple[float, list[str]]:
        prompt = (
            self.template.replace("{job_title}", job_public.get("title", ""))
            .replace("{job_description}", job_public.get("description", "")[:4000])
            .replace("{client_preferences}", json.dumps(hidden, sort_keys=True))
            .replace("{proposal_text}", text[:5000])
        )
        k = hashlib.sha256(prompt.encode()).hexdigest()
        if k not in self.cache:
            resp = httpx.post(
                f"{self.base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "seed": self.seed,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            resp.raise_for_status()
            out = json.loads(resp.json()["choices"][0]["message"]["content"])
            self.cache[k] = (
                max(0.0, min(1.0, float(out["score"]))),
                list(out.get("reasons", []))[:5],
            )
        return self.cache[k]


def _delay(r: random.Random, bounds: list[int], factor: float) -> float:
    return round(r.uniform(*bounds) * factor, 1)


def decide(
    settings: Settings,
    user: str,
    job_public: dict,
    gold: dict,
    hidden: dict,
    cover_letter: str,
    screening: dict,
    bid: float,
    llm: LLMRubric | None = None,
) -> Decision:
    cfg = settings.model
    m = cfg["client_model"]
    w = m["weights"]
    text = cover_letter + "\n" + "\n".join(str(v) for v in screening.values())
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    r = random.Random(f"{settings.seed}:{user}:{job_public['job_id']}:{digest}:{bid}")
    resp = max(0.25, min(4.0, float(hidden.get("responsiveness_hours", 12)) / 12.0))
    delays = cfg["delays_minutes"]

    if gold.get("is_scam"):
        d = Decision(
            "replied",
            3.0,
            1.0,
            {"scam_client": True},
            ["scam client: replies fast, asks to go off-platform"],
        )
        d.events = [{"type": "viewed", "delay_min": _delay(r, delays["viewed"], 0.3)}]
        t_reply = d.events[0]["delay_min"] + _delay(r, delays["replied"], 0.3)
        d.events.append({"type": "replied", "delay_min": t_reply})
        d.client_messages.append(
            {"delay_min": t_reply, "text": r.choice(cfg["scam_replies"]), "intent": "scam_signal"}
        )
        return d

    must = must_have_skills(job_public, gold)
    covered = [s for s in must if mentions(text, s, str(settings.data_dir))]
    coverage = len(covered) / len(must) if must else 1.0
    strict = float(hidden.get("must_have_strictness", 0.5)) >= 0.8
    first_lines = cover_letter.strip()[:300]
    generic = any(re.search(p, first_lines) for p in cfg["generic_opening_patterns"])
    specific = any(re.search(p, text) for p in cfg["specific_evidence_patterns"])
    ceiling = price_ceiling(job_public, hidden)
    price_ok = ceiling is None or bid <= ceiling

    if cfg["rubric"]["kind"] == "llm" and llm is not None:
        try:
            rubric, rubric_why = llm(job_public, hidden, text)
        except Exception as exc:  # network / parsing: fall back, but record it
            rubric, rubric_why = heuristic_rubric(job_public, text, generic, specific)
            rubric_why = [f"llm rubric failed ({type(exc).__name__}); heuristic used", *rubric_why]
    else:
        rubric, rubric_why = heuristic_rubric(job_public, text, generic, specific)

    score = m["bias"]
    reasons = []
    eff_cov = (
        coverage if not (strict and coverage < m["strict_coverage_threshold"]) else coverage * 0.3
    )
    score += w["must_have_coverage"] * eff_cov
    missing = sorted(set(must) - set(covered))
    reasons.append(
        f"must-have coverage {coverage:.2f}"
        + (f" (missing: {', '.join(missing)})" if missing else "")
        + (" - strict client" if strict and missing else "")
    )
    if ceiling is not None:
        score += w["price_within_ceiling"] if price_ok else w["price_over_ceiling"]
        reasons.append(f"bid {bid:g} {'<=' if price_ok else '>'} hidden ceiling {ceiling:.0f}")
    if generic and hidden.get("dislikes_generic_opening"):
        score += w["generic_opening"]
        reasons.append("generic opening (client dislikes it)")
    if specific:
        score += w["specific_evidence"] * (1.0 if hidden.get("values_specific_evidence") else 0.5)
        reasons.append("specific evidence with numbers")
    score += w["reply_propensity"] * float(hidden.get("reply_propensity", 0.4))
    score += m["rubric_weight"] * (rubric - 0.5)
    reasons.append(f"rubric {rubric:.2f}: " + "; ".join(rubric_why))
    score += r.gauss(0, m["noise_sd"])
    p = sigmoid(score)

    features = {
        "must_have": must,
        "covered": covered,
        "coverage": round(coverage, 3),
        "strict_client": strict,
        "generic_opening": generic,
        "specific_evidence": specific,
        "price_ok": price_ok,
        "ceiling": round(ceiling, 2) if ceiling else None,
        "rubric": round(rubric, 3),
    }
    d = Decision("ignored", round(score, 4), round(p, 4), features, reasons)
    t = 0.0
    if r.random() >= m["p_viewed"]:
        d.events.append(
            {
                "type": "lost",
                "delay_min": _delay(r, delays["decision"], resp),
                "payload": {"reason": "no_response"},
            }
        )
        return d
    t += _delay(r, delays["viewed"], resp)
    d.events.append({"type": "viewed", "delay_min": t})
    d.outcome = "viewed"
    if r.random() < p:
        t += _delay(r, delays["replied"], resp)
        d.events.append({"type": "replied", "delay_min": t})
        d.client_messages.append(
            {"delay_min": t, "text": r.choice(cfg["client_reply_templates"]), "intent": "question"}
        )
        d.outcome = "replied"
        if r.random() < min(1.0, m["interview_share"] * 2 * p):
            t += _delay(r, delays["interview"], resp)
            d.events.append({"type": "interview", "delay_min": t})
            d.client_messages.append(
                {
                    "delay_min": t,
                    "intent": "interview_request",
                    "text": "We'd like to interview you. "
                    "Which times work for a 30-minute call this week?",
                }
            )
            d.outcome = "interview"
            if r.random() < min(1.0, m["hire_share"] * 2 * p):
                t += _delay(r, delays["decision"], resp)
                d.events.append({"type": "hired", "delay_min": t})
                d.outcome = "hired"
                return d
    t += _delay(r, delays["decision"], resp)
    d.events.append(
        {"type": "lost", "delay_min": t, "payload": {"reason": "client chose someone else"}}
    )
    return d
