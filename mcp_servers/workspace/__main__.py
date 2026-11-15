"""Run: python -m mcp_servers.workspace  (Streamable HTTP on MCP_HOST:8203/mcp)."""

from mcp_servers.workspace.server import build_server

if __name__ == "__main__":
    build_server().run(transport="streamable-http")
