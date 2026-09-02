SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PYTHON ?= python3
VENV ?= .venv
VENV_BIN := $(VENV)/bin
COMPOSE ?= docker compose
API_URL ?= http://localhost:8000
WEB_URL ?= http://localhost:8080

.PHONY: help install install-dev web-install dvc-install dvc-repro dvc-metrics lint format-check \
	format typecheck test test-integration evaluate ci compose-config up lite down clean logs ps \
	smoke load-test terraform-fmt terraform-validate

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; printf "CatalogOps development commands\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(VENV_BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install --upgrade pip

install: $(VENV_BIN)/python ## Install API and matcher runtime dependencies
	$(VENV_BIN)/pip install -r apps/api/requirements.txt

install-dev: install ## Install Python development and test tooling
	$(VENV_BIN)/pip install -r requirements-dev.txt

web-install: ## Install the locked web dependencies
	npm --prefix apps/web ci

dvc-install: $(VENV_BIN)/python ## Optionally install DVC; normal demo startup does not require it
	$(VENV_BIN)/pip install "dvc[s3]>=3.59,<4.0"

dvc-repro: install dvc-install ## Reproduce the tracked sample training/evaluation pipeline
	PATH="$(abspath $(VENV_BIN)):$$PATH" $(VENV_BIN)/dvc repro

dvc-metrics: dvc-install ## Show tracked evaluation metrics
	$(VENV_BIN)/dvc metrics show

lint: install-dev ## Run Python lint checks
	$(VENV_BIN)/ruff check apps services pipelines evaluation tests scripts

format-check: install-dev ## Check Python formatting without changing files
	$(VENV_BIN)/ruff format --check apps services pipelines evaluation tests scripts

format: install-dev ## Format and apply safe lint fixes
	$(VENV_BIN)/ruff format apps services pipelines evaluation tests scripts
	$(VENV_BIN)/ruff check --fix apps services pipelines evaluation tests scripts

typecheck: install-dev web-install ## Type-check Python and TypeScript
	$(VENV_BIN)/mypy apps/api services pipelines evaluation
	npm --prefix apps/web run typecheck

test: install-dev ## Run unit tests with branch coverage
	$(VENV_BIN)/pytest -m "not integration" \
		--cov=apps.api \
		--cov=services.matcher \
		--cov-branch \
		--cov-report=term-missing \
		--cov-report=xml \
		--cov-fail-under=70

test-integration: install-dev ## Run tests that require local infrastructure
	$(VENV_BIN)/pytest -m integration -v

evaluate: install ## Run the reproducible sample benchmark and threshold gate
	$(VENV_BIN)/python -m evaluation.run \
		--catalog data/sample/catalog.csv \
		--offers data/sample/offers.jsonl \
		--output evaluation/results/sample-baseline.json \
		--check-thresholds

ci: lint format-check typecheck test evaluate ## Run all local CI-equivalent gates
	npm --prefix apps/web run build

compose-config: ## Validate the resolved Compose configuration
	$(COMPOSE) config --quiet

up: ## Build and start the complete local stack at localhost:8080
	$(COMPOSE) up --build --wait

lite: ## Start only Postgres, Redis, and the baseline API at localhost:8000
	CATALOGOPS_MODEL_BACKEND=baseline $(COMPOSE) up --build --wait postgres redis api

down: ## Stop local services without deleting persistent data
	$(COMPOSE) down --remove-orphans

clean: ## Stop services and delete project-owned Docker volumes
	$(COMPOSE) down --volumes --remove-orphans

logs: ## Follow API and web logs
	$(COMPOSE) logs --follow api web

ps: ## Show local service health
	$(COMPOSE) ps

smoke: ## Verify API, OpenAPI, and web endpoints
	./scripts/smoke-test.sh "$(API_URL)" "$(WEB_URL)"

load-test: ## Run a bounded local API load test (override URL/REQUESTS/CONCURRENCY)
	$(PYTHON) scripts/load_test.py \
		--url "$(API_URL)/health" \
		--requests "$${REQUESTS:-500}" \
		--concurrency "$${CONCURRENCY:-20}"

terraform-fmt: ## Check Terraform formatting
	terraform -chdir=infra/terraform fmt -check -recursive

terraform-validate: ## Initialize without a backend and validate Terraform
	terraform -chdir=infra/terraform init -backend=false
	terraform -chdir=infra/terraform validate
