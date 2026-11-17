"""Node runtime: injected dependencies, the node wrapper (budgets, retries, timeouts, dead-letter,
trace) and LLM helpers with rule-based fallback.

Nodes never import clients themselves: they receive `Deps` through LangGraph's runtime context,
so tests inject fakes and the graph cannot reach anything that is not an MCP tool.
"""

from __future__ import annotations

import asyncio
import functools
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml
from langgraph.errors import GraphBubbleUp
from langgraph.runtime import Runtime

from agent.mcp_client import MarketplaceDegraded, ToolCallFailed, ToolNotAllowed

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "data" / "policy_pack" / "policy.yaml"


class MCPCaller(Protocol):
    async def call(self, agent: str, tool: str, args: dict) -> dict: ...


@dataclass
class Deps:
    mcp: MCPCaller
    config: dict
    user: str
    llm: Callable[[str], Any] | None = None  # node name -> chat model, or None for rules mode
    policy: dict = field(default_factory=lambda: yaml.safe_load(POLICY.read_text(encoding="utf-8")))
    store: Any = None  # LangGraph BaseStore for long-term memory (style / outcome)

    def mode(self, node: str) -> str:
        if self.llm is None:
            return "rules"
        return self.config.get("agents", {}).get("modes", {}).get(node, "rules")


class BudgetExceeded(Exception):
    pass


NodeFn = Callable[[dict, Deps], Awaitable[dict]]


def node(name: str) -> Callable[[NodeFn], Callable]:
    """Wrap a node: budget check, bounded retries + timeout, dead-letter on failure, trace line."""

    def deco(fn: NodeFn):
        @functools.wraps(fn)
        async def wrapped(state: dict, runtime: Runtime[Deps]) -> dict:
            deps = runtime.context
            budgets = deps.config["budgets"]
            agents = deps.config.get("agents", {})
            if state.get("steps", 0) >= budgets["max_steps_per_thread"]:
                return _halt(
                    name,
                    "needs_attention",
                    f"step budget {budgets['max_steps_per_thread']} exceeded",
                )
            if state.get("tokens", 0) >= budgets["max_tokens_per_thread"]:
                return _halt(
                    name,
                    "needs_attention",
                    f"token budget {budgets['max_tokens_per_thread']} exceeded",
                )
            attempts = 1 + int(agents.get("node_retries", 2))
            t0 = time.perf_counter()
            last: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    out = await asyncio.wait_for(
                        fn(state, deps), timeout=float(agents.get("node_timeout_s", 90))
                    )
                    break
                except GraphBubbleUp:  # interrupt() and friends must reach LangGraph untouched
                    raise
                except MarketplaceDegraded as exc:
                    return _halt(name, "needs_attention", f"marketplace degraded: {exc.reason}")
                except (ToolNotAllowed, BudgetExceeded) as exc:
                    return _halt(name, "needs_attention", str(exc))
                except ToolCallFailed as exc:
                    last = exc
                    if exc.code not in {"rate_limited", "marketplace_unavailable", "timeout"}:
                        break  # permanent tool error: do not retry
                except (TimeoutError, Exception) as exc:  # noqa: BLE001 - recorded, then dead-letter
                    last = exc
                if attempt < attempts:
                    await asyncio.sleep(min(4.0, 0.25 * 2 ** (attempt - 1)))
            else:
                out = None
            if out is None:
                return {**_halt(name, "dead_letter", f"{type(last).__name__}: {last}"),
                        "errors": [f"{name}: {type(last).__name__}: {last}"]}  # fmt: skip
            note = out.pop("_note", "")
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {**out, "steps": 1, "trace": [{"node": name, "ms": ms, "note": note}]}

        wrapped.node_name = name  # type: ignore[attr-defined]
        wrapped.inner = fn  # type: ignore[attr-defined]
        # LangGraph reads the signature to inject `runtime`; functools.wraps would make
        # inspect.signature follow __wrapped__ to the inner (state, deps) signature instead.
        del wrapped.__wrapped__
        return wrapped

    return deco


def _halt(name: str, status: str, reason: str) -> dict:
    return {"status": status, "attention_reason": reason, "steps": 1,
            "trace": [{"node": name, "ms": 0.0, "note": f"{status}: {reason}"}]}  # fmt: skip


# ----------------------------------------------------------------------------- LLM helpers


def tokens_of(msg: Any) -> int:
    usage = getattr(msg, "usage_metadata", None) or {}
    return int(usage.get("total_tokens", 0))


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", strip_think(text), flags=re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


async def ask(deps: Deps, node_name: str, prompt: str) -> tuple[str, int]:
    """Call the node's model; returns (text, tokens)."""
    model = deps.llm(node_name) if deps.llm else None
    if model is None:
        raise RuntimeError(f"no model for {node_name}")
    msg = await model.ainvoke(prompt)
    return strip_think(str(msg.content)), tokens_of(msg)


def untrusted(label: str, text: str) -> str:
    """Wrap untrusted marketplace text in delimiters the prompts declare as data-only."""
    clean = text.replace("<<<", "«").replace(">>>", "»")
    return f"<<<UNTRUSTED {label}\n{clean}\n>>>"
