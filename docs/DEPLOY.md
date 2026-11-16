# Deploying GigBid

Live: **https://gigbid-beta.vercel.app** (web) and **https://gigbid-api.vercel.app** (API).

| Piece | Host | Source |
|---|---|---|
| Web UI (Next.js) | Vercel project `gigbid` | `apps/web` |
| API + agents (FastAPI, Python function) | Vercel project `gigbid-api` | bundle built by `scripts/build_vercel_api.py` |

The browser only talks to the web origin. Next.js rewrites `/api/*` to `API_INTERNAL_URL`
(`apps/web/next.config.ts`), so the session cookie is first-party and no CORS setup is needed.

## Demo mode vs the full stack

The hosted API runs in single-process demo mode:

- `GIGBID_MCP_MODE=inprocess`: the agents call the in-process tool layer (`evals/inprocess_mcp.py`).
  It has the same tool names, result shapes and idempotent write behaviour as the three MCP servers
  and is backed by the synthetic data in `data/`, so no Postgres, Redis or MCP servers are needed.
- `GIGBID_INLINE_RUNS=1`: serverless functions do not keep background tasks alive after a
  response, so analyze/approve drive the graph to its next stop (the approval interrupt or the end)
  before returning. The run timeline (SSE) replays the stored events.
- `GIGBID_AGENT_MODE=rules`: deterministic nodes, so no model keys are needed in the cloud.
- State (sqlite in `/tmp`, in-memory checkpoints) lives as long as a function instance. A cold
  start clears runs and drafts; the reviewer account is re-created from env on start, so signing in
  again always works. Setting `API_DATABASE_URL` to a Postgres URL in the Vercel project makes runs
  and checkpoints durable (`langgraph-checkpoint-postgres`).

Human approval via `interrupt()` is unchanged, and nothing is ever sent to a real marketplace.
The full stack (GigSim, three MCP servers over Streamable HTTP, Postgres checkpoints, Phoenix)
runs locally with `make up && make seed && make dev`.

The function bundle installs only what the API imports, pinned to `uv.lock` (about 200 MB, under the
Vercel limit); pandas reads the one parquet file with fastparquet instead of pyarrow.

## Redeploy

```sh
# API
uv run python -m scripts.build_vercel_api
cd var/vercel-api
npx vercel link --project gigbid-api          # first time only
npx vercel env add JWT_SECRET production      # first time only (random string)
npx vercel env add REVIEWER_EMAIL production
npx vercel env add REVIEWER_PASSWORD production
npx vercel deploy --prod

# Web (from apps/web)
npx vercel link --project gigbid              # first time only
npx vercel env add NEXT_PUBLIC_API_URL production   # /api
npx vercel env add API_INTERNAL_URL production      # https://gigbid-api.vercel.app
npx vercel deploy --prod
```

Both web variables are read at build time, so redeploy the web after changing them.

## Alternative: Docker host

`apps/api/Dockerfile.demo` runs the same demo-mode API as a long-lived container (runs continue in
the background, no inline mode needed). `render.yaml` is a Render blueprint for it.

## Check

- `https://gigbid-beta.vercel.app/api/health` returns the API health JSON.
- Sign in at `/onboarding` with the reviewer account.
- Inbox -> open a job -> Analyze -> the run timeline shows every node, and a bid-worthy job stops at
  the approval panel; approve -> the pipeline shows it as submitted.

Reviewer credentials go in the private Classroom comment only, never in the repository.
