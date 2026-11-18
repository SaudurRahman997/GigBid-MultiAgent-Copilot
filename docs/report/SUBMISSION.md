# GigBid: submission index

AI-4016 R&D Assignment II - multi-agent freelancer copilot

**Roll number:** 23i-0540

This index lists every deliverable and every graded item with a link to the evidence. Every number
below is copied from a result file written by a runner in `evals/runners/` (the source is named next
to it). All data is synthetic; no real client data is used.

## 1. Deliverables

| Deliverable | Notes | Link |
|---|---|---|
| Deployed web application | Live; sign in with the reviewer account | https://gigbid-beta.vercel.app |
| Deployed API (health check) | Returns ok when the backend is up | https://gigbid-beta.vercel.app/api/health |
| Public GitHub repository | Complete source, tests, results, docs | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot |
| R&D report (PDF, 7 pages) | Also uploaded to Classroom | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/report/GigBid_Report.pdf |
| Portfolio MCP server (published) | Docker and uv run commands, client config | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/mcp_servers/portfolio |
| Technical write-up | | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/WRITEUP.md |
| 3-minute demo video | Link added on the submission page | (submission page) |
| All results in one table | Generated from evals/results/*.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/RESULTS.md |
| CI runs (tests, lint, E2E, eval gate) | GitHub Actions | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/actions |
| Source code ZIP | Uploaded to Classroom (git archive of main) | (Classroom upload) |
| Reviewer login credentials | Private Classroom comment only, never in the repository | (private comment) |

## 2. How to check the live app (about 3 minutes)

1. Open https://gigbid-beta.vercel.app and sign in with the reviewer account from the private comment (the first request after a quiet period can take a few seconds).
2. Inbox -> open job **gj_16671e658f** -> Analyse this job. The run timeline shows every agent step; the job stops at the approval panel (price $320, inside the market band). Hover a sentence of the draft to see its evidence; Approve -> the pipeline shows it as submitted with an idempotency key.
3. Open job **gj_08aacce229** -> Analyse: skipped as a scam (upfront fee), no draft written.
4. Open job **gj_d252c3aa34** -> Analyse: the hidden "claim 10 years of experience" instruction is flagged as a prompt injection and the letter does not follow it.
5. Settings: autonomy, budgets, saved searches and the memory viewer (view and delete).

The hosted demo runs the API as one serverless function with the in-process tool layer (same tool names and results as the MCP servers); the full stack (GigSim, three MCP servers, Postgres, Redis, Phoenix, worker) starts with docker compose. Details: https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/DEPLOY.md

## 3. Definition of Done (BUILD_SPEC section 10) with evidence

| # | Item | Status | Evidence | Link |
|---|---|---|---|---|
| 1 | docker compose starts web, api, worker, MCP servers, GigSim, Postgres, Redis, Phoenix, Ollama | Partial: all except web and Ollama | infra/docker-compose.yml | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/infra/docker-compose.yml |
| 2 | Public URL with reviewer login | Done | Vercel (web + API); credentials in private comment | https://gigbid-beta.vercel.app |
| 3 | Three own MCP servers: schemas, annotations, idempotency, auth, audit log, tests, snapshots | Done (Inspector screenshots pending) | mcp_servers/, contract snapshots, docs/TOOLS.md | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/TOOLS.md |
| 4 | Upwork adapter behind the same port; GitHub MCP for repo ingestion; trust rationale | Partial: port + stub adapter, GitHub ingestion, TOOLS.md; no live Upwork | docs/TOOLS.md, ADR 0004 | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/adr/0004-mcp-tool-layer.md |
| 5 | V0 + 4 or more variants incl. V1, V2, V3, V8; claim verification; calibrated judge (kappa) | Done except kappa (needs 30 human labels) | rag/dev/*.json, verify_eval.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/evals/results/rag/dev |
| 6 | Bid and conversation graphs: parallel Send, critic loop at most 2, compliance block, interrupts, budgets | Done | agent/graphs/, tests/unit/test_graphs.py | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/agent/graphs |
| 7 | Crash-and-resume: approved proposal submitted exactly once | Done (tested) | lost-response and crash tests; API 409 on second approval | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/tests/unit/test_graphs.py |
| 8 | Style and outcome memory with promotion rules; memory viewer with delete | Done | agent/memory/, Settings page | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/agent/memory |
| 9 | All 9 screens, SSE, evidence hover, approvals resume graph, mobile + keyboard, 5 Playwright specs | Done | apps/web, 5 specs (6 tests) pass locally and in CI | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/apps/web/e2e |
| 10 | Worker schedules; CI with eval gates; end-to-end trace ids; injection ASR before/after; PII masking | Done | apps/worker, eval.yml, trace test, injection/asr.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/RUNBOOK.md |
| 11 | Budgets declared and measured; one optimisation documented | Done | budgets/budgets.json; report section 7 | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/budgets/budgets.json |
| 12 | R&D A, B, C tables; failure taxonomy; change-request diff | Done | report section 4 and 6; FAILURES.md; ADR 0006 | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/FAILURES.md |
| 13 | Extension documented and measured | Done | docs/EXTENSION.md, extension/ab.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/EXTENSION.md |
| 14 | README, report (10 pages max), demo video, write-up, published MCP server, AI_USAGE.md | Done except the video (submission page) | README, report, AI_USAGE | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/AI_USAGE.md |

## 4. Results by study

| Study | Headline result | Source | Link |
|---|---|---|---|
| R&D B: retrieval (6 variants) | V2 hybrid best and cheapest: Recall@5 0.216, MRR 0.402, p95 19 ms; reranking cost 10.9 s p95 without gain; corrective RAG refused correctly on 87.4% of no-evidence jobs | rag/dev/*.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/evals/results/rag/dev |
| R&D B: ablation | Removing per-requirement decomposition gave the best configuration (Recall@5 0.282, MRR 0.488) | rag/dev/ablation.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/rag/dev/ablation.json |
| Claim verification | Accuracy 0.988, macro-F1 0.985; unsupported claims 0.325 -> 0.014 after repair | verify/verify_eval.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/verify/verify_eval.json |
| Decisions (600 jobs) | Graph bid/skip macro-F1 0.870 vs keyword 0.696; scam recall 1.000; price in band 0.902 | decision/*.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/evals/results/decision |
| R&D C: is multi-agent worth it? (50 jobs) | Graph 0.760 vs single ReAct agent 0.548 vs supervisor 0.517 macro-F1; reply rate 0.455 / 0.296 / 0.167; graph uses 59% fewer tokens than the single agent; the single agent prices better (0.824 vs 0.632) | multiagent/*.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/evals/results/multiagent |
| R&D A: tool granularity (40 tasks) | Argument accuracy: fine tools 0.85, coarse tools 0.40, rewritten descriptions 0.95 | tools/granularity.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/tools/granularity.json |
| Model comparison (50 jobs) | llama3.2:3b 0.760 vs qwen2.5:1.5b 0.643 vs qwen2.5:3b 0.480 macro-F1; 40 tokens/s on a laptop GPU; $0 API cost | models/summary.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/models/summary.json |
| Injection defence (34 jobs) | Attack success rate 0.529 (no defences) -> 0.029 (prompt defences) -> 0.000 (full pipeline) | injection/asr.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/injection/asr.json |
| Budgets | Rules mode p95 2.4 s per job (within 20 s); local 3B LLM p95 79 s per job (over budget) | budgets/budgets.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/budgets/budgets.json |
| Failure analysis (600 jobs) | 100 mispriced -> 25 with clamp-to-band (now default); client-floor fix did not help wrong skips (cause: skill naming); 81 -> 68 missed evidence with a 4th evidence sentence | failures/failures.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/FAILURES.md |
| Change request (platform policy v2) | Absorbed through config and policy pack only: 3 files, 7 lines, 2 min 1 s | ADR 0006 | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/adr/0006-change-request-policy-v2.md |
| Extension X2: proposal A/B (267 paired jobs) | Outcome-first letters 0.513 vs evidence-first 0.446 reply rate; McNemar p = 0.105 (not significant) | extension/ab.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/EXTENSION.md |
| GigSim outcomes | Grounded proposals (V2) 0.422 vs generic letter 0.111 reply rate | gigsim/outcomes.json | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/results/gigsim/outcomes.json |

## 5. Engineering evidence

| Item | Evidence | Link |
|---|---|---|
| Tests | 207 unit and contract tests (make test) + 5 Playwright specs (make e2e) | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/tests |
| CI eval gate | 30-job smoke eval on every PR: macro-F1 0.80 (min 0.75), unsupported claims 0.0 (max 0.3) | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/.github/workflows/eval.yml |
| Architecture | Components, graphs, cross-cutting concerns | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/ARCHITECTURE.md |
| Decisions (ADRs 0001-0007) | Tech stack, data, GigSim, MCP layer, RAG, change request, frozen hash | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/tree/main/docs/adr |
| Runbook | Services, worker idempotency, polling intervals and why | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/RUNBOOK.md |
| Data card | Sources, licences, synthetic generators, gold labels | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/DATA_CARD.md |
| Hypotheses (written before running) | R&D B hypotheses | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/evals/HYPOTHESES.md |
| AI usage | Tool used, files, mistakes caught | https://github.com/SaudurRahman997/GigBid-MultiAgent-Copilot/blob/main/docs/AI_USAGE.md |

## 6. Not finished (stated honestly)

- **Judge calibration (Cohen's kappa):** the label sheet and runner are ready; the 30 human labels are not done yet.
- **Live Upwork adapter:** only the port and a stub; all evaluation uses GigSim.
- **docker compose:** the web app and Ollama are not compose services (the web runs on Vercel or `make web-dev`).
- **MCP Inspector screenshots:** not yet in docs/images.
- **CI secret scan:** the gitleaks job reports a finding in the history that is still being investigated; all other CI jobs pass.
- With every node on a local 3B model the graph is over its latency budget, and the extension's improvement is not statistically significant.
