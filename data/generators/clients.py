"""Generate ~500 synthetic clients (data/synthetic/clients.jsonl).

Public fields (what a marketplace shows) are sampled from REAL distributions in
data/processed/client_priors.json: total spend, rating, review count, payment verification,
country. Contracts in the Kaggle data carry no client id, so per-client histories are
synthesised from per-contract distributions (contract value, hourly rate).

Hidden fields live under "_hidden" (GigSim's simulated client uses them; agents never see them):
  must_have_strictness, budget_ceiling_multiplier, dislikes_generic_opening,
  values_specific_evidence, responsiveness_hours, reply_propensity.
"_gold.history_quality" is the label used by the bid/skip rule (see DATA_CARD):
  poor  if rating < 4.0, or >= 5 jobs posted with hire rate < 0.2,
        or payment unverified with >= 10 jobs posted and $0 spent
  good  if payment verified, spent >= $1,000 and rating >= 4.7
  ok    otherwise
"""

from __future__ import annotations

import math
import random
from datetime import timedelta
from pathlib import Path

from data.generators.common import (
    REF_NOW,
    SYNTHETIC,
    client_priors,
    iso,
    provenance,
    rng,
    sample_quantile,
    specs,
    stamp,
    weighted_choice,
    write_jsonl,
)

PROV = provenance(__file__)
N_CLIENTS = 500
POOR_RATING = 4.0
NAME_A = ["Blue", "North", "Bright", "Silver", "Oak", "Summit", "Harbor", "Clear", "True", "Swift",
          "Maple", "Copper", "Lumen", "Pioneer", "Atlas", "Cobalt", "Willow", "Granite", "Nova", "Vista"]  # fmt: skip
NAME_B = ["Labs", "Works", "Digital", "Partners", "Studio", "Group", "Ventures", "Systems",
          "Collective", "Co", "Analytics", "Health", "Retail", "Logistics", "Media", "Capital"]  # fmt: skip


def history_quality(c: dict) -> str:
    if c["rating"] is not None and c["rating"] < POOR_RATING:
        return "poor"
    if c["jobs_posted"] >= 5 and c["hire_rate"] < 0.2:
        return "poor"
    if not c["payment_verified"] and c["jobs_posted"] >= 10 and c["total_spent_usd"] == 0:
        return "poor"
    if c["payment_verified"] and c["total_spent_usd"] >= 1000 and (c["rating"] or 0) >= 4.7:
        return "good"
    return "ok"


def make_client(i: int, r: random.Random) -> dict:
    pri = client_priors()
    levels = pri["quantile_levels"]
    j = pri["jobs_60k"]
    spent = (
        0.0
        if r.random() < j["share_spent_zero"]
        else sample_quantile(j["client_spent_usd"], levels, r)
    )
    spent = round(min(spent, 2_000_000.0), -1 if spent > 100 else 0)
    verified = r.random() < (j["share_payment_verified"] + (0.25 if spent > 0 else -0.25))
    if spent == 0:
        hires, feedback = 0, 0
        jobs_posted = r.choice([0, 0, 0, 1, 1, 1, 2, 2, 3, 4, 6, 9, 12])
        rating = None
    else:
        feedback = max(1, int(round(sample_quantile(j["client_feedback_count"], levels, r))))
        hires = max(feedback, int(round(feedback * r.uniform(1.0, 1.4))))
        hire_rate_target = min(0.95, max(0.05, r.betavariate(4, 3)))
        jobs_posted = max(hires, int(math.ceil(hires / hire_rate_target)))
        rating = round(sample_quantile(j["client_rating"], levels, r), 2)
    hire_rate = round(hires / jobs_posted, 2) if jobs_posted else 0.0
    countries = pri["country_share_top30"]
    contracts = pri["contracts"]
    history = []
    for _ in range(min(hires, 5)):
        paid = round(sample_quantile(contracts["total_paid_usd"], levels, r), 2)
        history.append(
            {"paid_usd": paid, "feedback_given": round(r.choice([5, 5, 5, 4.8, 4.5, 4, 3]), 1)}
        )
    ind = r.choice(sorted(specs()["industries"]) + ["other"])
    client = {
        "client_id": f"cl_{i:04d}",
        "name": f"{r.choice(NAME_A)} {r.choice(NAME_B)}",
        "country": weighted_choice(r, countries),
        "industry": ind,
        "member_since": iso(REF_NOW - timedelta(days=r.randint(30, 9 * 365))),
        "payment_verified": verified,
        "total_spent_usd": spent,
        "rating": rating,
        "feedback_count": feedback,
        "hires": hires,
        "jobs_posted": jobs_posted,
        "hire_rate": hire_rate,
        "avg_hourly_rate_paid_usd": round(
            sample_quantile(contracts["hourly_rate_usd"], levels, r), 2
        )
        if hires
        else None,
        "recent_contracts": history,
    }
    client["_hidden"] = {
        "must_have_strictness": round(r.uniform(0.3, 1.0), 2),
        "budget_ceiling_multiplier": round(r.uniform(0.9, 1.5), 2),
        "dislikes_generic_opening": r.random() < 0.6,
        "values_specific_evidence": r.random() < 0.7,
        "responsiveness_hours": round(min(96.0, r.lognormvariate(2.3, 0.9)), 1),
        "reply_propensity": round(r.betavariate(3, 4), 2),
    }
    client["_gold"] = {"history_quality": history_quality(client)}
    return stamp(client, PROV)


def generate(out: Path = SYNTHETIC / "clients.jsonl") -> list[dict]:
    r = rng("clients")
    clients = [make_client(i, r) for i in range(1, N_CLIENTS + 1)]
    write_jsonl(out, clients)
    return clients


def main() -> None:
    clients = generate()
    q = [c["_gold"]["history_quality"] for c in clients]
    print({k: q.count(k) for k in ("good", "ok", "poor")}, "clients:", len(clients))


if __name__ == "__main__":
    main()
