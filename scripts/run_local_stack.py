"""Run GigSim + the three MCP servers locally on SQLite, without Docker (dev convenience).

Same ports as docker compose: GigSim :8100, portfolio :8201, marketplace :8202, workspace :8203.
Usage: uv run python scripts/run_local_stack.py   (Ctrl+C to stop)
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VAR = ROOT / "var"


def main() -> None:
    import uvicorn

    VAR.mkdir(exist_ok=True)
    os.environ.setdefault(
        "GIGSIM_DATABASE_URL", f"sqlite:///{(VAR / 'gigsim-local.db').as_posix()}"
    )
    os.environ.setdefault("GIGSIM_ERROR_RATE", "0.03")
    os.environ.setdefault("MCP_DATABASE_URL", f"sqlite:///{(VAR / 'mcp-local.db').as_posix()}")
    logging.getLogger("mcp").setLevel(logging.WARNING)

    from gigsim.app import create_app
    from mcp_servers.common.settings import MCPSettings
    from mcp_servers.common.store import Store
    from mcp_servers.marketplace.server import build_server as marketplace
    from mcp_servers.portfolio.server import build_server as portfolio
    from mcp_servers.workspace.server import build_server as workspace
    from mcp_servers.workspace.server import ws_metadata

    s = MCPSettings()
    store = Store(s.database_url, extra_metadata=[ws_metadata])
    apps = {
        8100: create_app(),
        8201: portfolio(s, store=store).streamable_http_app(),
        8202: marketplace(s, store=store).streamable_http_app(),
        8203: workspace(s, store=store).streamable_http_app(),
    }
    servers = []
    for port, app in apps.items():
        srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        threading.Thread(target=srv.run, daemon=True).start()
        servers.append(srv)
    while not all(x.started for x in servers):
        time.sleep(0.1)
    print(
        "local stack up: gigsim :8100 | portfolio :8201 | marketplace :8202 | workspace :8203",
        flush=True,
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for x in servers:
            x.should_exit = True


if __name__ == "__main__":
    main()
