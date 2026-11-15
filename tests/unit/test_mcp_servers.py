"""In-memory MCP client tests for the Portfolio, Marketplace and Workspace servers.

The marketplace server talks to a real GigSim app in-process (httpx ASGITransport, SQLite).
"""

from __future__ import annotations

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from agent.mcp_client import strip_sdk_prefix
from gigsim.app import create_app as create_gigsim
from gigsim.settings import Settings as GigSimSettings
from mcp_servers.common.settings import MCPSettings
from mcp_servers.common.store import Store
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.marketplace.server import build_server as build_marketplace
from mcp_servers.portfolio.server import build_server as build_portfolio
from mcp_servers.workspace.server import build_server as build_workspace
from mcp_servers.workspace.server import ws_metadata

pytestmark = pytest.mark.anyio
LETTER = (
    "You need a chatbot over your internal PDFs. I built a retrieval pipeline with LangChain and "
    "the OpenAI API for a law firm and we cut lookup time from 20 minutes to 5 seconds."
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def settings(tmp_path, user="ai_ml", **kw) -> MCPSettings:
    return MCPSettings(database_url=f"sqlite:///{tmp_path / 'mcp.db'}", dev_user=user, **kw)


async def call(session, tool: str, args: dict | None = None):
    res = await session.call_tool(tool, args or {})
    return res


def ok(res) -> dict:
    assert not res.isError, res.content
    return res.structuredContent


def err(res) -> str:
    """Error text with the SDK's 'Error executing tool X: ' prefix removed."""
    assert res.isError, res.structuredContent
    return strip_sdk_prefix(" ".join(c.text for c in res.content))


# ----------------------------------------------------------------------------- portfolio


async def test_portfolio_search_get_and_skills(tmp_path):
    async with connect(build_portfolio(settings(tmp_path))) as s:
        out = ok(
            await call(
                s, "search_evidence", {"requirement": "predict which customers will cancel", "k": 5}
            )
        )
        assert out["items"] and out["variant"]
        assert all(i["id"].startswith("ai_ml:") for i in out["items"])
        cases = ok(
            await call(
                s,
                "search_evidence",
                {"requirement": "churn model retention", "filters": {"types": ["case_study"]}},
            )
        )["items"]
        case = cases[0]
        assert all(c["type"] == "case_study" for c in cases)
        full = ok(await call(s, "get_case_study", {"id": case["id"]}))
        assert full["text"] and full["id"] == case["id"]
        skills = ok(await call(s, "list_skills"))["skills"]
        assert skills and skills[0]["evidence_count"] >= skills[-1]["evidence_count"]


async def test_portfolio_filters(tmp_path):
    async with connect(build_portfolio(settings(tmp_path))) as s:
        f = {"types": ["proposal"], "outcomes": ["won"]}
        out = ok(
            await call(
                s, "search_evidence", {"requirement": "retrieval pipeline", "k": 5, "filters": f}
            )
        )
        assert out["items"] and all(
            i["type"] == "proposal" and i["outcome"] == "won" for i in out["items"]
        )


async def test_portfolio_input_validation(tmp_path):
    async with connect(build_portfolio(settings(tmp_path))) as s:
        assert (await call(s, "search_evidence", {"requirement": "x"})).isError
        assert (await call(s, "search_evidence", {"requirement": "python", "k": 99})).isError


async def test_portfolio_tenant_isolation(tmp_path):
    async with connect(build_portfolio(settings(tmp_path, user="fullstack"))) as s:
        msg = err(await call(s, "get_case_study", {"id": "ai_ml:case:01"}))
        assert msg.startswith("not_found")


async def test_portfolio_resources_and_prompts(tmp_path):
    async with connect(build_portfolio(settings(tmp_path))) as s:
        templates = {t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates}
        assert templates == {
            "portfolio://case/{id}",
            "portfolio://proposal/{id}",
            "portfolio://repo/{name}",
        }
        case = await s.read_resource("portfolio://case/ai_ml:case:01")
        assert case.contents[0].text.startswith("#")
        prop = await s.read_resource("portfolio://proposal/ai_ml:proposal:001")
        assert prop.contents[0].text.startswith("Outcome:")
        readme = await s.read_resource("portfolio://repo/doc-qa-service")
        assert "## Stack" in readme.contents[0].text
        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert prompts == {
            "answer_screening_question",
            "summarise_experience",
            "cover_letter_opening",
        }
        p = await s.get_prompt("cover_letter_opening", {"job": "Need a RAG chatbot"})
        assert (
            "UNTRUSTED" in p.messages[0].content.text
            and "Need a RAG chatbot" in p.messages[0].content.text
        )


async def test_portfolio_audits_every_call(tmp_path):
    srv = build_portfolio(settings(tmp_path))
    async with connect(srv) as s:
        await call(s, "list_skills")
        await call(s, "get_case_study", {"id": "nope:case:99"})
    rows = srv.store.audit_rows("ai_ml")
    assert [r["tool"] for r in rows] == ["list_skills", "get_case_study"]
    assert [r["status"] for r in rows] == ["ok", "error"] and all(r["trace_id"] for r in rows)


# ----------------------------------------------------------------------------- marketplace


@pytest.fixture
def gigsim(tmp_path):
    def make(**kw):
        base = {
            "database_url": f"sqlite:///{tmp_path / 'gigsim.db'}",
            "error_rate": 0.0,
            "time_scale": 0.0,
            "include_heldout": False,
            "rate_limit_per_min": 100_000,
            "release_interval_min": 10_000,
        }
        return create_gigsim(GigSimSettings(**{**base, **kw}))

    return make


def marketplace(tmp_path, app, **kw):
    s = settings(tmp_path, **kw)
    adapter = GigSimAdapter(
        s,
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gigsim"
        ),
        backoff_base_s=0.0,
    )
    return build_marketplace(s, adapter=adapter, store=Store(s.database_url))


