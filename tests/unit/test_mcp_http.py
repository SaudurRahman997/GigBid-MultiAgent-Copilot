"""MCP over real Streamable HTTP: bearer auth, langchain-mcp-adapters client, allowlists,
retries and degraded mode. Servers run in-process with uvicorn on free ports (no Docker)."""

from __future__ import annotations

import socket
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from mcp.types import CallToolResult, TextContent

from agent.mcp_client import (
    GigBidMCPClient,
    MarketplaceDegraded,
    PendingQueue,
    RetryInterceptor,
    ToolNotAllowed,
)
from gigsim.app import create_app as create_gigsim
from gigsim.settings import Settings as GigSimSettings
from mcp_servers.common.settings import MCPSettings
from mcp_servers.common.store import Store
from mcp_servers.marketplace.server import build_server as build_marketplace
from mcp_servers.portfolio.server import build_server as build_portfolio
from mcp_servers.workspace.server import build_server as build_workspace
from mcp_servers.workspace.server import ws_metadata

pytestmark = pytest.mark.anyio
TOKEN = "dev-mcp-ai-ml"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(app) -> tuple[str, uvicorn.Server]:
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("http")
    gs = GigSimSettings(
        database_url=f"sqlite:///{tmp / 'gigsim.db'}",
        error_rate=0.0,
        time_scale=0.0,
        include_heldout=False,
        rate_limit_per_min=100_000,
        release_interval_min=10_000,
    )
    gigsim_url, g = serve(create_gigsim(gs))
    s = MCPSettings(database_url=f"sqlite:///{tmp / 'mcp.db'}", gigsim_url=gigsim_url)
    store = Store(s.database_url, extra_metadata=[ws_metadata])
    servers = {
        "portfolio": build_portfolio(s, store=store),
        "marketplace": build_marketplace(s, store=store),
        "workspace": build_workspace(s, store=store),
    }
    urls, running = {}, [g]
    for name, mcp in servers.items():
        base, srv = serve(mcp.streamable_http_app())
        urls[name] = base + "/mcp"
        running.append(srv)
    yield SimpleNamespace(urls=urls, store=store)
    for srv in running:
        srv.should_exit = True


def connections(urls: dict, token: str = TOKEN) -> dict:
    return {
        n: {
            "transport": "streamable_http",
            "url": u,
            "timeout": 20.0,
            "headers": {"Authorization": f"Bearer {token}"},
        }
        for n, u in urls.items()
    }


def test_http_requires_bearer_token(stack):
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    }
    hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    for url in stack.urls.values():
        assert httpx.post(url, json=init, headers=hdr).status_code == 401
        assert (
            httpx.post(url, json=init, headers={**hdr, "Authorization": "Bearer wrong"}).status_code
            == 401
        )
        ok = httpx.post(url, json=init, headers={**hdr, "Authorization": f"Bearer {TOKEN}"})
        assert ok.status_code == 200


async def test_allowlists_filter_tools(stack):
    c = GigBidMCPClient(TOKEN, connections=connections(stack.urls))
    assert {t.name for t in await c.tools_for("scout")} == {"search_jobs", "get_job"}
    assert {t.name for t in await c.tools_for("critic")} == set()
    writer = {t.name for t in await c.tools_for("writer")}
    assert writer == {"search_evidence", "get_case_study"}
    assert "submit_proposal" not in writer
    with pytest.raises(ToolNotAllowed):
        await c.tools_for("nobody")
    with pytest.raises(ToolNotAllowed):
        await c.call(
            "scout", "submit_proposal", {"proposal_id": "x", "idempotency_key": "kkkkkkkk"}
        )


async def test_tool_calls_over_http_are_audited_with_trace_id(stack):
    c = GigBidMCPClient(TOKEN, connections=connections(stack.urls), trace_id="trace-abc-123")
    out = await c.call("scout", "search_jobs", {"category": "ai_ml", "limit": 2})
    assert out  # langchain tool returns the tool's content
    ev = await c.call("writer", "search_evidence", {"requirement": "Power BI dashboard", "k": 3})
    assert ev
    rows = [r for r in stack.store.audit_rows("ai_ml") if r["trace_id"] == "trace-abc-123"]
    assert {r["tool"] for r in rows} >= {"search_jobs", "search_evidence"}
    assert {r["server"] for r in rows} >= {"marketplace", "portfolio"}


# ----------------------------------------------------------------------------- retry / degraded


def result(text: str | None) -> CallToolResult:
    if text is None:
        return CallToolResult(content=[TextContent(type="text", text="ok")], isError=False)
    return CallToolResult(
        content=[TextContent(type="text", text=f"Error executing tool x: {text}")], isError=True
    )


def request(server: str = "marketplace", name: str = "get_job"):
    return SimpleNamespace(
        name=name,
        args={"job_id": "j"},
        server_name=server,
        headers=None,
        override=lambda **kw: SimpleNamespace(
            name=name, args={"job_id": "j"}, server_name=server, headers=kw.get("headers")
        ),
    )


async def test_retry_interceptor_backs_off_then_succeeds():
    sleeps: list[float] = []

    async def sleep(s):
        sleeps.append(s)

    outcomes = iter(
        [
            result("rate_limited: retry after 2s"),
            result("marketplace_unavailable: GigSim 503"),
            result(None),
        ]
    )
    seen_headers = []

    async def handler(req):
        seen_headers.append(req.headers)
        return next(outcomes)

    r = RetryInterceptor(max_attempts=3, base_s=0.5, sleep=sleep, trace_id="t1")
    out = await r(request(), handler)
    assert not out.isError and sleeps == [0.5, 1.0]
    assert all(h["X-Trace-Id"] == "t1" for h in seen_headers)


async def test_retry_interceptor_does_not_retry_permanent_errors():
    calls = 0

    async def handler(_):
        nonlocal calls
        calls += 1
        return result("not_found: job x")

    async def sleep(_):
        pass

    out = await RetryInterceptor(max_attempts=3, sleep=sleep)(request(), handler)
    assert out.isError and calls == 1


async def test_marketplace_down_raises_degraded_and_write_is_queued(tmp_path):
    async def handler(_):
        raise httpx.ConnectError("refused")

    async def sleep(_):
        pass

    with pytest.raises(MarketplaceDegraded):
        await RetryInterceptor(max_attempts=2, sleep=sleep)(request(), handler)
    q = PendingQueue(tmp_path / "q.jsonl")
    q.enqueue(
        "submitter", "submit_proposal", {"proposal_id": "p1", "idempotency_key": "th1:v1"}, "t"
    )
    assert q.pending()[0]["args"]["idempotency_key"] == "th1:v1"
    q.clear()
    assert q.pending() == []


async def test_health_reports_down_servers():
    c = GigBidMCPClient(TOKEN, connections={})
    c.urls = {"marketplace": f"http://127.0.0.1:{free_port()}/mcp"}
    assert await c.health() == {"marketplace": False}


async def test_call_returns_structured_output_and_coded_errors(stack):
    from agent.mcp_client import ToolCallFailed

    c = GigBidMCPClient(TOKEN, connections=connections(stack.urls))
    page = await c.call("scout", "search_jobs", {"category": "ai_ml", "limit": 2})
    assert isinstance(page, dict) and len(page["items"]) == 2
    with pytest.raises(ToolCallFailed) as exc:
        await c.call("scout", "get_job", {"job_id": "does-not-exist"})
    assert exc.value.code == "not_found"
