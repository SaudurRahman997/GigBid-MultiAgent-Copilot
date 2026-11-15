"""Needs `make up`: GigSim in Docker on Postgres behaves like the unit-tested app."""

import json
import urllib.error
import urllib.request
import uuid

import pytest

pytestmark = pytest.mark.integration
BASE = "http://localhost:8100"
H = {"Authorization": "Bearer dev-token-data-analyst"}


def call(
    method: str, path: str, body: dict | None = None, headers: dict | None = None, tries: int = 6
):
    """HTTP call that retries simulated 5xx (the service injects them on purpose)."""
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(tries):
        req = urllib.request.Request(
            BASE + path,
            data=data,
            method=method,
            headers={**H, "Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read()), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return e.code, json.loads(e.read() or b"{}"), dict(e.headers)
    raise AssertionError(f"{method} {path}: still failing after {tries} tries")


def test_health_and_hidden_gold():
    with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
        assert r.status == 200
    status, page, _ = call("GET", "/jobs?limit=20")
    assert status == 200 and page["items"] and all("_gold" not in j for j in page["items"])


def test_submit_is_idempotent_on_postgres():
    _, page, _ = call("GET", "/jobs?category=data_analysis&limit=50")
    job = page["items"][hash(uuid.uuid4()) % len(page["items"])]
    status, draft, _ = call(
        "POST",
        "/proposals",
        {
            "job_id": job["job_id"],
            "bid_amount": 30,
            "cover_letter": "I build Power BI dashboards and SQL models.",
        },
    )
    assert status == 201
    _, before, _ = call("GET", "/me/connects")
    key = {"Idempotency-Key": f"it-{uuid.uuid4()}"}
    results = [
        call("POST", f"/proposals/{draft['proposal_id']}/submit", headers=key) for _ in range(3)
    ]
    if results[0][0] == 402:
        pytest.skip("reviewer balance exhausted on this long-running dev database")
    assert all(r[0] == 200 for r in results) and results[0][1] == results[2][1]
    _, after, _ = call("GET", "/me/connects")
    assert after["balance"] == before["balance"] - draft["connects_cost"]
