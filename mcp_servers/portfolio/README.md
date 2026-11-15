# GigBid Portfolio MCP server

A Model Context Protocol server that lets an AI agent search a freelancer's **own** portfolio
evidence (case studies, past proposals, client reviews, GitHub READMEs) and check whether claims
in a draft proposal are supported by that evidence. Read-only; built with the official MCP Python
SDK (FastMCP) over Streamable HTTP with bearer-token auth and a masked audit log.

## Tools

| Tool | What it does |
|---|---|
| `search_evidence(requirement, k)` | hybrid (BM25 + dense) retrieval of evidence items for one job requirement |
| `get_case_study(id)` | full text of one portfolio item |
| `list_skills()` | skills found in the portfolio with counts |
| `get_profile()` | headline, skills, rate floors |
| `verify_claims(draft)` | splits a draft into claims and labels each supported / partial / unsupported with evidence ids |

Resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://repo/{name}`.
Prompts: three proposal-writing prompts (see `prompts/`). Input/output schemas are snapshotted in
`tests/contract/snapshots/portfolio.json`; the full catalogue is in `docs/TOOLS.md`.

## Run it

### Docker (no Python needed)

```bash
git clone https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot.git
cd GigBid-MultiAgent-Copilot
docker build -f mcp_servers/Dockerfile -t gigbid-mcp .
docker run --rm -p 8201:8201 \
  -e MCP_HOST=0.0.0.0 -e MCP_DATABASE_URL=sqlite:////tmp/mcp.db \
  -e MCP_TOKENS=ai_ml:demo-token \
  -v "$PWD/data:/app/data:ro" \
  gigbid-mcp python -m mcp_servers.portfolio
```

### uv (from source)

```bash
uv sync
MCP_DATABASE_URL=sqlite:///./mcp.db MCP_TOKENS=ai_ml:demo-token uv run python -m mcp_servers.portfolio
```

The server listens on `http://localhost:8201/mcp`. Send `Authorization: Bearer demo-token`.

### Connect a client

MCP Inspector: `npx @modelcontextprotocol/inspector`, transport *Streamable HTTP*, URL
`http://localhost:8201/mcp`, header `Authorization: Bearer demo-token`.

Claude Desktop / any MCP client config:

```json
{
  "mcpServers": {
    "gigbid-portfolio": {
      "type": "http",
      "url": "http://localhost:8201/mcp",
      "headers": { "Authorization": "Bearer demo-token" }
    }
  }
}
```

The token above signs you in as user `ai_ml`, which serves the bundled synthetic AI/ML persona
(`data/personas/ai_ml`). Point `MCP_DATA_DIR` at your own portfolio files to use your own
evidence.

## Trust and safety

Read-only (no write tools), bearer auth on every request, per-user rate limit, PII masking in the
audit log, and evidence text is returned as data (clients should treat it as untrusted).
