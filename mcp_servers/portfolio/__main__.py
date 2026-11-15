"""Run: python -m mcp_servers.portfolio  (Streamable HTTP on MCP_HOST:8201/mcp)."""

from mcp_servers.portfolio.server import build_server

if __name__ == "__main__":
    build_server().run(transport="streamable-http")
