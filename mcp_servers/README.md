# GigBid MCP servers

Three first-party MCP servers built with the official MCP Python SDK (FastMCP), served over
**Streamable HTTP** with **bearer-token auth**. Agents reach the outside world only through
these tools (via `agent/mcp_client.py`). Full tool table: [docs/TOOLS.md](../docs/TOOLS.md).

| Server | Port | Purpose | Tools |
|---|---|---|---|
| `portfolio` | 8201 | read-only portfolio retrieval (`rag/retriever.py`) | `search_evidence`, `get_case_study`, `list_skills` + resources `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://repo/{name}` + 3 prompts |
| `marketplace` | 8202 | marketplace read/write over **one port, two adapters** (`agent/marketplace_port.py` -> `adapters/gigsim.py` / `adapters/upwork_live.py`) | `search_jobs`, `get_job`, `get_client_history`, `get_connects_balance`, `list_messages`, `create_proposal_draft`, `submit_proposal`, `send_message` |
| `workspace` | 8203 | calendar + email drafts (local mock) | `free_slots`, `create_tentative_hold`, `create_email_draft` |

## Run

```bash
make up            # docker compose: postgres, gigsim and the three servers
make local-stack   # or without Docker (SQLite) on the same ports
make proposal-demo # one agent drafts one grounded proposal through these tools
```

Call a server by hand (needs a token from `MCP_TOKENS`):

```bash
curl -s localhost:8202/health
```

## Guarantees

- **Auth:** `Authorization: Bearer <token>`; unknown or missing token -> 401. Each user only sees
  their own persona / marketplace account.
- **Writes:** required `idempotency_key` (same key + same args -> stored result, `replayed: true`;
  same key + different args -> `idempotency_conflict`) and `dry_run` (preview + Connects cost,
  nothing sent). `submit_proposal` forwards the key to GigSim as `Idempotency-Key`, so even a
  lost response followed by a retry charges Connects once.
- **Rate limit:** per-user token bucket, 50/min by default (under GigSim's 60/min); the GigSim
  adapter also honours `429 Retry-After` and backs off on 5xx.
- **Audit:** append-only `gigbid.mcp_audit_log` (Postgres trigger blocks UPDATE/DELETE) with
  masked args, result summary, status and the caller's `X-Trace-Id`.

## MCP Inspector screenshots (manual step for docs/images/)

```bash
make up                                   # or: make local-stack
npx @modelcontextprotocol/inspector       # opens the Inspector in your browser
```

In the Inspector choose **Transport: Streamable HTTP**, URL `http://localhost:8202/mcp`, and add the
header `Authorization: Bearer dev-mcp-ai-ml`. Connect, then screenshot:
1. the **Tools** list with annotations (marketplace),
2. a `create_proposal_draft` call with `dry_run: true` showing the preview and Connects cost,
3. the portfolio **Resources** tab (`portfolio://case/{id}`) and **Prompts** tab.
Save them as `docs/images/inspector-*.png`.
