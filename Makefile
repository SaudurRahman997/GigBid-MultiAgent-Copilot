# GigBid task runner. Run from Git Bash or any POSIX shell.
.DEFAULT_GOAL := help
UV      ?= uv
COMPOSE := docker compose -f infra/docker-compose.yml $(if $(wildcard .env),--env-file .env,)

.PHONY: help data dev up down logs ps test test-integration lint fmt typecheck eval seed demo openapi check-prompts web-dev

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
	$(UV) run python -m data.generators.preprocess

demo: ## end-to-end demo (Phase 7+)
	@echo "demo: not implemented yet (Phase 7)"

openapi: ## export FastAPI schema and regenerate the TS client (Phase 6)
	@echo "openapi: not implemented yet (Phase 6)"

web-dev: ## run the Next.js dev server
	cd apps/web && npm run dev