async def a_job(s, query="chatbot internal PDFs") -> dict:
    return ok(await call(s, "search_jobs", {"query": query, "limit": 1}))["items"][0]


async def test_marketplace_reads(tmp_path, gigsim):
    async with connect(marketplace(tmp_path, gigsim())) as s:
        page = ok(await call(s, "search_jobs", {"category": "ai_ml", "limit": 3}))
        assert page["total"] > 0 and len(page["items"]) == 3
        job = ok(await call(s, "get_job", {"job_id": page["items"][0]["job_id"]}))
        assert job["description"]
        hist = ok(await call(s, "get_client_history", {"client_id": job["client_id"]}))
        assert hist["client_id"] == job["client_id"] and "_hidden" not in hist
        assert ok(await call(s, "get_connects_balance"))["balance"] == 120
        threads = ok(await call(s, "list_messages"))["threads"]
        msgs = ok(await call(s, "list_messages", {"thread_id": threads[0]["thread_id"]}))[
            "messages"
        ]
        assert threads and msgs


async def test_draft_dry_run_previews_without_creating(tmp_path, gigsim):
    async with connect(marketplace(tmp_path, gigsim())) as s:
        job = await a_job(s)
        args = {
            "job_id": job["job_id"],
            "cover_letter": LETTER,
            "bid_amount": 40.0,
            "idempotency_key": "draft:test:1",
            "dry_run": True,
        }
        prev = ok(await call(s, "create_proposal_draft", args))
        assert (
            prev["dry_run"]
            and prev["proposal_id"] is None
            and prev["connects_cost"] == job["connects_required"]
        )
        assert prev["would_send"]["cover_letter"] == LETTER
        real = ok(await call(s, "create_proposal_draft", {**args, "dry_run": False}))
        assert real["proposal_id"] == "pr_000001"  # the dry run created nothing


