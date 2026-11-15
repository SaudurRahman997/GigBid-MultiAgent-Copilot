# ADR 0003: GigSim design

- Status: accepted (GigSim frozen at this point; hash in `gigsim/FROZEN.sha256`)
- Date: 2026-11-15

## Context
GigBid needs a marketplace to develop and be graded against that behaves like the real one
(rate limits, flaky responses, Connects, clients who answer late or not at all) but is
reproducible and cheap.

## Decisions
1. **FastAPI + SQLAlchemy Core on Postgres, own schema `gigsim`.** Tests run the same code on
   SQLite (schema name translated away), so the 20+ behaviour tests need no Docker.
2. **Hidden data stays server-side.** Gold labels and client preferences live in separate
   columns; no public endpoint returns them. Evals read decisions through `/admin/*` with a
   separate admin token that agents never receive.
3. **Simulated time.** A persisted clock (`offset + wall x time_scale`) drives job releases,
   event due-times and message visibility. `time_scale=0` + `/admin/tick` makes tests and evals
   deterministic and fast.
4. **Idempotency is tested against the hard case.** Some simulated 5xx on submit happen *after*
   the submission is committed ("lost response"). The `Idempotency-Key` table stores the first
   response per (user, key) and replays it, so a retry never double-submits or double-charges.
5. **Simulated client = transparent scoring model + rubric.** Features (must-have coverage,
   price vs hidden ceiling, generic opening, specific evidence, reply propensity) plus a rubric
   score feed a logistic score; the RNG is seeded by (seed, user, job, text, bid). The default
   rubric is a deterministic heuristic so seeded runs are identical without API keys; a seeded,
   cached LLM rubric (OpenAI-compatible endpoint) is available via `gigsim/config.yaml`.
   Calibrated so tailored, evidence-backed proposals get far more replies than generic ones,
   while nothing is guaranteed (`tests/unit/test_gigsim_calibration.py`).
6. **Policy versions as data** (`gigsim/policy/v1.yaml`, `v2.yaml`) so the change request is a
   config switch on the simulator side.
7. **Frozen.** `scripts/check_gigsim_frozen.py` (CI) fails when `gigsim/` changes without
   updating `FROZEN.sha256`; any deliberate change needs a new ADR.

## Consequences
- Rate limiter is in-process (one GigSim instance); fine for a simulator, noted as a limitation.
- Outcomes depend on proposal text features GigSim can observe, not on the freelancer's real
  skill; the evals report reply rates as "GigSim reply rate", not real-world performance.
