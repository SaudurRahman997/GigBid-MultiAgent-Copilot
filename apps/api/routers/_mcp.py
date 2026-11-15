"""Calls from routers to MCP tools (read-only listing screens); errors become HTTP errors."""

from __future__ import annotations

from fastapi import HTTPException

from agent.mcp_client import MarketplaceDegraded, ToolCallFailed, ToolNotAllowed


async def mcp_read(svc, user: dict, agent: str, tool: str, args: dict) -> dict:
    try:
        return await svc.mcp(user).call(agent, tool, args)
    except MarketplaceDegraded as exc:
        raise HTTPException(503, {"degraded": True, "message": "marketplace unavailable", "reason": str(exc)}) from None
    except ToolCallFailed as exc:
        raise HTTPException(404 if "not_found" in str(exc) else 502, str(exc)) from None
    except ToolNotAllowed as exc:
        raise HTTPException(500, str(exc)) from None
