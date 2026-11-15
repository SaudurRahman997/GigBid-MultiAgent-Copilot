"""GigSim behaviour tests (SQLite, simulated clock frozen: time only moves via /admin/tick)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gigsim.app import create_app
from gigsim.settings import Settings

TOKEN = "dev-token-ai-ml"
H = {"Authorization": f"Bearer {TOKEN}"}
ADMIN = {"Authorization": "Bearer dev-admin-token"}
GOOD_LETTER = (
    "You need a chatbot that answers questions from your internal PDFs with citations. "
    "Last year I built a retrieval pipeline with LangChain, Postgres and the OpenAI API "
    "for a law firm and we cut average lookup time from 20 minutes to under 5 seconds. "
    "Python and FastAPI throughout. "
    "Happy to share a short plan."
)


def make_settings(tmp_path, name="sim.db", **kw) -> Settings:
    base = {
        "database_url": f"sqlite:///{tmp_path / name}",
        "error_rate": 0.0,
        "time_scale": 0.0,
        "include_heldout": False,
        "rate_limit_per_min": 10_000,
        "release_interval_min": 10_000,
    }
    return Settings(**{**base, **kw})


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def first_job(c: TestClient, **params) -> dict:
    r = c.get("/jobs", headers=H, params={"limit": 1, **params})
    assert r.status_code == 200
    return r.json()["items"][0]


def draft(c: TestClient, job_id: str, letter: str = GOOD_LETTER, bid: float = 40.0) -> dict:
    r = c.post(
        "/proposals", headers=H, json={"job_id": job_id, "cover_letter": letter, "bid_amount": bid}
    )
    assert r.status_code == 201, r.text
    return r.json()


# ----------------------------------------------------------------------------- auth + data hiding


def test_requires_bearer_token(client):
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/admin/clock", headers=H).status_code == 401  # user token is not admin


def test_jobs_hide_gold_labels_and_held_back_jobs(client):
    data = client.get("/jobs", headers=H, params={"limit": 200}).json()
    assert data["total"] > 0
    for job in data["items"]:
        assert "_gold" not in job and "requirements" not in job and "release_minute" not in job
    devjob = client.get("/jobs", headers=H, params={"query": "chatbot", "limit": 50}).json()[
        "items"
    ]
    assert devjob


def test_client_history_hides_preferences(client):
    job = first_job(client)
    hist = client.get(f"/clients/{job['client_id']}/history", headers=H).json()
    assert "_hidden" not in hist and "_gold" not in hist and "total_spent_usd" in hist


def test_job_filters(client):
    cat = client.get("/jobs", headers=H, params={"category": "ai_ml", "limit": 20}).json()["items"]
    assert cat and all(j["category"] == "ai_ml" for j in cat)
    q = client.get("/jobs", headers=H, params={"query": "Power BI", "limit": 20}).json()["items"]
    assert all("power" in (j["title"] + j["description"]).lower() for j in q)


# ----------------------------------------------------------------------------- rate limit + chaos


def test_rate_limit_returns_429_with_retry_after(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, rate_limit_per_min=5))) as c:
        codes = [c.get("/policy", headers=H).status_code for _ in range(7)]
        assert codes[:5] == [200] * 5 and codes[5] == 429
        r = c.get("/policy", headers=H)
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        other = {"Authorization": "Bearer dev-token-fullstack"}
        assert c.get("/policy", headers=other).status_code == 200  # per-user buckets


def test_simulated_5xx_at_configured_rate(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, error_rate=0.3))) as c:
        codes = [c.get("/policy", headers=H).status_code for _ in range(400)]
    share = sum(code >= 500 for code in codes) / len(codes)
    assert 0.2 < share < 0.4


# ----------------------------------------------------------------------------- proposals


def test_draft_rejects_contact_details(client):
    job = first_job(client)
    r = client.post(
        "/proposals",
        headers=H,
        json={
            "job_id": job["job_id"],
            "bid_amount": 50,
            "cover_letter": "Email me at me@example.com",
        },
    )
    assert r.status_code == 422 and "email" in r.json()["detail"]["violations"]


def test_draft_validates_input(client):
    job = first_job(client)
    assert (
        client.post(
            "/proposals",
            headers=H,
            json={"job_id": job["job_id"], "bid_amount": -1, "cover_letter": "x"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/proposals",
            headers=H,
            json={"job_id": job["job_id"], "bid_amount": 10, "cover_letter": "x" * 5001},
        ).status_code
        == 422
    )


def test_submit_requires_idempotency_key(client):
    p = draft(client, first_job(client)["job_id"])
    assert client.post(f"/proposals/{p['proposal_id']}/submit", headers=H).status_code == 400


def test_idempotent_submit_charges_once(client):
    p = draft(client, first_job(client)["job_id"])
    before = client.get("/me/connects", headers=H).json()["balance"]
    hk = {**H, "Idempotency-Key": "thread-1:v1"}
    r1 = client.post(f"/proposals/{p['proposal_id']}/submit", headers=hk)
    r2 = client.post(f"/proposals/{p['proposal_id']}/submit", headers=hk)
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json() and r2.headers.get("Idempotent-Replayed") == "true"
    after = client.get("/me/connects", headers=H).json()
    assert after["balance"] == before - p["connects_cost"]
    assert sum(1 for x in after["ledger"] if x["reason"] == "submit_proposal") == 1
    # a different key cannot submit the same proposal twice
    r3 = client.post(
        f"/proposals/{p['proposal_id']}/submit", headers={**H, "Idempotency-Key": "other"}
    )
    assert r3.status_code == 409
    # and a used key cannot be reused for another proposal
    p2 = draft(client, first_job(client, offset=1)["job_id"])
    assert client.post(f"/proposals/{p2['proposal_id']}/submit", headers=hk).status_code == 409


def test_chaos_lost_response_path_processes_submit(tmp_path):
    s = make_settings(tmp_path, error_rate=0.0)
    with TestClient(create_app(s)) as c:
        p = draft(c, first_job(c)["job_id"])
    s_chaos = make_settings(tmp_path, error_rate=1.0, lost_response_share=1.0)  # same DB file
    with TestClient(create_app(s_chaos)) as c:
        hk = {**H, "Idempotency-Key": "chaos-key"}
        r = c.post(f"/proposals/{p['proposal_id']}/submit", headers=hk)
        assert r.status_code == 502  # processed, answer lost
    with TestClient(create_app(make_settings(tmp_path))) as c:
        r = c.post(f"/proposals/{p['proposal_id']}/submit", headers=hk)
        assert r.status_code == 200 and r.headers["Idempotent-Replayed"] == "true"
        assert c.get(f"/proposals/{p['proposal_id']}", headers=H).json()["status"] == "submitted"


def test_insufficient_connects_returns_402(client):
    jobs = client.get("/jobs", headers=H, params={"limit": 60}).json()["items"]
    codes = []
    for i, job in enumerate(jobs):
        p = draft(client, job["job_id"])
        codes.append(
            client.post(
                f"/proposals/{p['proposal_id']}/submit", headers={**H, "Idempotency-Key": f"k{i}"}
            ).status_code
        )
        if codes[-1] == 402:
            break
    assert 402 in codes
    assert client.get("/me/connects", headers=H).json()["balance"] >= 0


# ----------------------------------------------------------------------------- events + clock


def submit_dev_job(c: TestClient, key: str = "ev-1") -> dict:
    job = first_job(c, query="chatbot internal PDFs")
    p = draft(c, job["job_id"], bid=float(job.get("budget_usd") or job.get("hourly_low") or 30))
    r = c.post(f"/proposals/{p['proposal_id']}/submit", headers={**H, "Idempotency-Key": key})
    assert r.status_code == 200, r.text
    return p


def test_events_flow_over_simulated_time(client):
    p = submit_dev_job(client)
    assert client.get("/events", headers=H).json()["items"] == []  # nothing due yet
    client.post("/admin/tick", headers=ADMIN, params={"minutes": 60 * 24 * 30})
    evs = [
        e
        for e in client.get("/events", headers=H).json()["items"]
        if e["proposal_id"] == p["proposal_id"]
    ]
    types = [e["type"] for e in evs]
    assert types and types[-1] in {"hired", "lost"}
    assert types[0] in {"viewed", "lost"}
    times = [e["at"] for e in evs]
    assert times == sorted(times)
    dec = client.get("/admin/decisions", headers=ADMIN).json()["items"]
    assert dec and dec[0]["reasons"] and "coverage" in dec[0]["features"]


def test_events_since_cursor_is_exclusive(client):
    submit_dev_job(client)
    client.post("/admin/tick", headers=ADMIN, params={"minutes": 60 * 24 * 30})
    first = client.get("/events", headers=H).json()
    again = client.get("/events", headers=H, params={"since": first["next_since"]}).json()
    assert first["items"] and again["items"] == []


def test_replied_proposal_opens_thread(client):
    p = submit_dev_job(client)
    client.post("/admin/tick", headers=ADMIN, params={"minutes": 60 * 24 * 30})
    dec = client.get("/admin/decisions", headers=ADMIN).json()["items"][0]
    threads = [
        t
        for t in client.get("/threads", headers=H).json()["items"]
        if t["proposal_id"] == p["proposal_id"]
    ]
    assert bool(threads) == (dec["outcome"] in {"replied", "interview", "hired"})


def test_release_loop_releases_held_back_jobs(client):
    before = client.get("/jobs", headers=H, params={"limit": 1}).json()["total"]
    out = client.post("/admin/tick", headers=ADMIN, params={"minutes": 7 * 24 * 60 + 5000}).json()
    after = client.get("/jobs", headers=H, params={"limit": 1}).json()["total"]
    assert out["released"] > 0 and after == before + out["released"]


def test_seeded_messages_and_send(client):
    threads = client.get("/threads", headers=H).json()["items"]
    assert threads
    tid = threads[0]["thread_id"]
    msgs = client.get(f"/threads/{tid}/messages", headers=H).json()["items"]
    assert msgs and all("_gold" not in m and "gold" not in m for m in msgs)
    ok = client.post(
        f"/threads/{tid}/messages", headers=H, json={"text": "Happy to talk here on the platform."}
    )
    assert ok.status_code == 201
    bad = client.post(
        f"/threads/{tid}/messages", headers=H, json={"text": "WhatsApp me: +1 555 010 9999"}
    )
    assert bad.status_code == 422
    other = {"Authorization": "Bearer dev-token-fullstack"}
    assert client.get(f"/threads/{tid}/messages", headers=other).status_code == 404


# ----------------------------------------------------------------------------- policy versions


def test_policy_v1_vs_v2(tmp_path):
    with (
        TestClient(create_app(make_settings(tmp_path, name="v1.db", policy_version="v1"))) as c1,
        TestClient(create_app(make_settings(tmp_path, name="v2.db", policy_version="v2"))) as c2,
    ):
        assert c1.get("/policy", headers=H).json()["version"] == "v1"
        assert c2.get("/policy", headers=H).json()["proposals"]["external_links_allowed"] is False
        busy = next(
            j
            for j in c1.get("/jobs", headers=H, params={"limit": 200}).json()["items"]
            if j["applicants"] in ("20 to 50", "50+")
        )
        cost1 = draft(c1, busy["job_id"])["connects_cost"]
        cost2 = draft(c2, busy["job_id"])["connects_cost"]
        assert cost2 == min(2 * cost1, 32)
        link = GOOD_LETTER + " See https://example.com/portfolio"
        assert draft(c1, busy["job_id"], letter=link)
        r = c2.post(
            "/proposals",
            headers=H,
            json={"job_id": busy["job_id"], "cover_letter": link, "bid_amount": 40},
        )
        assert r.status_code == 422 and "link" in r.json()["detail"]["violations"]


# ----------------------------------------------------------------------------- determinism


def run_scenario(tmp_path, name: str) -> list:
    with TestClient(create_app(make_settings(tmp_path, name=name))) as c:
        jobs = c.get("/jobs", headers=H, params={"category": "ai_ml", "limit": 8}).json()["items"]
        for i, job in enumerate(jobs):
            p = draft(
                c, job["job_id"], bid=float(job.get("budget_usd") or job.get("hourly_low") or 30)
            )
            c.post(
                f"/proposals/{p['proposal_id']}/submit", headers={**H, "Idempotency-Key": f"d{i}"}
            )
        c.post("/admin/tick", headers=ADMIN, params={"minutes": 60 * 24 * 30})
        events = [
            (e["proposal_id"], e["type"], e["at"])
            for e in c.get("/events", headers=H).json()["items"]
        ]
        decisions = [
            (d["proposal_id"], d["outcome"], d["score"])
            for d in c.get("/admin/decisions", headers=ADMIN).json()["items"]
        ]
    return [events, decisions]


def test_seeded_runs_give_identical_outcomes(tmp_path):
    a, b = run_scenario(tmp_path, "a.db"), run_scenario(tmp_path, "b.db")
    assert a == b and a[0] and a[1]
