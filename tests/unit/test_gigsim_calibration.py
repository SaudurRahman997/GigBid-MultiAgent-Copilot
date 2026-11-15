"""The simulated client must reward tailored, evidence-backed proposals over generic ones."""

import json
import statistics
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import update

from gigsim import db
from gigsim.app import create_app
from tests.unit.test_gigsim import ADMIN, H, make_settings

GENERIC = (
    "Dear Hiring Manager, I am very interested in your job posting. "
    "I am the perfect fit and can start immediately."
)
ANSWERED = {"replied", "interview", "hired"}


def replied(decisions: list[dict]) -> float:
    return sum(d["outcome"] in ANSWERED for d in decisions) / len(decisions)


def test_tailored_proposals_beat_generic(tmp_path):
    lines = Path("data/devset/ai_ml.jsonl").read_text(encoding="utf-8").split("\n")
    jobs = [j for j in (json.loads(x) for x in lines if x) if j["_gold"]["bid"] == "bid"][:30]
    with TestClient(create_app(make_settings(tmp_path))) as c:
        with c.app.state.engine.begin() as conn:
            conn.execute(update(db.users).values(connects=100_000))
        for i, j in enumerate(jobs):
            must = [r["skill"] for r in j["requirements"] if r["must_have"]]
            price = j["budget_usd"] or j["hourly_low"]
            good = (
                f"You need help with {j['title'].lower()}. I built a similar system using "
                f"{', '.join(must)} for a client and we cut processing time by 45%. "
                "Here is how I would approach your project, step by step."
            )
            for kind, letter in (("good", good), ("generic", GENERIC)):
                body = {"job_id": j["job_id"], "cover_letter": letter, "bid_amount": price}
                p = c.post("/proposals", headers=H, json=body).json()
                key = {**H, "Idempotency-Key": f"{kind}{i}"}
                c.post(f"/proposals/{p['proposal_id']}/submit", headers=key)
        dec = c.get("/admin/decisions", headers=ADMIN).json()["items"]
    good, generic = dec[0::2], dec[1::2]
    p_good = statistics.mean(d["features"]["p"] for d in good)
    p_generic = statistics.mean(d["features"]["p"] for d in generic)
    assert p_good - p_generic > 0.3
    assert replied(good) > replied(generic) + 0.2
    assert replied(generic) < 0.25  # generic spam rarely gets answers
    assert replied(good) < 0.9  # but nothing is guaranteed
