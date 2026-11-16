"""API tests: auth, tenant isolation, approval resume (refresh-safe, exactly-once), SSE, settings, memory."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from agent.marketplace_port import load_config
from apps.api import db
from apps.api.main import create_app
from apps.api.service import GraphService
from tests.fakes import FakeMCP

DEV = Path("data/devset/ai_ml.jsonl")


def bid_job() -> str:
    for line in DEV.read_text(encoding="utf-8").split("\n"):
        if line:
            j = json.loads(line)
            if j["_gold"]["job_type"] == "bid" and not j["_gold"].get("has_injection"):
                return j["job_id"]
    raise LookupError


class World:
    def __init__(self):
        self.fakes: dict[str, FakeMCP] = {}
        self.engine = db.make_engine("sqlite://")
        self.svc = GraphService(self.engine, load_config(), self.mcp, checkpointer=InMemorySaver(), store=InMemoryStore())

    def mcp(self, persona: str, trace_id: str) -> FakeMCP:
        return self.fakes.setdefault(persona, FakeMCP(persona))


@pytest.fixture
def world():
    w = World()
    with TestClient(create_app(lambda: w.svc)) as client:
        w.client = client
        yield w


def signup(client: TestClient, email: str, persona: str = "ai_ml") -> dict:
    r = client.post("/auth/register", json={"email": email, "password": "correct-horse", "persona": persona})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def idle(w: World) -> None:
    w.client.portal.call(w.svc.wait_idle)


# ----------------------------------------------------------------------------- auth


def test_register_login_me_and_password_is_hashed(world):
    c = world.client
    signup(c, "a@example.com")
    assert c.post("/auth/register", json={"email": "a@example.com", "password": "correct-horse"}).status_code == 409
    assert c.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"}).status_code == 401
    r = c.post("/auth/login", json={"email": "A@example.com", "password": "correct-horse"})
    assert r.status_code == 200 and "gigbid_session" in r.cookies
    assert c.get("/auth/me").json()["email"] == "a@example.com"  # cookie session
    with world.engine.connect() as conn:
        stored = conn.execute(select(db.users.c.password_hash)).scalar_one()
    assert stored.startswith("scrypt$") and "correct-horse" not in stored


def test_everything_requires_a_session(world):
    c = TestClient(world.client.app)  # no cookie jar from other tests
    for path in ("/auth/me", "/jobs", "/runs", "/approvals", "/settings", "/memory", "/analytics"):
        assert c.get(path).status_code == 401, path


# ----------------------------------------------------------------------------- approvals


def test_analyze_pauses_then_approval_resumes_and_submits_once(world):
    c, h = world.client, signup(world.client, "fl@example.com")
    jobs = c.get("/jobs", headers=h).json()
    assert jobs["items"]
    r = c.post(f"/jobs/{bid_job()}/analyze", headers=h)
    assert r.status_code == 202
    thread = r.json()["thread_id"]
    idle(world)
    pending = c.get("/approvals", headers=h).json()
    assert [p["thread_id"] for p in pending] == [thread]
    req = pending[0]["request"]
    assert req["kind"] == "proposal" and req["dry_run_preview"]["dry_run"] is True
    assert c.get("/approvals", headers=h).json()[0]["request"] == req  # refresh: same request, from the checkpoint
    assert world.fakes["ai_ml"].submits == 0

    assert c.post(f"/approvals/{thread}", headers=h, json={"action": "approve"}).status_code == 202
    idle(world)
    run = c.get(f"/runs/{thread}", headers=h).json()
    assert run["status"] == "submitted" and run["stage"] == "submitted"
    assert run["state"]["submission"]["idempotency_key"] == f"{thread}:submit:v1"
    assert world.fakes["ai_ml"].submits == 1
    assert c.post(f"/approvals/{thread}", headers=h, json={"action": "approve"}).status_code == 409  # no second submit
    assert world.fakes["ai_ml"].submits == 1
    cols = {col["stage"]: col["items"] for col in c.get("/proposals/pipeline", headers=h).json()["columns"]}
    assert [i["thread_id"] for i in cols["submitted"]] == [thread]


def test_reject_needs_reason_and_records_it(world):
    c, h = world.client, signup(world.client, "fl@example.com")
    thread = c.post(f"/jobs/{bid_job()}/analyze", headers=h).json()["thread_id"]
    idle(world)
    assert c.post(f"/approvals/{thread}", headers=h, json={"action": "reject"}).status_code == 422
    assert c.post(f"/approvals/{thread}", headers=h, json={"action": "reject", "reason": "not my niche"}).status_code == 202
    idle(world)
    run = c.get(f"/runs/{thread}", headers=h).json()
    assert run["status"] == "rejected" and "not my niche" in run["state"]["attention_reason"]


def test_tenant_isolation(world):
    c = world.client
    ha, hb = signup(c, "a@example.com"), signup(c, "b@example.com")
    thread = c.post(f"/jobs/{bid_job()}/analyze", headers=ha).json()["thread_id"]
    idle(world)
    assert c.get(f"/runs/{thread}", headers=hb).status_code == 404
    assert c.get(f"/runs/{thread}/events", headers=hb).status_code == 404
    assert c.post(f"/approvals/{thread}", headers=hb, json={"action": "approve"}).status_code == 404
    assert c.get("/approvals", headers=hb).json() == [] and c.get("/runs", headers=hb).json() == []
    assert len(c.get("/approvals", headers=ha).json()) == 1


def test_sse_replays_node_events_and_supports_reconnect(world):
    c, h = world.client, signup(world.client, "fl@example.com")
    thread = c.post(f"/jobs/{bid_job()}/analyze", headers=h).json()["thread_id"]
    idle(world)
    body = c.get(f"/runs/{thread}/events", headers=h).text
    events = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]
    nodes = [i["node"] for e in events if e["type"] == "node" for i in e["items"]]
    assert {"scout_in", "job_analyst", "risk_assessor", "fit_matcher", "decide", "writer"} <= set(nodes)
    assert events[-1]["type"] == "end" and events[-1]["status"] == "awaiting_approval"
    last = events[-2]["id"]
    again = c.get(f"/runs/{thread}/events", headers={**h, "Last-Event-ID": str(last)}).text
    assert [json.loads(x[5:])["type"] for x in again.splitlines() if x.startswith("data:")] == ["end"]


def test_conversation_reply_flow(world):
    c, h = world.client, signup(world.client, "fl@example.com")
    assert c.get("/messages/threads", headers=h).json()["threads"]
    run = c.post("/messages/threads/th_test/reply", headers=h).json()["thread_id"]
    idle(world)
    pending = c.get("/approvals", headers=h).json()
    assert pending[0]["request"]["kind"] == "message"
    c.post(f"/approvals/{run}", headers=h, json={"action": "approve"})
    idle(world)
    assert c.get(f"/runs/{run}", headers=h).json()["stage"] == "interview"
    assert len(world.fakes["ai_ml"].sent) == 1


# ----------------------------------------------------------------------------- settings / memory / analytics


def test_settings_and_encrypted_account_tokens(world):
    c, h = world.client, signup(world.client, "fl@example.com")
    assert c.get("/settings", headers=h).json()["autonomy"] == "approve_each"
    s = {"autonomy": "draft", "daily_connects_budget": 20, "max_tokens_per_thread": 5000,
         "saved_searches": [{"name": "llm", "query": "rag", "every_minutes": 60}]}  # fmt: skip
    assert c.put("/settings", headers=h, json=s).json()["autonomy"] == "draft"
    assert c.put("/settings", headers=h, json={**s, "saved_searches": [{"name": "x", "every_minutes": 5}]}).status_code == 422
    assert c.put("/settings/accounts/upwork", headers=h, json={"access_token": "secret-abc"}).json()["connected"]
    with world.engine.connect() as conn:
        ct = conn.execute(select(db.oauth_tokens.c.ciphertext)).scalar_one()
    assert "secret-abc" not in ct and world.client.app.state.vault.open(ct)["access_token"] == "secret-abc"
    assert "secret-abc" not in c.get("/settings/accounts", headers=h).text
    assert c.delete("/settings/accounts/upwork", headers=h).json()["connected"] is False


def test_memory_viewer_lists_and_deletes(world):
    from agent.memory.store import record_edit

    c, h = world.client, signup(world.client, "fl@example.com")
    uid = c.get("/auth/me", headers=h).json()["id"]
    for t in ("t1", "t2", "t3"):
        record_edit(world.svc.store, uid, t, "Dear Hiring Manager, I can help.", "I can help. Best regards")
    items = c.get("/memory", headers=h).json()
    style = [i for i in items if i["namespace"] == "style"]
    assert style
    assert c.delete(f"/memory/style/{style[0]['key']}", headers=h).status_code == 204
    assert len([i for i in c.get("/memory", headers=h).json() if i["namespace"] == "style"]) == len(style) - 1
    assert c.get("/analytics", headers=h).json()["runs"] == 0


def test_demo_mode_serves_the_full_stack_in_one_process(tmp_path, monkeypatch):
    """GIGBID_MCP_MODE=inprocess (single-process hosting): the real lifespan, no MCP servers."""
    monkeypatch.setenv("GIGBID_MCP_MODE", "inprocess")
    monkeypatch.setenv("API_DATABASE_URL", f"sqlite:///{(tmp_path / 'demo.db').as_posix()}")
    monkeypatch.setenv("REVIEWER_EMAIL", "reviewer@example.com")
    monkeypatch.setenv("REVIEWER_PASSWORD", "demo-pass-123")
    with TestClient(create_app()) as c:
        assert c.get("/health").json()["ok"]
        tok = c.post("/auth/login", json={"email": "reviewer@example.com", "password": "demo-pass-123"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        job = json.loads(next(x for x in (ROOT_DATA / "ai_ml.jsonl").read_text(encoding="utf-8").splitlines()
                              if json.loads(x)["_gold"]["bid"] == "bid"))  # fmt: skip
        tid = c.post(f"/jobs/{job['job_id']}/analyze", headers=h).json()["thread_id"]
        for _ in range(200):  # the run is driven in the background; poll until it settles
            if c.get(f"/runs/{tid}", headers=h).json()["status"] != "running":
                break
            time.sleep(0.1)
        assert c.get(f"/runs/{tid}", headers=h).json()["status"] == "awaiting_approval"
        assert c.get("/approvals", headers=h).json()[0]["thread_id"] == tid


ROOT_DATA = Path(__file__).resolve().parents[2] / "data" / "devset"
