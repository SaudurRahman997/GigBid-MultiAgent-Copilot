"""Agent-side MCP client discipline (the only way agents reach the outside world).

* MultiServerMCPClient over Streamable HTTP to Portfolio, Marketplace and Workspace, with the
  user's bearer token and a propagated X-Trace-Id header.
* Per-agent tool allowlists by name (agent/config.yaml mcp.allowlists): a node only ever sees
  the tools its role needs.
* Timeouts, and bounded retries with exponential backoff for transient errors
  (rate_limited, marketplace_unavailable, timeouts). Writes are safe to retry because every
  write carries an idempotency_key.
* Degraded mode: if the marketplace is unreachable or still failing after retries,
  MarketplaceDegraded is raised and the other servers keep working. The API reports it (UI shows a
  banner) and the run halts; GraphService.recover_degraded restarts it from the checkpoint before
  the failed node once the marketplace is back. PendingQueue keeps a record of deferred writes.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from agent.marketplace_port import load_config

REPO = Path(__file__).resolve().parents[1]


class MarketplaceDegraded(Exception):
    """Marketplace unreachable after retries; caller should report and queue."""

    def __init__(self, tool: str, args: dict, reason: str):
        super().__init__(f"marketplace degraded during {tool}: {reason}")
        self.tool, self.args, self.reason = tool, args, reason


class ToolNotAllowed(Exception):
    pass


class ToolCallFailed(Exception):
    """A tool returned an error result; `code` is the stable prefix (e.g. not_found)."""

    def __init__(self, tool: str, message: str):
        super().__init__(f"{tool}: {message}")
        self.tool, self.message, self.code = tool, message, error_code(message)


SDK_ERROR_PREFIX = re.compile(r"^Error executing tool [^:]+:\s*")


def strip_sdk_prefix(text: str) -> str:
    """'Error executing tool get_job: not_found: ...' -> 'not_found: ...' (code first)."""
    return SDK_ERROR_PREFIX.sub("", text, count=1)


def error_code(text: str) -> str:
    return strip_sdk_prefix(text).split(":", 1)[0].strip()


def _root_cause(exc: BaseException) -> str:
    """The first real error inside the (possibly nested) exception groups the transport raises."""
    while getattr(exc, "exceptions", None):
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = [
        c.get("text", "") if isinstance(c, dict) else getattr(c, "text", "") for c in content or []
    ]
    return " ".join(p for p in parts if p)


def _error_text(result: Any) -> str | None:
    """Error message (SDK prefix removed) if an MCP tool result is an error, else None."""
    if getattr(result, "isError", False):
        parts = [getattr(c, "text", "") for c in getattr(result, "content", []) or []]
        return strip_sdk_prefix(" ".join(p for p in parts if p) or "error")
    return None


@dataclass
class RetryInterceptor:
    """Bounded exponential backoff for transient failures; adds the trace header."""

    max_attempts: int = 3
    base_s: float = 0.5
    max_s: float = 8.0
    transient: tuple[str, ...] = (
        "rate_limited",
        "marketplace_unavailable",
        "timeout",
        "connection",
    )
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    sleep: Any = asyncio.sleep
    attempts_log: list[tuple[str, int]] = field(default_factory=list)

    async def __call__(self, request: MCPToolCallRequest, handler):
        request = request.override(headers={**(request.headers or {}), "X-Trace-Id": self.trace_id})
        last_reason = ""
        for attempt in range(1, self.max_attempts + 1):
            self.attempts_log.append((request.name, attempt))
            try:
                result = await handler(request)
            except (httpx.TransportError, TimeoutError, ConnectionError) as exc:
                last_reason = f"connection: {type(exc).__name__}"
            else:
                err = _error_text(result)
                if err is None or error_code(err) not in self.transient:
                    return result
                last_reason = err
            if attempt < self.max_attempts:
                await self.sleep(min(self.max_s, self.base_s * 2 ** (attempt - 1)))
        if request.server_name == "marketplace":
            raise MarketplaceDegraded(request.name, request.args, last_reason)
        raise RuntimeError(
            f"{request.server_name}.{request.name} failed after retries: {last_reason}"
        )


class PendingQueue:
    """Append-only JSONL queue of marketplace writes deferred during degraded mode."""

    def __init__(self, path: Path):
        self.path = path

    def enqueue(self, agent: str, tool: str, args: dict, trace_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "agent": agent,
            "tool": tool,
            "args": args,
            "trace_id": trace_id,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    def pending(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").split("\n") if x]

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class GigBidMCPClient:
    def __init__(
        self,
        token: str,
        *,
        config: dict | None = None,
        trace_id: str | None = None,
        connections: dict | None = None,
    ):
        self.config = config or load_config()
        m = self.config["mcp"]
        self.token = token
        r = m["retries"]
        self.retry = RetryInterceptor(
            max_attempts=r["max_attempts"],
            base_s=r["backoff_base_s"],
            max_s=r["backoff_max_s"],
            transient=tuple(m["transient_errors"]),
            trace_id=trace_id or uuid.uuid4().hex,
        )
        self.urls = {
            name: os.environ.get(s["url_env"], s["default"]) for name, s in m["servers"].items()
        }
        self.connections = connections or {
            name: {
                "transport": "streamable_http",
                "url": url,
                "timeout": float(m["timeout_s"]),
                "headers": {"Authorization": f"Bearer {token}"},
            }
            for name, url in self.urls.items()
        }
        self.client = MultiServerMCPClient(self.connections, tool_interceptors=[self.retry])
        self.queue = PendingQueue(REPO / m["pending_queue_path"])
        self._tools: list[BaseTool] | None = None
        self.unreachable: dict[str, str] = {}  # server name -> why its tools could not be listed

    @property
    def trace_id(self) -> str:
        return self.retry.trace_id

    async def all_tools(self) -> list[BaseTool]:
        """Tools of every reachable server, listed one server at a time so that one server being
        down never takes the others with it. Only a complete listing is cached."""
        if self._tools is not None:
            return self._tools
        tools: list[BaseTool] = []
        self.unreachable = {}
        for name in self.connections:
            try:
                tools += await self.client.get_tools(server_name=name)
            except Exception as exc:  # noqa: BLE001 - recorded; callers decide what it means
                self.unreachable[name] = _root_cause(exc)
        if not self.unreachable:
            self._tools = tools
        return tools

    async def tools_for(self, agent: str) -> list[BaseTool]:
        """Only the tools on this agent's allowlist (unknown agent -> error, not 'all tools')."""
        allow = self.config["mcp"]["allowlists"].get(agent)
        if allow is None:
            raise ToolNotAllowed(f"no MCP allowlist for agent {agent!r}")
        tools = [t for t in await self.all_tools() if t.name in set(allow)]
        missing = set(allow) - {t.name for t in tools}
        if missing and not self.unreachable:
            raise ToolNotAllowed(f"allowlisted tools not offered by any server: {sorted(missing)}")
        return tools

    async def call(
        self, agent: str, tool: str, args: dict, *, queue_on_degraded: bool = True
    ) -> dict:
        """Call one tool (deterministic nodes), enforcing the allowlist; returns the tool's
        structured output. Error results raise ToolCallFailed (with .code)."""
        tools = {t.name: t for t in await self.tools_for(agent)}
        if tool not in tools:
            if self.unreachable and tool in self.config["mcp"]["allowlists"][agent]:
                self._unavailable(agent, tool, args, queue_on_degraded)
            raise ToolNotAllowed(f"agent {agent!r} may not call {tool!r}")
        try:
            msg = await tools[tool].ainvoke(
                {"type": "tool_call", "id": uuid.uuid4().hex, "name": tool, "args": args}
            )
        except MarketplaceDegraded:
            self._queue_write(agent, tool, args, queue_on_degraded)
            raise
        if getattr(msg, "status", "success") == "error":
            raise ToolCallFailed(tool, strip_sdk_prefix(_content_text(msg.content)))
        artifact = getattr(msg, "artifact", None) or {}
        structured = artifact.get("structured_content") if isinstance(artifact, dict) else None
        if structured is not None:
            return structured
        return json.loads(_content_text(msg.content) or "{}")

    def _queue_write(self, agent: str, tool: str, args: dict, enabled: bool) -> None:
        if enabled and "idempotency_key" in args and not args.get("dry_run"):
            self.queue.enqueue(agent, tool, args, self.trace_id)  # keep a record of the write

    def _unavailable(self, agent: str, tool: str, args: dict, queue_on_degraded: bool) -> None:
        """The tool's server could not be listed. A missing marketplace is degraded mode."""
        reason = "; ".join(f"{n}: {why}" for n, why in sorted(self.unreachable.items()))
        if "marketplace" in self.unreachable:
            self._queue_write(agent, tool, args, queue_on_degraded)
            raise MarketplaceDegraded(tool, args, reason)
        raise RuntimeError(f"tool {tool!r} is unavailable: {reason}")

    async def health(self) -> dict[str, bool]:
        """Server name -> up?  (GET <base>/health; used for the degraded-mode banner)."""
        out = {}
        async with httpx.AsyncClient(timeout=3) as http:
            for name, url in self.urls.items():
                try:
                    out[name] = (
                        await http.get(url.rsplit("/mcp", 1)[0] + "/health")
                    ).status_code == 200
                except httpx.TransportError:
                    out[name] = False
        return out

    async def resume_pending(self, agent: str = "submitter") -> int:
        """Replay queued writes once the marketplace is back (same idempotency keys: safe)."""
        done = 0
        remaining = []
        for row in self.queue.pending():
            try:
                await self.call(
                    row["agent"] or agent, row["tool"], row["args"], queue_on_degraded=False
                )
                done += 1
            except MarketplaceDegraded:
                remaining.append(row)
        self.queue.clear()
        for row in remaining:
            self.queue.enqueue(row["agent"], row["tool"], row["args"], row["trace_id"])
        return done
