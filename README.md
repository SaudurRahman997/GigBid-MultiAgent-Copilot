# GigBid — multi-agent freelancer copilot

GigBid reads freelance job posts, decides **bid / skip / watch**, writes proposals grounded in the
freelancer's own portfolio evidence, and handles client messages. **A human approves every
proposal, message and Connects spend** (LangGraph `interrupt()`); nothing is ever auto-sent.

AI-4016 R&D Assignment II.

| | |
|---|---|
| R&D report | [`docs/report/GigBid_Report.pdf`](docs/report/GigBid_Report.pdf) (source: [`REPORT.md`](docs/report/REPORT.md)) |
| All results | [`evals/results/RESULTS.md`](evals/results/RESULTS.md) — generated from `evals/results/*.json` |
| Portfolio MCP server | [`mcp_servers/portfolio/`](mcp_servers/portfolio/README.md) — Docker / uv run instructions |
| Tool catalogue | [`docs/TOOLS.md`](docs/TOOLS.md) |
| Live demo | https://gigbid-beta.vercel.app (web and API both on Vercel; API in single-process demo mode, see docs/DEPLOY.md) |

## Headline results (dev set, synthetic data)

| What | Result | Source |
|---|---|---|
| Bid/skip macro-F1, LangGraph multi-agent vs keyword baseline (price in market band 0.902 vs 0.652) | **0.870** vs 0.696 | `evals/results/decision/*.json` |
| Scam recall / precision (graph) | 1.000 / 0.905 | `evals/results/decision/graph.json` |
| Unsupported claims in drafts, before → after verification + repair | 0.325 → **0.014** | `evals/results/verify/verify_eval.json` |
| Best retrieval variant (V2 hybrid BM25 + dense): Recall@5 / MRR | 0.216 / 0.402 | `evals/results/rag/dev/v2_hybrid.json` |
| Simulated reply rate, grounded (V2) vs generic proposal | 0.422 vs 0.111 | `evals/results/gigsim/outcomes.json` |
| R&D C: graph vs single ReAct agent vs supervisor (50 jobs, llama3.2:3b), bid/skip macro-F1 | **0.760** vs 0.548 vs 0.517 (graph uses 59% fewer tokens than the single agent) | `evals/results/multiagent/*.json` |
| R&D A: argument accuracy, fine tools vs coarse tools vs rewritten descriptions (40 tasks) | 0.85 vs 0.40 vs **0.95** | `evals/results/tools/granularity.json` |
| Prompt-injection attack success rate: no defences → prompt defences → full pipeline (34 jobs) | 0.529 → 0.029 → **0.000** | `evals/results/injection/asr.json` |
| Extension X2: reply rate, outcome-first vs evidence-first letters (267 paired jobs) | 0.513 vs 0.446, McNemar p = 0.105 (not significant) | `evals/results/extension/ab.json` |
| Platform policy change absorbed by config + policy pack only | 3 files, 7 lines, 2 min 1 s | `docs/adr/0006-change-request-policy-v2.md` |

## Architecture

```
 Next.js web (9 screens, SSE)  ──►  FastAPI (auth, tenants, approvals, SSE)
                                         │  LangGraph (Postgres checkpointer + store)
                                         ▼
  bid graph:  scout ─► [Job Analyst ‖ Risk Assessor ‖ Fit Matcher] ─► decide ─► pricing
              ─► writer ─► verify claims ─► critic (≤2 rounds) ─► compliance
              ─► approval interrupt ─► submit (idempotent, exactly-once) ─► record outcome
  conversation graph: message ─► intent ─► slots / reply ─► compliance ─► approval ─► send
                                         │  MCP (Streamable HTTP, bearer auth, allowlists)
                                         ▼
   Portfolio MCP  ·  Marketplace MCP  ·  Workspace MCP   ──►  GigSim marketplace simulator
                         Postgres 16 + pgvector · Redis · Arize Phoenix
```

Design decisions are recorded in [`docs/adr/`](docs/adr/).

## Run it

Prerequisites: Docker Desktop, [uv](https://docs.astral.sh/uv/), Node 22, GNU make (Git Bash on Windows).

```bash
cp .env.example .env          # set JWT_SECRET, REVIEWER_EMAIL/PASSWORD; GROQ_API_KEY optional
uv sync && (cd apps/web && npm ci)
make up                       # postgres, redis, phoenix, gigsim, 3 MCP servers
make seed                     # deterministic synthetic data (needs `make data` once for Kaggle)
make api                      # API on http://localhost:8000/docs
make web-dev                  # web on http://localhost:3000
make test                     # 183 unit + contract tests
make eval                     # re-runs every evaluation -> evals/results/*.json
```

Agents run in deterministic **rules** mode by default; set `GIGBID_AGENT_MODE=llm` (and a Groq key
or a local Ollama model) to use LLM nodes, which fall back to rules per node on error.

## Repository map

| Path | What |
|---|---|
| `agent/` | LangGraph graphs, nodes, prompts (`prompts/<node>.v1.md`), config, memory |
| `mcp_servers/` | portfolio, marketplace, workspace MCP servers |
| `gigsim/` | marketplace simulator (frozen; hash in `gigsim/FROZEN.sha256`) |
| `rag/` | ingestion, chunking, pgvector index, retrieval variants V0–V4, V8, claim verification |
| `apps/api/`, `apps/web/`, `apps/worker/` | FastAPI backend, Next.js frontend (Playwright specs in `apps/web/e2e/`), Arq worker |
| `evals/` | runners, metrics, hypotheses, results |
| `data/` | generators, personas, policy pack, dev set (held-out set is not committed) |

## Pinned versions

Python 3.12 · LangGraph 1.2.22 · langgraph-checkpoint-postgres 3.2.1 · MCP SDK 1.30 ·
langchain-mcp-adapters 0.3.2 · FastAPI 0.163.0 · Next.js 16.4.3 · React 19.3.0 · Postgres 16 + pgvector.
Exact pins: `pyproject.toml` + `uv.lock`, `apps/web/package-lock.json`.

## Status

Done: data and GigSim, three MCP servers, RAG study (6 variants + ablation), claim verification,
bid and conversation graphs with exactly-once submit, memory, API, web UI, worker (Arq, saved
searches, idempotent), end-to-end trace ids, R&D A, B and C, model comparison, injection ASR,
budgets, failure analysis, change request (ADR 0006), extension X2 (`docs/EXTENSION.md`), 5 Playwright
specs (`make e2e`), CI with an eval gate (`.github/workflows/eval.yml`), deployment (web and API on
Vercel, `docs/DEPLOY.md`), runbook (`docs/RUNBOOK.md`).
Not done: judge calibration (kappa; needs the 30 human-labelled proposals), the live Upwork adapter.

AI assistance is disclosed in [`docs/AI_USAGE.md`](docs/AI_USAGE.md).
