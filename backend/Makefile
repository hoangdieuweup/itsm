.PHONY: help up down logs migrate seed worker-logs

ENV ?= stg

ifeq ($(ENV),prod)
COMPOSE_FILE := docker-compose.prod.yml
else
COMPOSE_FILE := docker-compose.yml
endif

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-15s %s\n", $$1, $$2}'

up: ## Build and start (ENV=prod for production)
	docker compose -f $(COMPOSE_FILE) up -d --build

down: ## Stop and remove containers
	docker compose -f $(COMPOSE_FILE) down

logs: ## Tail the API's logs
	docker compose -f $(COMPOSE_FILE) logs -f api

migrate: ## Run Alembic migrations
	docker compose -f $(COMPOSE_FILE) exec api alembic upgrade head

seed: ## Run every seed script under app/seeds/
	docker compose -f $(COMPOSE_FILE) exec api sh -c "for m in app/seeds/seed_*.py; do python -m $$(echo $$m | sed 's#/#.#g; s#\.py##'); done"

worker-logs: ## Tail the worker's logs
	docker compose -f $(COMPOSE_FILE) logs -f worker