async def test_draft_idempotency_replay_and_conflict(tmp_path, gigsim):
    async with connect(marketplace(tmp_path, gigsim())) as s:
        job = await a_job(s)
        args = {
            "job_id": job["job_id"],
            "cover_letter": LETTER,
            "bid_amount": 40.0,
            "idempotency_key": "draft:k:1",
        }
        first = ok(await call(s, "create_proposal_draft", args))
        again = ok(await call(s, "create_proposal_draft", args))
        assert (
            again["proposal_id"] == first["proposal_id"]
            and again["replayed"]
            and not first["replayed"]
        )
        clash = err(await call(s, "create_proposal_draft", {**args, "bid_amount": 99.0}))
        assert clash.startswith("idempotency_conflict")


async def test_submit_dry_run_then_exactly_once(tmp_path, gigsim):
    async with connect(marketplace(tmp_path, gigsim())) as s:
        job = await a_job(s)
        d = ok(
            await call(
                s,
                "create_proposal_draft",
                {
                    "job_id": job["job_id"],
                    "cover_letter": LETTER,
                    "bid_amount": 40.0,
                    "idempotency_key": "draft:x:1",
                },
            )
        )
        sub = {"proposal_id": d["proposal_id"], "idempotency_key": "thread-9:v1"}
        prev = ok(await call(s, "submit_proposal", {**sub, "dry_run": True}))
        assert (
            prev["dry_run"]
            and prev["balance_before"] == 120
            and prev["balance_after"] == 120 - d["connects_cost"]
        )
        assert ok(await call(s, "get_connects_balance"))["balance"] == 120  # dry run spent nothing
        r1 = ok(await call(s, "submit_proposal", sub))
        r2 = ok(await call(s, "submit_proposal", sub))
        assert r1["status"] == "submitted" and r2["replayed"]
        assert ok(await call(s, "get_connects_balance"))["balance"] == 120 - d["connects_cost"]


async def test_submit_survives_flaky_gigsim_exactly_once(tmp_path, gigsim):
    app = gigsim()
    async with connect(marketplace(tmp_path, app)) as s:
        job = await a_job(s)
        d = ok(
            await call(
                s,
                "create_proposal_draft",
                {
                    "job_id": job["job_id"],
                    "cover_letter": LETTER,
                    "bid_amount": 40.0,
                    "idempotency_key": "draft:f:1",
                },
            )
        )
    flaky = gigsim(error_rate=0.6, lost_response_share=1.0)  # same DB file, chaos on
    async with connect(marketplace(tmp_path, flaky, gigsim_max_retries=12)) as s:
        r = ok(
            await call(
                s,
                "submit_proposal",
                {"proposal_id": d["proposal_id"], "idempotency_key": "flaky:v1"},
            )
        )
        assert r["status"] == "submitted"
    async with connect(marketplace(tmp_path, gigsim())) as s:
        assert ok(await call(s, "get_connects_balance"))["balance"] == 120 - d["connects_cost"]


async def test_marketplace_down_reports_unavailable(tmp_path, gigsim):
    down = gigsim(error_rate=1.0, lost_response_share=0.0)
    async with connect(marketplace(tmp_path, down, gigsim_max_retries=2)) as s:
        assert err(await call(s, "get_connects_balance")).startswith("marketplace_unavailable")


async def test_policy_violation_is_coded_and_audit_is_masked(tmp_path, gigsim):
    srv = marketplace(tmp_path, gigsim())
    async with connect(srv) as s:
        job = await a_job(s)
        bad = LETTER + " Email me at someone@example.com or call +44 7700 900123."
        msg = err(
            await call(
                s,
                "create_proposal_draft",
                {
                    "job_id": job["job_id"],
                    "cover_letter": bad,
                    "bid_amount": 40.0,
                    "idempotency_key": "draft:bad:1",
                },
            )
        )
        assert msg.startswith("policy_violation")
    row = srv.store.audit_rows("ai_ml")[-1]
    text = str(row["args_masked"])
    assert "someone@example.com" not in text and "[EMAIL]" in text and "[PHONE]" in text
    assert row["status"] == "error"


