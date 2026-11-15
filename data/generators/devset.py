"""Build the dev set and the held-out test set with gold labels BY CONSTRUCTION.

Per persona we construct 300 jobs and split them 200 dev (data/devset/<persona>.jsonl,
committed) / 100 test (data/heldout/<persona>.jsonl, git-ignored, never tuned on).

How each gold label is produced (no LLM judges anything here):
  gold_evidence_ids    the job is written FROM 1-2 "anchor" portfolio projects; requirements
                       are drawn from the anchors' skills; the anchors' evidence items (case
                       study, README, code, reviews; 2-5 items) are the gold. Requirements are
                       phrased by name, by synonym, or only implied, so lexical match is not enough.
  gold_related_ids     case studies of OTHER projects of the same archetype (graded relevance 1)
  gold_bid             bid_rule() below, applied to the constructed job (and asserted against
                       the job type that was planted)
  gold_is_scam         planted (scam template)
  gold_has_injection   planted (instruction inserted into the description)
  gold_price_band      p25..p75 of real Kaggle prices for the first required skill with
                       n >= 100, else the persona's category (common.price_band)

bid_rule (also in docs/DATA_CARD.md), first matching reason wins:
  1. scam                -> skip (reason "scam")
  2. a must-have skill is not in the persona's skills -> skip ("missing_skill")
  3. fixed budget < persona fixed floor, or hourly max < persona hourly floor -> skip ("low_budget")
  4. client history_quality == "poor" -> skip ("poor_client")
  otherwise -> bid
"""

from __future__ import annotations

import json
import random
from datetime import timedelta
from pathlib import Path

from data.generators.common import (
    DEVSET,
    HELDOUT,
    PERSONAS,
    REF_NOW,
    SYNTHETIC,
    connects_cost,
    iso,
    price_band,
    provenance,
    read_jsonl,
    rng,
    specs,
    stamp,
    weighted_choice,
    write_jsonl,
)
from data.generators.jobs import INJECTIONS, SCAM_TASKS, SCAMS

PROV = provenance(__file__)
N_PER_PERSONA, N_DEV = 300, 200
JOB_TYPES = {
    "bid": 0.50,
    "missing_skill": 0.15,
    "scam": 0.10,
    "low_budget": 0.12,
    "poor_client": 0.13,
}
SHARE_INJECTION = 0.05
P_TWO_ANCHORS = 0.3
PHRASING = {"name": 0.45, "synonym": 0.30, "implied": 0.25}
MAX_GOLD, MIN_GOLD = 5, 2
EVIDENCE_PRIORITY = ["case_study", "readme", "review", "code"]

INTROS_NOUN = [  # need is a noun phrase: "a chatbot that ..."
    "We're {a_noun} and we need {need}.",
    "Our team at {a_noun} is looking for help: we need {need}.",
    "Hi! We run {a_noun}. The project: {need}.",
    "{Need_cap} - that's what we're after. We're {a_noun} with a small in-house team.",
]
INTROS_VERB = [  # need is a verb phrase: "predict which customers ..."
    "We're {a_noun} and we want to {need}.",
    "Our team at {a_noun} is looking for someone to help us {need}.",
    "Hi! We run {a_noun}. Goal: {need}.",
    "We need to {need}. We're {a_noun} with a small in-house team.",
]


def intro_for(need: str, a_noun: str, r: random.Random) -> str:
    noun_phrase = need.split()[0].lower() in {"a", "an", "one", "the"}
    tpl = r.choice(INTROS_NOUN if noun_phrase else INTROS_VERB)
    return tpl.format(a_noun=a_noun, need=need, Need_cap=need[:1].upper() + need[1:])


TITLES = [
    "{skill} expert needed for {noun} project",
    "Freelancer to build {deliverable} ({skill})",
    "Help wanted: {short_need}",
    "{skill} specialist - {deliverable}",
]
SCREENING = [
    "Describe a similar project you have delivered and its result.",
    "Which tools would you use for this and why?",
    "How would you measure whether this project succeeded?",
    "What would you need from us in the first week?",
    "What is the biggest risk you see in this project?",
]


