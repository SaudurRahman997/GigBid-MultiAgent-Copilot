# GigSim — simulated freelance marketplace

GigBid develops and is graded against GigSim instead of a live marketplace. It is a FastAPI
service backed by its own Postgres schema (`gigsim`), loaded from the Phase 1 data
(`data/synthetic`, `data/devset`, optionally `data/heldout`).

> **Frozen after Phase 2.** CI fails if anything under `gigsim/` changes without updating
> `FROZEN.sha256` (`uv run python scripts/check_gigsim_frozen.py --update`) and adding an ADR.

## Run

```bash
make up                         # postgres + redis + phoenix + gigsim (docker compose)
curl -H "Authorization: Bearer dev-token-ai-ml" localhost:8100/jobs?limit=3
make gigsim                     # or locally on SQLite, auto-reload: http://localhost:8100/docs
```

## API (bearer token per user; tokens from `GIGSIM_TOKENS`)

| Method | Path | Notes |
|---|---|---|
| GET | `/jobs?query&category&since&limit&offset` | released jobs only; gold labels never returned |
| GET | `/jobs/{id}` | |
| GET | `/clients/{id}/history` | public profile only; hidden preferences never returned |
| GET | `/me/connects` | balance + last 20 ledger entries |
| POST | `/proposals` | create a **draft**; rejects contact details (and links under policy v2) with 422 |
| POST | `/proposals/{id}/submit` | **requires `Idempotency-Key`**; spends Connects once; 402 if balance too low |
| GET | `/proposals/{id}` | |
| GET | `/threads`, `/threads/{id}/messages` | client replies appear when their simulated time arrives |
| POST | `/threads/{id}/messages` | rejects contact details with 422 |
| GET | `/events?since=<ISO>` | `viewed / replied / interview / hired / lost`; `since` is exclusive, use `next_since` |
| GET | `/policy` | current platform policy and version |
| POST | `/admin/tick?minutes=` | admin token: advance simulated time, release due jobs |
| GET | `/admin/decisions` | admin token: simulated-client decisions **with reasons** (for evals only) |

## Behaviour

- **Rate limit:** token bucket per user, `GIGSIM_RATE_LIMIT_PER_MIN` (default 60) -> `429` + `Retry-After`.
- **Chaos:** `GIGSIM_ERROR_RATE` (default 3%) of requests get `503`. For submits, a share
  (`GIGSIM_LOST_RESPONSE_SHARE`) is **processed first and then answered with `502`** — the
  client cannot tell whether it worked. Retrying with the same `Idempotency-Key` replays the
  stored response: one submission, one Connects charge.
- **Clock:** simulated time = offset + wall time x `GIGSIM_TIME_SCALE` (default: 1 simulated
  minute per second). Held-back jobs (`release_minute > 0`) are released by a background loop
  every `GIGSIM_RELEASE_INTERVAL_MIN` minutes, or immediately on `/admin/tick`.
- **Simulated clients** (`client_sim.py`, weights in `config.yaml`): must-have skill coverage,
  price vs a hidden ceiling, generic-opening dislike, specific evidence, hidden reply propensity
  and a rubric score (deterministic heuristic by default; seeded LLM via `rubric.kind: llm`).
  Outcomes are seeded by (seed, user, job, proposal text, bid): the same submission always gets
  the same result. Scam clients reply fast and ask to move off-platform.
- **Policy versions:** `policy/v1.yaml` (default) and `policy/v2.yaml` (the change request:
  Connects x2 for jobs with more than 20 proposals; no external links). Select with
  `GIGSIM_POLICY_VERSION`.
