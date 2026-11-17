# GigBid task runner. Run from Git Bash or any POSIX shell.
.DEFAULT_GOAL := help
UV      ?= uv
COMPOSE := docker compose -f infra/docker-compose.yml $(if $(wildcard .env),--env-file .env,)

.PHONY: help data validate-data local-stack snapshots tools-doc proposal-demo gigsim gigsim-check gigsim-freeze dev up down logs ps test test-integration lint fmt typecheck eval seed demo openapi check-prompts web-dev api worker

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*## ' Makefile | awk 'BEGIN{FS=":.*## "}{printf "  %-14s %s\n", $$1, $$2}'

up: ## start docker services in the background and wait until healthy
	$(COMPOSE) up -d --wait

down: ## stop docker services (keeps volumes)
	$(COMPOSE) down

ps: ## show service status
	$(COMPOSE) ps

logs: ## follow service logs
	$(COMPOSE) logs -f

dev: up ## start the dev stack (api/web/worker are added in later phases)
	@echo "Postgres :5432  Redis :6379  Phoenix UI http://localhost:6006"

lint: check-prompts ## ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## auto-format Python
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck: ## mypy (lenient)
	$(UV) run mypy agent mcp_servers rag gigsim apps/api evals scripts

check-prompts: ## fail if prompt text is hard-coded outside agent/prompts/
	$(UV) run python scripts/check_prompts.py

test: ## unit + contract tests (integration tests need `make up`)
	$(UV) run pytest -m "not integration"

test-integration: ## tests that need docker services
	$(UV) run pytest -m integration

eval: ## run all eval runners -> evals/results/*.json (Phase 4/11)
	@echo "eval: not implemented yet (Phase 4/11)"

data: ## download Kaggle datasets (needs KAGGLE_API_TOKEN in .env) and profile them
	bash scripts/download_kaggle.sh
	$(UV) run python -m data.generators.profile_datasets

seed: ## regenerate processed + synthetic data deterministically (needs `make data` once)
	@if [ -d data/raw/asaniczka__upwork-job-postings-dataset-2024-50k-records ]; then \
		$(UV) run python -m data.generators.preprocess; \
	else echo "data/raw missing: skipping preprocess (run 'make data' first)"; fi
	$(UV) run python -m data.generators.seed

validate-data: ## check synthetic/provenance on every record, dev-set gold fields, planted rates
	$(UV) run python -m data.generators.validate

demo: ## end-to-end demo (Phase 7+)
	@echo "demo: not implemented yet (Phase 7)"

openapi: ## export FastAPI schema and regenerate the TS client (Phase 6)
	$(UV) run python -m scripts.export_openapi
	cd apps/web && npx openapi-typescript ../api/openapi.json -o src/lib/api/schema.d.ts

api: ## run the API with auto-reload (http://localhost:8000/docs)
	$(UV) run uvicorn apps.api.main:app --reload --port 8000

worker: ## run the Arq worker (saved searches, graph runs, message polling; needs REDIS_URL)
	$(UV) run arq apps.worker.main.WorkerSettings

gigsim: ## run GigSim locally on SQLite with auto-reload (http://localhost:8100/docs)
	GIGSIM_DATABASE_URL=sqlite:///./gigsim-dev.db $(UV) run uvicorn gigsim.app:create_app --factory --reload --port 8100

gigsim-check: ## fail if gigsim/ changed without updating gigsim/FROZEN.sha256
	$(UV) run python scripts/check_gigsim_frozen.py

gigsim-freeze: ## record the current gigsim/ hash (deliberate change: also add an ADR)
	$(UV) run python scripts/check_gigsim_frozen.py --update

local-stack: ## run GigSim + MCP servers locally on SQLite (no Docker)
	$(UV) run python scripts/run_local_stack.py

snapshots: ## regenerate MCP schema snapshots after a deliberate signature change
	UPDATE_SNAPSHOTS=1 $(UV) run pytest tests/contract -q

tools-doc: ## regenerate docs/TOOLS.md from the snapshots
	$(UV) run python scripts/gen_tools_doc.py

proposal-demo: ## one agent drafts one grounded proposal via MCP (needs make up or make local-stack)
	$(UV) run python scripts/single_agent_proposal.py --persona ai_ml

web-dev: ## run the Next.js dev server
	cd apps/web && npm run dev
