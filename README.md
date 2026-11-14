# GigBid

Multi-agent freelancer copilot (AI-4016 R&D Assignment II). LangGraph agents find freelance jobs,
judge whether they are worth bidding on, write proposals grounded in portfolio evidence and manage
client conversations. **A human approves every proposal, message and Connects spend.**

> Work in progress. This README is filled in during Phase 12 with the demo, results tables and live link.

## Quick start (development)

Prerequisites: Docker Desktop, uv, Node 22, GNU make (run `make` from Git Bash on Windows).

```bash
cp .env.example .env        # then edit values
uv sync                     # Python 3.12 env with pinned deps
(cd apps/web && npm ci)     # web deps
make up                     # postgres+pgvector, redis, phoenix (waits until healthy)
make lint && make test
```

Phoenix UI: http://localhost:6006

See `docs/BUILD_SPEC.pdf` for the phased plan and `CLAUDE.md` for project rules.
