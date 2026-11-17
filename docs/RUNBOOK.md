# Runbook

## Services

| Service | Start | Health |
|---|---|---|
| Full stack | `make up` (infra/docker-compose.yml) | `make ps` |
| API | `make api` (dev) or compose `api` | `GET /health` (`degraded: true` when the marketplace is down) |
| Worker | `make worker` (needs `REDIS_URL`) or compose `worker` | Arq logs each cron and job; runs appear on the Runs page |
| Web | `make web-dev` or Vercel (docs/DEPLOY.md) | `/onboarding` loads; the degraded banner shows API health |
| GigSim | `make gigsim` or compose `gigsim` | `GET /docs` |

## Worker: what it does

`apps/worker/` (Arq 0.28.0, Redis):

| Job | Trigger | Does |
|---|---|---|
| `schedule_saved_searches` | cron, every minute | For every user's saved search (Settings), enqueues `run_saved_search` once per interval slot |
| `run_saved_search` | enqueued | `search_jobs` via the Scout MCP tool; enqueues `analyze_job` for each result |
| `analyze_job` | enqueued | Runs the bid graph up to the human-approval interrupt |
| `poll_messages` | cron, every 5 minutes | For each thread whose latest message is from the client, enqueues `reply_to_thread` |
| `reply_to_thread` | enqueued | Runs the conversation graph up to the message-approval interrupt |

**Idempotency.**
- An Arq job id is enqueued only once. Saved searches use `search:<user>:<name>:<slot>`.
- Analyses use the dedupe key `analyze:<user>:<marketplace job id>`. `analyze_job` also skips a job
  that already has a bid run, so an expired Redis key cannot cause a second analysis.
- Replies use `msg:<user>:<thread>:<message id>`.
- A worker restart, two workers, or a repeated cron tick cannot double-process anything.

**Nothing is sent by the worker.** Every graph stops at `interrupt()`; a human approves in the UI.

## Polling intervals (why they are conservative)

Configured in `agent/config.yaml` `scheduling` and enforced by `apps/worker/jobs.py::interval_minutes`.
A saved search runs at its own `every_minutes` (30 to 1440, validated by the API), but never faster
than the marketplace floor:

| Marketplace | Floor | Reason |
|---|---|---|
| GigSim (`marketplace: gigsim`) | 10 min | Our own simulator; jobs are released on a simulated clock, so 10 minutes is enough and keeps logs readable. |
| Upwork live (`marketplace: upwork_live`) | **60 min** | We read jobs only through the official API/MCP and never scrape. Job posts stay open for days, so a freelancer gains nothing from minute-level polling. Hourly polling keeps us far below any rate limit, respects the platform's guidance against aggressive automation, and limits token spend: each new job costs one graph run. Saved searches can only make it slower. |

Message polling runs every 5 minutes, but it only reads and starts graphs that wait for approval.
On Upwork live it should be set to the same 60-minute floor or replaced by webhooks when available.

## Common operations

- **Marketplace down:** the API returns 503 with `degraded: true`, and the UI shows a banner; the
  worker's jobs fail and Arq retries them on the next cron slot. Nothing is lost: graph state is
  checkpointed in Postgres.
- **A run is stuck in `needs_attention`:** a step or token budget was hit
  (`agent/config.yaml budgets`). Open the run timeline, read the last node's note, and re-run the job
  from the Inbox.
- **Platform policy change:** follow ADR 0006. Edit `data/policy_pack/` and `agent/config.yaml`
  `policy_version`; `tests/unit/test_policy_alignment.py` fails until the pack matches the platform.
- **Rotate secrets:** set `JWT_SECRET` and `TOKEN_ENCRYPTION_KEY` in the environment (never in git).
  Rotating `JWT_SECRET` signs everyone out; rotating `TOKEN_ENCRYPTION_KEY` requires reconnecting
  accounts.