def display(skill: str) -> str:
    """'sql' -> 'SQL', 'aws' -> 'AWS', 'react' -> 'React'."""
    return skill.upper() if skill.isalpha() and len(skill) <= 4 else skill[:1].upper() + skill[1:]


def with_article(noun: str) -> str:
    return ("an " if noun[0].lower() in "aeiou" else "a ") + noun


def bid_rule(job: dict, persona_skills: set[str], floors: dict, client_quality: str,
             is_scam: bool) -> tuple[str, str | None]:  # fmt: skip
    """The written bid/skip rule. Returns (decision, reason)."""
    if is_scam:
        return "skip", "scam"
    if any(r["must_have"] and r["skill"] not in persona_skills for r in job["requirements"]):
        return "skip", "missing_skill"
    if job["pay_type"] == "fixed" and (job["budget_usd"] or 0) < floors["fixed"]:
        return "skip", "low_budget"
    if job["pay_type"] == "hourly" and (job["hourly_high"] or 0) < floors["hourly"]:
        return "skip", "low_budget"
    if client_quality == "poor":
        return "skip", "poor_client"
    return "bid", None


def phrase(skill: str, how: str, synonyms: dict, r: random.Random) -> tuple[str, str]:
    """Requirement text for one skill and the phrasing actually used."""
    if how == "synonym" and synonyms.get(skill):
        return f"Experience with {r.choice(synonyms[skill])}", "synonym"
    if how == "implied":
        return "You have shipped something like this before (tell us about it)", "implied"
    return f"Strong {skill} skills", "name"


def gold_evidence(anchors: list[dict], r: random.Random) -> list[str]:
    per = MAX_GOLD if len(anchors) == 1 else r.choice([2, 3])
    gold: list[str] = []
    for p in anchors:
        ranked = sorted(
            p["evidence_items"], key=lambda e: (EVIDENCE_PRIORITY.index(e["type"]), e["id"])
        )
        take = per if p is anchors[0] else MAX_GOLD - len(gold)
        gold += [e["id"] for e in ranked[: max(MIN_GOLD, min(take, MAX_GOLD - len(gold)))]]
    return gold[:MAX_GOLD]


def budget_for(band: dict, pay_type: str, floors: dict, low: bool, r: random.Random) -> dict:
    if pay_type == "fixed":
        if low:
            amount = floors["fixed"] * r.uniform(0.2, 0.8)
        else:
            amount = max(
                floors["fixed"] * r.uniform(1.0, 1.4),
                r.uniform(band["low"], max(band["p90"], band["low"] + 1)),
            )
        return {
            "budget_usd": float(round(amount, -1 if amount > 100 else 0)),
            "hourly_low": None,
            "hourly_high": None,
        }
    if low:
        hi = floors["hourly"] * r.uniform(0.4, 0.9)
        lo = hi * 0.6
    else:
        lo = max(floors["hourly"], band["low"] * r.uniform(0.9, 1.1))
        hi = max(lo + 5, band["high"] * r.uniform(1.0, 1.3))
    return {"budget_usd": None, "hourly_low": float(round(lo)), "hourly_high": float(round(hi))}  # fmt: skip


