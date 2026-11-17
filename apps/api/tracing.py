"""The current request's trace id (set by the API middleware from X-Trace-Id).

A ContextVar, so every MCP call made while serving a request (reads in routers and graph runs started
by it) carries the same id to the MCP servers' audit logs without threading it through every call.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)


def trace_id_or_new() -> str:
    return current_trace_id.get() or uuid.uuid4().hex
