"""Schema snapshot tests: fail when any MCP tool/resource/prompt signature changes.

A deliberate change: `UPDATE_SNAPSHOTS=1 uv run pytest tests/contract` (or `make snapshots`),
review the diff, regenerate docs/TOOLS.md (`make tools-doc`), commit all three together.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from mcp_servers.common.settings import MCPSettings
from mcp_servers.common.store import Store
from mcp_servers.marketplace.server import build_server as build_marketplace
from mcp_servers.portfolio.server import build_server as build_portfolio
from mcp_servers.workspace.server import build_server as build_workspace
from mcp_servers.workspace.server import ws_metadata

SNAPSHOTS = Path(__file__).with_name("snapshots")
BUILDERS = {
    "portfolio": build_portfolio,
    "marketplace": build_marketplace,
    "workspace": build_workspace,
}


def describe(name: str) -> dict:
    s = MCPSettings(database_url="sqlite://", dev_user="ai_ml")
    store = Store(s.database_url, extra_metadata=[ws_metadata])
    mcp = BUILDERS[name](s, store=store)
    tools = asyncio.run(mcp.list_tools())
    templates = asyncio.run(mcp.list_resource_templates())
    prompts = asyncio.run(mcp.list_prompts())
    return {
        "server": name,
        "tools": [
            {
                "name": t.name,
                "title": t.title,
                "description": t.description,
                "annotations": t.annotations.model_dump(exclude_none=True)
                if t.annotations
                else None,
                "inputSchema": t.inputSchema,
                "outputSchema": t.outputSchema,
            }
            for t in sorted(tools, key=lambda t: t.name)
        ],
        "resource_templates": sorted(t.uriTemplate for t in templates),
        "prompts": sorted(
            ({"name": p.name, "arguments": [a.name for a in p.arguments or []]} for p in prompts),
            key=lambda p: p["name"],
        ),
    }


def render(obj: dict) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_schema_snapshot(name):
    path = SNAPSHOTS / f"{name}.json"
    current = render(describe(name))
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current, encoding="utf-8", newline="\n")
    assert path.exists(), f"missing snapshot {path.name}: run `make snapshots`"
    assert path.read_text(encoding="utf-8") == current, (
        f"{name} MCP signature changed. If deliberate: `make snapshots`, `make tools-doc`, commit."
    )


def test_every_write_tool_has_idempotency_key_and_dry_run():
    for name in BUILDERS:
        for tool in describe(name)["tools"]:
            ann = tool["annotations"] or {}
            if ann.get("readOnlyHint") is False:
                props = tool["inputSchema"]["properties"]
                assert "idempotency_key" in tool["inputSchema"].get("required", []), tool["name"]
                assert "dry_run" in props, tool["name"]


def test_every_tool_declares_output_schema_and_annotations():
    for name in BUILDERS:
        for tool in describe(name)["tools"]:
            assert tool["outputSchema"], tool["name"]
            ann = tool["annotations"]
            assert ann and {"readOnlyHint", "destructiveHint", "idempotentHint"} <= set(ann), tool[
                "name"
            ]


def test_tools_doc_is_up_to_date():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "gen_tools_doc.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
