"""SSE bridge: LangGraph `astream` (updates + custom) -> per-thread event log -> browser.

Every event gets a monotonically increasing id inside its thread. A browser that reconnects sends
`Last-Event-ID` (or `?after=`) and receives everything it missed, then live events. The log for a
thread lives as long as the process; state that must survive restarts comes from the checkpointer
(GET /runs/{thread_id}), not from this log.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

TERMINAL = "end"


def jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [jsonable(v) for v in obj]
    if hasattr(obj, "value") and type(obj).__name__ == "Interrupt":
        return {"interrupt": jsonable(obj.value)}
    if obj is None or isinstance(obj, str | int | float | bool):
        return obj
    return str(obj)


def update_event(chunk: dict) -> dict:
    """One `updates` chunk -> a compact event: which node finished and what it wrote (trace + note)."""
    out = []
    for node_name, update in chunk.items():
        if node_name == "__interrupt__":
            out.append({"node": "approval", "event": "interrupt", "payload": jsonable(update)})
            continue
        update = update or {}
        trace = update.get("trace") or []
        out.append({"node": node_name, "event": "done", "status": update.get("status"),
                    "note": trace[-1].get("note") if trace else None})  # fmt: skip
    return {"type": "node", "items": out}


class Broker:
    def __init__(self) -> None:
        self.events: dict[str, list[dict]] = defaultdict(list)
        self.cond: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def publish(self, thread_id: str, event: dict) -> None:
        cond = self.cond[thread_id]
        async with cond:
            log = self.events[thread_id]
            log.append({"id": len(log) + 1, **event})
            cond.notify_all()

    async def subscribe(self, thread_id: str, after: int = 0) -> AsyncIterator[dict]:
        cond = self.cond[thread_id]
        i = after
        while True:
            async with cond:
                while len(self.events[thread_id]) <= i:
                    try:
                        await asyncio.wait_for(cond.wait(), timeout=15)
                    except TimeoutError:
                        break
                batch = self.events[thread_id][i:]
            if not batch:
                log = self.events[thread_id]
                if log and log[-1]["type"] == TERMINAL:  # reconnect after the run already ended
                    return
                yield {"id": i, "type": "ping"}
                continue
            for ev in batch:
                i = ev["id"]
                yield ev
                if ev["type"] == TERMINAL:
                    return


def sse_format(ev: dict) -> dict:
    """Shape for sse_starlette's EventSourceResponse."""
    return {"id": str(ev["id"]), "event": ev["type"], "data": json.dumps(ev, default=str)}
