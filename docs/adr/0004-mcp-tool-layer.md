# ADR 0004: MCP tool layer

- Status: accepted
- Date: 2026-11-15

## Decisions
1. **Official MCP Python SDK (FastMCP), Streamable HTTP, static bearer tokens.** First-party
   servers inside one deployment; tokens map to users (`MCP_TOKENS`). OAuth 2.1 is used where it
   matters - the client side of Upwork's MCP (Phase 10). Token audience validation is off because
   static tokens carry no audience; documented in `mcp_servers/common/runtime.py`.
2. **Idempotency lives in the server, not only in GigSim.** Every write stores
   `(server, user, tool, key) -> result` with a hash of the arguments. This makes drafts and
   messages idempotent even though GigSim's own draft/message endpoints are not, and rejects key
   reuse with different arguments. Submit additionally forwards the key to GigSim.
3. **dry_run on every write** returns the exact payload and Connects cost; the approval UI shows it.
4. **One marketplace port** (`agent/marketplace_port.py`) with canonical Pydantic models; adapters
   map into them. The MCP tools depend on the port, so swapping GigSim for Upwork is a config
   change (`marketplace:` in `agent/config.yaml`).
5. **Granularity (first version):** task-shaped read tools (`search_jobs` returns summaries,
   `get_job` the full post) and one write tool per irreversible step (draft vs submit). R&D A
   (Phase 11) compares this against finer and coarser sets and rewritten descriptions.
6. **Per-agent allowlists in config**, enforced in `agent/mcp_client.py`; an unknown agent gets an
   error, never "all tools". Only the `submitter` role can see `submit_proposal`.
7. **Errors are `<code>: <message>`** (the SDK adds an `Error executing tool X:` prefix that the
   client strips). Transient codes (`rate_limited`, `marketplace_unavailable`) are retried with
   bounded exponential backoff; after that the marketplace is reported degraded and writes are
   queued (`PendingQueue`) to be resumed with the same idempotency keys.
8. **Retrieval behind an interface** (`rag/retriever.py`); `bm25_baseline` is an interim variant so
   the Portfolio server works before Phase 4. The deployed variant is chosen by measurement.

## Consequences
- A BM25 smoke test exposed a data leak (past proposals reused the dev-set job wording); fixed in
  the generator before any RAG numbers were produced (see AI_USAGE.md).
- Rate limiter and idempotency store are per server process + database; fine for one instance.
