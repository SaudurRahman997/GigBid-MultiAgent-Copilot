# GigBid — instructions for Claude Code

## Source of truth
- docs/BUILD_SPEC.pdf (phases in section 7). Work one phase at a time.
- The assignment PDF in docs/assignment/ for exact requirements.

## Always
- Show a plan before writing code for a phase; wait for my OK.
- Keep the required directory tree; never rename listed paths.
- Prompts only in agent/prompts/<node>.vN.md. Models, thresholds, budgets,
  rules only in agent/config.yaml or data/policy_pack/.
- Agents use MCP tools only (no direct DB/HTTP/file access from nodes).
- Pydantic models for every hand-off and every MCP tool input/output.
- Every write tool: idempotency_key + dry_run.
- Mark every synthetic record: synthetic=true, provenance=<generator>@<sha>.
- Tests with every feature; run `make test` before saying a task is done.
- Small commits with clear messages.
- Pin dependency versions; check current docs for LangGraph, MCP SDK,
  langchain-mcp-adapters and Upwork MCP before using their APIs.

## Never
- Invent or edit numbers. Results come only from evals/runners/* writing
  evals/results/*.json.
- Commit secrets, .env, tokens, the held-out test set, or real client data.
- Scrape websites, automate browsers, or use session cookies.
- Auto-send anything. Every proposal/message/Connects spend needs a
  human approval via interrupt().
- Modify gigsim/ after Phase 2 without updating gigsim/FROZEN.sha256 and
  noting why in docs/adr/.

## Commands
make dev | make test | make eval | make seed | make demo | make lint | make openapi

## Environment notes (Windows dev box)
- Python is pinned to 3.12 via `.python-version`; use `uv run ...`.
- Run `make` from Git Bash (the Makefile uses POSIX sh).