def build_job(pid: str, persona: dict, profile: dict, projects: list[dict], clients: dict,
              job_type: str, r: random.Random) -> dict:  # fmt: skip
    synonyms = specs()["synonyms"]
    industries = specs()["industries"]
    archetypes = {a["key"]: a for a in persona["archetypes"]}
    persona_skills = set(profile["skills"])
    pay_type = r.choice(["fixed", "hourly"])
    anchors: list[dict] = []
    is_scam = job_type == "scam"
    scam_type = None

    if is_scam:
        scam_type = r.choice(sorted(SCAMS))
        spec = SCAMS[scam_type]
        title = r.choice(spec["titles"])
        desc = r.choice(spec["bodies"]).format(task=r.choice(SCAM_TASKS), n=r.randint(100, 999),
                                               fee=r.choice([25, 49, 75, 120]))  # fmt: skip
        requirements = []
        noun = "company"
        band = price_band(persona["category"], [], pay_type)
        money = budget_for(band, pay_type, persona["floors"], False, r)
        if scam_type == "vague_high_budget" and pay_type == "fixed":
            money["budget_usd"] = float(r.choice([10000, 25000, 50000]))
        screening = []
    elif job_type == "missing_skill":
        lack = r.choice([s for s in persona["lacks"] if s in specs()["lack_needs"]])
        need = specs()["lack_needs"][lack]
        extra = r.sample(
            sorted(persona_skills - set(persona["base_skills"])) or sorted(persona_skills), 2
        )
        requirements = [
            {
                "skill": lack,
                "must_have": True,
                "text": f"Proven {lack} experience (must have)",
                "phrasing": "name",
            }
        ]
        requirements += [{"skill": s, "must_have": False, "text": f"Nice to have: {s}", "phrasing": "name"}
                         for s in extra]  # fmt: skip
        ind = r.choice(sorted(industries))
        noun = industries[ind]["noun"]
        title = f"{lack.title()} expert needed for {noun} project"
        desc = f"We're {with_article(noun)} looking for {need}."
        band = price_band(persona["category"], [lack], pay_type)
        money = budget_for(band, pay_type, persona["floors"], False, r)
        screening = r.sample(SCREENING, r.randint(1, 3))
    else:
        n_anchor = 2 if r.random() < P_TWO_ANCHORS else 1
        first = r.choice(projects)
        anchors = [first]
        if n_anchor == 2:
            others = [p for p in projects if p["archetype"] != first["archetype"]]
            anchors.append(r.choice(others))
        arch = archetypes[first["archetype"]]
        pool = list(dict.fromkeys(s for p in anchors for s in archetypes[p["archetype"]]["skills"]))
        chosen = r.sample(pool, k=min(len(pool), r.randint(2, 4)))
        n_must = r.randint(1, min(2, len(chosen)))
        requirements = []
        for i, s in enumerate(chosen):
            text, used = phrase(s, weighted_choice(r, PHRASING), synonyms, r)
            must = i < n_must
            requirements.append({"skill": s, "must_have": must, "phrasing": used,
                                 "text": text + (" (must have)" if must else "")})  # fmt: skip
        ind = r.choice(sorted(industries))
        noun = industries[ind]["noun"]
        need = arch["job_need"]
        if n_anchor == 2:
            need += ", plus " + archetypes[anchors[1]["archetype"]]["job_need"]
        named = next((r_["text"].replace("Strong ", "").replace(" skills", "").replace(" (must have)", "")
                      for r_ in requirements if r_["phrasing"] == "name"), None)  # fmt: skip
        skill_label = named or r.choice(synonyms.get(chosen[0], [chosen[0]]))
        title = r.choice(TITLES).format(skill=display(skill_label), noun=noun,
                                        deliverable=r.choice(arch["deliverables"]),
                                        short_need=arch["job_need"].split(" so ")[0].split(",")[0][:70])  # fmt: skip
        intro = intro_for(need, with_article(noun), r)
        bullets = "\n".join(f"- {q['text']}" for q in requirements)
        deliver = ", ".join(arch["deliverables"])
        desc = f"{intro}\n\nWhat we need:\n{bullets}\n\nDeliverables: {deliver}.\nTimeline: about {r.randint(2, 12)} weeks."
        # generic base skills (python, sql, ...) would give a band for "any python job"
        band = price_band(
            persona["category"], [s for s in chosen if s not in persona["base_skills"]], pay_type
        )
        money = budget_for(band, pay_type, persona["floors"], job_type == "low_budget", r)
        screening = r.sample(SCREENING, r.randint(1, 3))

    has_injection = (not is_scam) and r.random() < SHARE_INJECTION
    injection_text = r.choice(INJECTIONS) if has_injection else None
    if injection_text:
        desc = (
            desc.replace("\n\n", f"\n\n{injection_text}\n\n", 1)
            if "\n\n" in desc
            else f"{desc} {injection_text}"
        )

    quality_wanted = {"poor_client": ["poor"], "scam": ["poor", "ok"]}.get(job_type, ["good", "ok"])
    client = r.choice(
        [c for c in clients.values() if c["_gold"]["history_quality"] in quality_wanted]
    )
    job = {
        "title": title,
        "description": desc,
        "category": persona["category"],
        "skills": [q["skill"] for q in requirements if q["phrasing"] == "name"],
        "pay_type": pay_type,
        **money,
        "client_id": client["client_id"],
        "screening_questions": screening,
        "experience_level": r.choice(["Intermediate", "Expert"]),
        "posted_at": iso(REF_NOW - timedelta(minutes=r.randint(10, 5 * 24 * 60))),
        "requirements": requirements,
    }
    job["connects_required"] = connects_cost(pay_type, job["budget_usd"], job["hourly_high"])
    decision, reason = bid_rule(job, persona_skills, persona["floors"],
                                client["_gold"]["history_quality"], is_scam)  # fmt: skip
    expected = ("bid", None) if job_type == "bid" else ("skip", job_type)
    assert (decision, reason) == expected, (job_type, decision, reason)

    gold_ids = gold_evidence(anchors, r) if anchors else []
    anchor_arch = {p["archetype"] for p in anchors}
    related = sorted(
        e["id"]
        for p in projects
        if p["archetype"] in anchor_arch and p not in anchors
        for e in p["evidence_items"]
        if e["type"] == "case_study"
    )
    job["_gold"] = {
        "persona": pid,
        "job_type": job_type,
        "bid": decision,
        "skip_reason": reason,
        "is_scam": is_scam,
        "scam_type": scam_type,
        "risk_flags": (list(SCAMS[scam_type]["flags"]) if is_scam else []) + (["injection"] if has_injection else []),
        "has_injection": has_injection,
        "injection_text": injection_text,
        "evidence_ids": gold_ids,
        "related_evidence_ids": related,
        "anchor_project_ids": [p["project_id"] for p in anchors],
        "price_band": {"pay_type": pay_type, "low": band["low"], "high": band["high"], "source": band["source"]},
        "client_quality": client["_gold"]["history_quality"],
    }  # fmt: skip
    return stamp(job, PROV)


