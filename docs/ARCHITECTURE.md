# GigBid architecture

GigBid is a multi-agent copilot for one freelancer at a time. It reads marketplace jobs, decides
bid / skip / watch, drafts a proposal grounded in the freelancer's own portfolio, handles client
messages, and **never sends anything without a human approval** (LangGraph `interrupt()`).

## Components

```
 Browser (Next.js, apps/web)
    |  /api/*  (same origin; X-Trace-Id per request)
    v
 FastAPI (apps/api) ── auth, tenants, SSE, approvals ──┐
    |  start / resume graph runs                       │ shared Postgres (checkpoints, store, runs)
    v                                                  │
 LangGraph (agent/)  <── enqueue ── Arq worker (apps/worker): saved searches, message polling
    |  every data access is an MCP tool call (per-agent allowlist, bearer token, X-Trace-Id)
    v
 MCP servers (mcp_servers/): Portfolio | Marketplace | Workspace   ── audit log (PII-masked)
    |                                   |
    v                                   v
 pgvector evidence index (rag/)     GigSim marketplace simulator (gigsim/, frozen)
```

| Component | Path | Responsibility |
|---|---|---|
| Web | `apps/web/` | 9 screens; typed client generated from OpenAPI; live run timeline over SSE; evidence on hover; approval panel with edit diff |
| API | `apps/api/` | Multi-user auth (scrypt, JWT cookie), tenant id on every query, graph start/resume, SSE bridge, encrypted OAuth token store, trace-id middleware |
| Worker | `apps/worker/` | Arq jobs: saved searches once per interval slot, idempotent analysis (user + job id), message polling |
| Agents | `agent/` | Bid graph and conversation graph; prompts in `agent/prompts/<node>.v1.md`; thresholds and budgets in `agent/config.yaml`; hand-offs are Pydantic models (`agent/handoffs.py`) |
| MCP servers | `mcp_servers/` | Portfolio (evidence, case studies, profile, claim verification), Marketplace (jobs, clients, market rates, Connects, proposals), Workspace (messages, calendar, holds); every write tool has `idempotency_key` + `dry_run` |
| Retrieval | `rag/` | Ingestion, chunking, pgvector index, variants V0–V4 and V8, claim verifier |
| Simulator | `gigsim/` | Marketplace with simulated clients, rate limits, chaos errors, idempotent submit, policy versions |
| Policy | `data/policy_pack/` | Compliance rules, scam and injection patterns, Connects rules |

## Bid graph

`scout_in` -> parallel `Send` fan-out to **Job Analyst || Risk Assessor || Fit Matcher** -> `decide`
(bid / skip / watch) -> `pricing` -> `writer` -> `verify_claims` -> `critic` (back to the writer, at
most 2 rounds) -> `compliance` -> `prepare_approval` -> **`approval` interrupt** -> `submit` (or
`apply_edit` -> compliance re-check, or reject) -> `record_outcome`.

## Conversation graph

`new_message` -> `classify_intent` -> `propose_slots` / `draft_reply` -> `message_compliance` ->
**`message_approval` interrupt** -> `send` -> `update_pipeline`.

## Cross-cutting

- **Exactly-once submit:** idempotency key `<thread>:submit:v<draft version>`; a lost response or a
  crash inside `submit` replays the stored result instead of charging Connects twice.
- **Tracing:** one `X-Trace-Id` per UI request reaches the graph run, every MCP call and every
  server's audit log, plus the LangGraph run metadata (Phoenix).
- **Guardrails:** untrusted-data delimiters, injection flagging, output compliance filter, PII
  masking, step and token budgets, human approval for every send and Connects spend.
- **Memory:** style rules learned from repeated human edits (3 threads), outcome memory from terminal
  marketplace events; viewable and deletable in Settings.

Deployment: `docs/DEPLOY.md` (Vercel demo) and `infra/docker-compose.yml` (full stack).
Decisions: `docs/adr/`.
