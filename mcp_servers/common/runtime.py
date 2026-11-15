"""Per-request helpers for MCP tools: who is calling, trace id, rate limit, bearer auth."""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections.abc import Callable

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from mcp_servers.common.settings import MCPSettings

TRACE_HEADERS = ("x-trace-id", "traceparent")


class StaticTokenVerifier:
    """Bearer tokens from MCP_TOKENS ("user:token,..."). The user becomes AccessToken.client_id."""

    def __init__(self, token_map: dict[str, str], scopes: list[str] | None = None):
        self.token_map = token_map
        self.scopes = scopes or ["gigbid"]

    async def verify_token(self, token: str) -> AccessToken | None:
        user = self.token_map.get(token)
        if user is None:
            return None
        return AccessToken(token=token, client_id=user, scopes=self.scopes, subject=user)


def make_server(name: str, instructions: str, settings: MCPSettings, port: int) -> FastMCP:
    """FastMCP with bearer auth on Streamable HTTP and DNS-rebinding protection."""
    url = f"{settings.public_url}:{port}"
    return FastMCP(
        name=name,
        instructions=instructions,
        host=settings.host,
        port=port,
        token_verifier=StaticTokenVerifier(settings.token_map),
        # Static first-party tokens carry no audience claim, so resource validation is off;
        # Phase 10 (Upwork OAuth 2.1) uses real issuer-validated tokens on the client side.
        auth=AuthSettings(
            issuer_url=url,
            resource_server_url=f"{url}/mcp",
            required_scopes=["gigbid"],
            validate_token_resource=False,
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.allowed_host_list,
            allowed_origins=[f"http://{h}" for h in settings.allowed_host_list],
        ),
    )


def current_user(settings: MCPSettings) -> str:
    """Caller from the verified bearer token; MCP_DEV_USER only for in-memory/stdio sessions."""
    token = get_access_token()
    if token is not None:
        return token.client_id
    if settings.dev_user:
        return settings.dev_user
    raise ToolError("unauthenticated: a bearer token is required")


def trace_id(ctx: Context | None) -> str:
    """Trace id from the HTTP request (X-Trace-Id / traceparent), else a new one."""
    try:
        request = ctx.request_context.request if ctx is not None else None
    except (AttributeError, ValueError, LookupError):
        request = None
    headers = getattr(request, "headers", None)
    if headers is not None:
        for h in TRACE_HEADERS:
            if headers.get(h):
                value = headers.get(h)
                return (
                    value.split("-")[1] if h == "traceparent" and value.count("-") >= 3 else value
                )
    return uuid.uuid4().hex


class TokenBucket:
    """Per-user limiter: `rate_per_min` calls per minute, bursts up to the same size."""

    def __init__(self, rate_per_min: int, clock: Callable[[], float] = time.monotonic):
        self.capacity = float(rate_per_min)
        self.refill = rate_per_min / 60.0
        self.clock = clock
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def check(self, user: str) -> None:
        with self._lock:
            now = self.clock()
            tokens, last = self._state.get(user, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill)
            if tokens < 1.0:
                self._state[user] = (tokens, now)
                retry = max(1, math.ceil((1.0 - tokens) / self.refill))
                raise ToolError(f"rate_limited: retry after {retry}s")
            self._state[user] = (tokens - 1.0, now)


class ToolRunner:
    """Wraps every tool call: auth -> rate limit -> run -> audit (masked) -> map errors.

    `error_codes` maps exception types to stable error codes the agent can branch on; the
    exception's own `code` attribute wins if present. Errors surface as ToolError("<code>: msg").
    """

    def __init__(
        self,
        server: str,
        settings: MCPSettings,
        store,
        limiter: TokenBucket,
        error_codes: dict[type[Exception], str] | None = None,
    ):
        self.server, self.s, self.store, self.limiter = server, settings, store, limiter
        self.error_codes = error_codes or {}

    async def run(
        self, tool: str, args: dict, ctx: Context | None, fn, summarize=lambda r: type(r).__name__
    ):
        from mcp_servers.common.store import IdempotencyConflict

        user = current_user(self.s)
        tid = trace_id(ctx)
        self.limiter.check(user)
        try:
            result = await fn(user)
        except ToolError as exc:
            self.store.audit(
                user=user,
                server=self.server,
                tool=tool,
                args=args,
                result_summary=str(exc),
                status="error",
                trace_id=tid,
            )
            raise
        except Exception as exc:
            code = (
                "idempotency_conflict"
                if isinstance(exc, IdempotencyConflict)
                else getattr(exc, "code", None)
            )
            code = code or next(
                (c for t, c in self.error_codes.items() if isinstance(exc, t)), None
            )
            if code is None:
                raise
            self.store.audit(
                user=user,
                server=self.server,
                tool=tool,
                args=args,
                result_summary=f"{code}: {exc}",
                status="error",
                trace_id=tid,
            )
            raise ToolError(f"{code}: {exc}") from exc
        status = (
            "dry_run"
            if args.get("dry_run")
            else ("replayed" if getattr(result, "replayed", False) else "ok")
        )
        self.store.audit(
            user=user,
            server=self.server,
            tool=tool,
            args=args,
            result_summary=summarize(result),
            status=status,
            trace_id=tid,
        )
        return result

    async def idempotent(self, user: str, tool: str, key: str, args: dict, model, do):
        """Same key + same args -> stored result (replayed=True); first call runs `do`."""
        prior = self.store.recall(self.server, user, tool, key, args)
        if prior is not None:
            return model.model_validate({**prior, "replayed": True})
        result = await do()
        stored = self.store.remember(
            self.server, user, tool, key, args, result.model_dump(mode="json")
        )
        return model.model_validate(stored)