def load_persona(pid: str, root: Path) -> tuple[dict, list[dict]]:
    profile = json.loads((root / pid / "profile.json").read_text(encoding="utf-8"))
    projects = json.loads((root / pid / "_meta" / "projects.json").read_text(encoding="utf-8"))
    evidence = {e["id"]: e for e in read_jsonl(root / pid / "evidence.jsonl")}
    for p in projects:
        p["evidence_items"] = [evidence[i] for i in p["evidence"]]
    return profile, projects


def generate(personas_root: Path = PERSONAS, dev_root: Path = DEVSET, heldout_root: Path = HELDOUT,
             clients_path: Path = SYNTHETIC / "clients.jsonl") -> dict:  # fmt: skip
    clients = {c["client_id"]: c for c in read_jsonl(clients_path)}
    summary = {}
    for pid, persona in specs()["personas"].items():
        r = rng(f"devset:{pid}")
        profile, projects = load_persona(pid, personas_root)
        n_types = {k: round(v * N_PER_PERSONA) for k, v in JOB_TYPES.items()}
        n_types["bid"] += N_PER_PERSONA - sum(n_types.values())
        types = [t for t, n in sorted(n_types.items()) for _ in range(n)]
        r.shuffle(types)
        jobs = [build_job(pid, persona, profile, projects, clients, t, r) for t in types]
        for j in jobs:
            j["job_id"] = f"gj_{r.getrandbits(40):010x}"
        dev, test = jobs[:N_DEV], jobs[N_DEV:]
        write_jsonl(dev_root / f"{pid}.jsonl", dev)
        write_jsonl(heldout_root / f"{pid}.jsonl", test)
        summary[pid] = {
            "dev": len(dev),
            "test": len(test),
            "dev_bid": sum(j["_gold"]["bid"] == "bid" for j in dev),
            "dev_scam": sum(j["_gold"]["is_scam"] for j in dev),
            "dev_injection": sum(j["_gold"]["has_injection"] for j in dev),
            "dev_with_gold_evidence": sum(bool(j["_gold"]["evidence_ids"]) for j in dev),
        }
    return summary


def main() -> None:
    for pid, s in generate().items():
        print(pid, s)


if __name__ == "__main__":
    main()
