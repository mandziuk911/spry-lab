SHELL := /bin/bash
.DEFAULT_GOAL := help
AWS_PROFILE ?= $(if $(AWS_SESSION_TOKEN),,spry)

.PHONY: help start up down logs ps test test-back test-front lint format aws-check deploy deploy-backend deploy-frontend aws-outputs

help: ## Show commands; deploys use temporary aws login credentials, never .env keys
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

start: ## Build and start the local app at http://localhost:5173
	docker compose up -d --build --wait

up: start ## Start local services

down: ## Stop local services without deleting database data
	docker compose down

logs: ## Follow local logs (Ctrl+C exits log viewing)
	docker compose logs -f $(SERVICE)

ps: ## Show local service status
	docker compose ps

test: ## Run backend and frontend tests
	$(MAKE) test-back
	$(MAKE) test-front

test-back: ## Run backend tests in Docker against dedicated spry_test, not app data
	docker compose up -d --wait db
	@docker compose exec -T db psql -U spry -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='spry_test'" | grep -q 1 || docker compose exec -T db psql -U spry -d postgres -c 'CREATE DATABASE spry_test'
	docker compose run --rm --no-deps -e TEST_DATABASE_URL=postgresql+psycopg://spry:spry@db:5432/spry_test -v "$(CURDIR)/back/tests:/app/tests:ro" backend uv run --frozen pytest /app/tests

test-front: ## Run frontend tests with installed npm dependencies
	cd front && npm test

lint: ## Check backend and frontend style (host uv and npm required)
	cd back && uv run --frozen ruff check . && uv run --frozen ruff format --check .
	cd front && npm run lint && npm run format:check

format: ## Format backend/frontend source (host uv and npm required)
	cd back && uv run --frozen ruff format .
	cd front && npm run format

aws-check: ## Verify expected AWS account, ACTIVE Free plan and sufficient credits
	AWS_PROFILE=$(AWS_PROFILE) python3 infra/scripts/deploy.py check

deploy: ## Deploy backend then frontend; consumes Free-plan credits
	$(MAKE) deploy-backend
	$(MAKE) deploy-frontend

deploy-backend: ## Push exact SHA image, provision ECS/RDS, migrate once and enable service
	AWS_PROFILE=$(AWS_PROFILE) python3 infra/scripts/deploy.py backend

deploy-frontend: ## Provision private S3/CloudFront, publish same-origin frontend and wait
	AWS_PROFILE=$(AWS_PROFILE) python3 infra/scripts/deploy.py frontend

aws-outputs: ## Show public AWS URLs and deployed SHAs without secrets
	AWS_PROFILE=$(AWS_PROFILE) python3 infra/scripts/deploy.py outputs