async def test_marketplace_rate_limit(tmp_path, gigsim):
    async with connect(marketplace(tmp_path, gigsim(), rate_limit_per_min=3)) as s:
        results = [await call(s, "get_connects_balance") for _ in range(4)]
        assert [r.isError for r in results] == [False, False, False, True]
        assert err(results[3]).startswith("rate_limited")


async def test_write_inputs_are_constrained(tmp_path, gigsim):
    async with connect(marketplace(tmp_path, gigsim())) as s:
        job = await a_job(s)
        base = {
            "job_id": job["job_id"],
            "cover_letter": LETTER,
            "bid_amount": 40.0,
            "idempotency_key": "k" * 10,
        }
        assert (
            await call(s, "create_proposal_draft", {**base, "idempotency_key": "short"})
        ).isError
        assert (await call(s, "create_proposal_draft", {**base, "bid_amount": 0})).isError
        assert (
            await call(s, "create_proposal_draft", {**base, "cover_letter": "too short"})
        ).isError
        no_key = {k: v for k, v in base.items() if k != "idempotency_key"}
        assert (await call(s, "create_proposal_draft", no_key)).isError


async def test_send_message_idempotent(tmp_path, gigsim):
    async with connect(marketplace(tmp_path, gigsim())) as s:
        tid = ok(await call(s, "list_messages"))["threads"][0]["thread_id"]
        args = {
            "thread_id": tid,
            "text": "Happy to discuss here on the platform.",
            "idempotency_key": "msg:1:v1",
        }
        assert ok(await call(s, "send_message", {**args, "dry_run": True}))["message_id"] is None
        m1 = ok(await call(s, "send_message", args))
        m2 = ok(await call(s, "send_message", args))
        assert m1["message_id"] == m2["message_id"] and m2["replayed"]
        msgs = ok(await call(s, "list_messages", {"thread_id": tid}))["messages"]
        assert sum(m["text"] == args["text"] for m in msgs) == 1


# ----------------------------------------------------------------------------- workspace


def workspace(tmp_path, user="ai_ml"):
    s = settings(tmp_path, user=user)
    return build_workspace(s, store=Store(s.database_url, extra_metadata=[ws_metadata]))


async def test_workspace_slots_holds_and_drafts(tmp_path):
    async with connect(workspace(tmp_path)) as s:
        week = {"start": "2026-11-02T00:00:00Z", "end": "2026-11-06T23:00:00Z", "duration_min": 30}
        slots = ok(await call(s, "free_slots", week))["slots"]
        assert slots and all("T" in x["start"] for x in slots)
        first = slots[0]
        hold = {
            "start": first["start"],
            "duration_min": 30,
            "title": "Interview",
            "idempotency_key": "hold:1:v1",
        }
        assert (
            ok(await call(s, "create_tentative_hold", {**hold, "dry_run": True}))["hold_id"] is None
        )
        h1 = ok(await call(s, "create_tentative_hold", hold))
        h2 = ok(await call(s, "create_tentative_hold", hold))
        assert h1["hold_id"] == h2["hold_id"] and h2["replayed"]
        clash = err(
            await call(s, "create_tentative_hold", {**hold, "idempotency_key": "hold:2:v1"})
        )
        assert clash.startswith("slot_unavailable")
        after = ok(await call(s, "free_slots", week))["slots"]
        assert first not in after
        d = ok(
            await call(
                s,
                "create_email_draft",
                {
                    "to": "me@example.com",
                    "subject": "Notes",
                    "body": "Prep",
                    "idempotency_key": "mail:1:v1",
                },
            )
        )
        assert d["status"] == "draft" and d["draft_id"]
        assert (
            await call(
                s, "free_slots", {"start": "2026-11-02T00:00:00Z", "end": "2026-12-30T00:00:00Z"}
            )
        ).isError
