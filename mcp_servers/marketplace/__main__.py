"""Run: python -m mcp_servers.marketplace  (Streamable HTTP on MCP_HOST:8202/mcp)."""

from mcp_servers.marketplace.server import build_server

if __name__ == "__main__":
    build_server().run(transport="streamable-http")
