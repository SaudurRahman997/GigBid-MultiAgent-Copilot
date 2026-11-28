"""Marketplace outage: other servers keep working, the run halts, and it finishes exactly once
after recovery, from the checkpoint before the failed node."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.marketplace_port import load_config
from agent.mcp_client import GigBidMCPClient, MarketplaceDegraded, PendingQueue
from apps.api import db
from apps.api.service import GraphService
from evals.inprocess_mcp import FakeMCP
from tests.unit.test_mcp_http import TOKEN, connections, free_port, stack  # noqa: F401

pytestmark = pytest.mark.anyio
USER = {"id": "u_test", "persona": "ai_ml", "email": "t@example.com"}
BID_JOB = "gj_16671e658f"


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_unreachable_marketplace_leaves_other_servers_working(stack, tmp_path):  # noqa: F811
    down = {**stack.urls, "marketplace": f"http://127.0.0.1:{free_port()}/mcp"}
    client = GigBidMCPClient(TOKEN, connections=connections(down))
    client.queue = PendingQueue(tmp_path / "queue.jsonl")
    found = await client.call("writer", "search_evidence", {"requirement": "Python", "k": 2})
    assert found["items"]
    with pytest.raises(MarketplaceDegraded) as exc:
        await client.call("scout", "get_job", {"job_id": BID_JOB})
    assert "marketplace" in exc.value.reason
    assert client.queue.pending() == []  # a read is not queued
    with pytest.raises(MarketplaceDegraded):
        await client.call(
            "submitter", "submit_proposal", {"proposal_id": "p", "idempotency_key": "kkkkkkkk"}
        )
    assert [r["tool"] for r in client.queue.pending()] == ["submit_proposal"]


class FlakyMarketplace(FakeMCP):
    """FakeMCP whose tools in `broken` raise as if the marketplace were down."""

    broken: set[str] = set()

    async def call(self, agent, tool, args):
        if tool in self.broken and not args.get("dry_run"):
            raise MarketplaceDegraded(tool, args, "connection refused")
        return await super().call(agent, tool, args)

    async def health(self):
        return {"marketplace": not self.broken}


def service(mcp: FlakyMarketplace) -> GraphService:
    return GraphService(
        db.make_engine("sqlite://"),
        load_config(),
        lambda persona, trace: mcp,
        checkpointer=InMemorySaver(),
        store=InMemoryStore(),
        inline=True,
    )


async def test_approved_proposal_is_submitted_once_after_the_marketplace_returns():
    mcp = FlakyMarketplace("ai_ml")
    svc = service(mcp)
    thread = await svc.start(USER, "bid", BID_JOB)
    mcp.broken = {"create_proposal_draft", "submit_proposal"}
    await svc.resume(USER, thread, {"action": "approve"})
    halted = await svc.state(USER, thread)
    assert halted["status"] == "needs_attention"
    assert halted["state"]["attention_reason"].startswith("marketplace degraded")
    assert mcp.submits == 0

    assert await svc.recover_degraded(lambda _: USER) == 0  # still down: wait
    mcp.broken = set()
    assert await svc.recover_degraded(lambda _: USER) == 1
    done = await svc.state(USER, thread)
    assert done["status"] == "submitted"
    assert done["state"]["submission"]["idempotency_key"] == f"{thread}:submit:v1"
    assert mcp.submits == 1
    assert await svc.recover_degraded(lambda _: USER) == 0  # nothing left to recover
    assert mcp.submits == 1


async def test_recovery_never_sends_without_a_recorded_approval():
    mcp = FlakyMarketplace("ai_ml")
    svc = service(mcp)
    mcp.broken = {"get_client_history"}  # fails during analysis, before any approval
    thread = await svc.start(USER, "bid", BID_JOB)
    assert (await svc.state(USER, thread))["status"] == "needs_attention"
    mcp.broken = set()
    assert await svc.recover_degraded(lambda _: USER) == 1
    assert (await svc.state(USER, thread))["status"] == "awaiting_approval"
    assert mcp.submits == 0
