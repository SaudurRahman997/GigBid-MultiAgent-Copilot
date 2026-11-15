"""Generate ~150 past proposals per persona with outcomes (data/personas/<p>/proposals.jsonl).

Outcomes are driven by PLANTED features so outcome-aware retrieval (V4) has a real signal:
  specific_evidence     cites a concrete past project and its measured result
  personalised_opening  first line restates the client's actual problem
  price_position        below | within | above the fair band for the category
Outcome model (documented in DATA_CARD, applied with a seeded RNG):
  score   = B0 + B_SPEC*specific + B_PERS*personal + B_PRICE[position] + Normal(0, NOISE)
  replied ~ Bernoulli(sigmoid(score)); won ~ Bernoulli(sigmoid(score + B_WON)) given replied
  outcome = won | replied | ignored
The proposal text is public portfolio material; the planted features sit under "_gold".
"""

from __future__ import annotations

import json
import math
import random
from datetime import timedelta
from pathlib import Path

from data.generators.common import (
    PERSONAS,
    REF_NOW,
    iso,
    price_band,
    provenance,
    rng,
    specs,
    stamp,
    write_jsonl,
)

PROV = provenance(__file__)
N_PER_PERSONA = 150
B0, B_SPEC, B_PERS, B_WON, NOISE = -1.4, 1.5, 1.1, -0.9, 0.6
B_PRICE = {"below": 0.2, "within": 0.4, "above": -1.0}
P_SPECIFIC, P_PERSONAL = 0.5, 0.5
PRICE_WEIGHTS = {"below": 0.25, "within": 0.5, "above": 0.25}

GENERIC_OPENINGS = [
    "Dear Hiring Manager, I am very interested in your job posting.",
    "Hello, I have read your job description and I am the perfect fit.",
    "Hi there! I can do this job for you.",
    "Greetings, I am an experienced professional ready to start immediately.",
]
PERSONAL_OPENINGS = [
    "It sounds like {need_lc} - and that the current workaround is eating your team's time.",
    "You need {need_lc}, ideally without disrupting how your team works today.",
    "Reading your post, the real goal seems to be {need_lc}, done properly the first time.",
]
GENERIC_BODIES = [
    "I have many years of experience with {skills} and always deliver high quality work on time.",
    "I am skilled in {skills} and have completed many similar projects with great feedback.",
]
SPECIFIC_BODIES = [
    "I did something very close for {client_desc}: I {approach}. The result was that we {metric}.",
    "Last time I solved this, for {client_desc}, I {approach} - and we {metric}.",
]
CLOSINGS = [
    "Happy to share a short plan after a quick call on the platform.",
    "I can start this week; let me know a good time to talk here.",
    "Looking forward to hearing from you.",
]


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def outcome(specific: bool, personal: bool, position: str, r: random.Random) -> tuple[str, float]:
    score = B0 + B_SPEC * specific + B_PERS * personal + B_PRICE[position] + r.gauss(0, NOISE)
    if r.random() >= sigmoid(score):
        return "ignored", score
    return ("won" if r.random() < sigmoid(score + B_WON) else "replied"), score


def bid_amount(band: dict, position: str, pay_type: str, r: random.Random) -> float:
    lo, hi = band["low"], band["high"]
    if position == "below":
        v = lo * r.uniform(0.55, 0.95)
    elif position == "within":
        v = r.uniform(lo, hi)
    else:
        v = hi * r.uniform(1.15, 1.8)
    return round(v, 0 if pay_type == "fixed" else 1)


def generate_for(pid: str, persona: dict, out_root: Path = PERSONAS) -> list[dict]:
    r = rng(f"proposals:{pid}")
    projects = json.loads((out_root / pid / "_meta" / "projects.json").read_text(encoding="utf-8"))
    archetypes = {a["key"]: a for a in persona["archetypes"]}
    proposals = []
    for n in range(1, N_PER_PERSONA + 1):
        arch = archetypes[r.choice(sorted(archetypes))]
        pay_type = r.choice(["fixed", "hourly"])
        band = price_band(persona["category"], arch["skills"], pay_type)
        specific = r.random() < P_SPECIFIC
        personal = r.random() < P_PERSONAL
        position = r.choices(
            sorted(PRICE_WEIGHTS), [PRICE_WEIGHTS[k] for k in sorted(PRICE_WEIGHTS)]
        )[0]
        need = arch["job_need"]
        cited = None
        if specific:
            same = [p for p in projects if p["archetype"] == arch["key"]]
            cited = r.choice(same)
            body = r.choice(SPECIFIC_BODIES).format(
                client_desc=f"a {cited['industry_noun']}",
                approach=arch["approach"][0].format(client=cited["client"], noun=cited["industry_noun"],
                                                    **cited["numbers"]),
                metric=cited["metric"],
            )  # fmt: skip
        else:
            body = r.choice(GENERIC_BODIES).format(skills=", ".join(arch["skills"][:3]))
        opening = (
            r.choice(PERSONAL_OPENINGS).format(need_lc=need[0].lower() + need[1:])
            if personal
            else r.choice(GENERIC_OPENINGS)
        )
        amount = bid_amount(band, position, pay_type, r)
        price_line = (
            f"My fixed price for this scope is ${amount:,.0f}."
            if pay_type == "fixed"
            else f"My rate is ${amount:,.1f}/hour."
        )
        text = f"{opening}\n\n{body}\n\n{price_line} {r.choice(CLOSINGS)}"
        result, score = outcome(specific, personal, position, r)
        sent = REF_NOW - timedelta(days=r.randint(20, 3 * 365))
        proposals.append(
            stamp(
                {
                    "id": f"{pid}:proposal:{n:03d}",
                    "persona": pid,
                    "type": "proposal",
                    "job_title": need[0].upper() + need[1:],
                    "category": persona["category"],
                    "skills": list(arch["skills"]),
                    "pay_type": pay_type,
                    "bid_usd": amount,
                    "date": iso(sent)[:10],
                    "text": text,
                    "outcome": result,
                    "cited_project_id": cited["project_id"] if cited else None,
                    "_gold": {
                        "specific_evidence": specific,
                        "personalised_opening": personal,
                        "price_position": position,
                        "fair_band": [band["low"], band["high"]],
                        "band_source": band["source"],
                        "score": round(score, 3),
                    },
                },
                PROV,
            )
        )
    write_jsonl(out_root / pid / "proposals.jsonl", proposals)
    return proposals


def main(out_root: Path = PERSONAS) -> None:
    for pid, persona in specs()["personas"].items():
        props = generate_for(pid, persona, out_root)
        outs = [p["outcome"] for p in props]
        print(pid, {k: outs.count(k) for k in ("won", "replied", "ignored")})


if __name__ == "__main__":
    main()
