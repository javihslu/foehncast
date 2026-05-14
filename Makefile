.PHONY: help install install-docs install-feast lock lint format test test-feature check docs-build docs-serve bootstrap-local smoke-local-evaluator bootstrap-gcp terraform-remote smoke-bootstrap-only compose-up compose-down compose-ps compose-logs dev-build dev-rebuild dev-shell notebook-server notebook-stop feast-prepare

ROOT_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
DATASET ?= train
JUPYTER_TOKEN ?= foehncast-local
TF_REMOTE_ARGS ?= plan
SMOKE_BOOTSTRAP_ARGS ?=
LOCAL_ONLY_COMPOSE := COMPOSE_PROFILES=local-only docker compose

help:  ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-24s %s\n", $$1, $$2}'

install:  ## Install default dependencies with uv
	cd $(ROOT_DIR) && uv sync

install-docs:  ## Install docs dependencies with uv
	cd $(ROOT_DIR) && uv sync --group docs

install-feast:  ## Install Feast dependencies with uv
	cd $(ROOT_DIR) && uv sync --group feast

lock:  ## Refresh uv.lock
	cd $(ROOT_DIR) && uv lock

lint:  ## Lint the repository
	cd $(ROOT_DIR) && uv run ruff check .

format:  ## Format the repository
	cd $(ROOT_DIR) && uv run ruff format .

test:  ## Run the full test suite
	cd $(ROOT_DIR) && uv run pytest -q

test-feature:  ## Run focused feature-pipeline and orchestration tests
	cd $(ROOT_DIR) && uv run pytest tests/test_ingest.py tests/test_engineer.py tests/test_validate.py tests/test_store.py tests/test_feast_export.py tests/test_orchestration.py tests/test_dags.py -q

check: lint test  ## Run lint and the full test suite

docs-build:  ## Build the documentation site
	cd $(ROOT_DIR) && uv sync --group docs && uv run mkdocs build -f docs/mkdocs.yml --strict

docs-serve:  ## Serve the documentation site locally
	cd $(ROOT_DIR) && uv sync --group docs && uv run mkdocs serve -f docs/mkdocs.yml

bootstrap-local:  ## Rebuild and validate the GCP-free local evaluator stack from scratch
	cd $(ROOT_DIR) && ./scripts/bootstrap-local.sh

smoke-local-evaluator:  ## Run the bounded local evaluator smoke and tear the stack down on exit
	cd $(ROOT_DIR) && bash scripts/smoke-local-evaluator.sh

bootstrap-gcp:  ## Run the cloud-operator GCP bootstrap (prefer Cloud Shell)
	cd $(ROOT_DIR) && ./scripts/bootstrap-gcp.sh

terraform-remote:  ## Trigger the remote Terraform workflow with TF_REMOTE_ARGS='<command> [flags]'
	cd $(ROOT_DIR) && ./scripts/terraform-remote.sh $(TF_REMOTE_ARGS)

smoke-bootstrap-only:  ## Run the disposable bootstrap-only smoke driver with SMOKE_BOOTSTRAP_ARGS='--repo owner/repo'
	cd $(ROOT_DIR) && ./scripts/smoke-bootstrap-only.sh $(SMOKE_BOOTSTRAP_ARGS)

compose-up:  ## Start the default local runtime stack
	cd $(ROOT_DIR) && docker compose up -d

compose-down:  ## Stop and remove the local compose stack
	cd $(ROOT_DIR) && docker compose down

compose-ps:  ## List compose services
	cd $(ROOT_DIR) && docker compose ps

compose-logs:  ## Tail compose logs
	cd $(ROOT_DIR) && docker compose logs -f

dev-build:  ## Rebuild the opt-in development_env image
	cd $(ROOT_DIR) && $(LOCAL_ONLY_COMPOSE) build development_env

dev-rebuild:  ## Rebuild and recreate the opt-in development_env container
	cd $(ROOT_DIR) && $(LOCAL_ONLY_COMPOSE) up -d --build --force-recreate development_env

dev-shell:  ## Open a shell in the opt-in development_env container
	cd $(ROOT_DIR) && $(LOCAL_ONLY_COMPOSE) up -d development_env && $(LOCAL_ONLY_COMPOSE) exec development_env /bin/bash

notebook-server:  ## Start the opt-in development_env container and localhost-only Jupyter Lab
	cd $(ROOT_DIR) && $(LOCAL_ONLY_COMPOSE) up -d development_env && $(LOCAL_ONLY_COMPOSE) restart development_env && $(LOCAL_ONLY_COMPOSE) exec -d development_env env JUPYTER_TOKEN="$(JUPYTER_TOKEN)" start-jupyter-server.sh && printf 'VS Code Jupyter URL: http://127.0.0.1:8888/?token=%s\n' "$(JUPYTER_TOKEN)"

notebook-stop:  ## Stop the container-backed notebook server by restarting development_env
	cd $(ROOT_DIR) && $(LOCAL_ONLY_COMPOSE) up -d development_env && $(LOCAL_ONLY_COMPOSE) restart development_env

feast-prepare:  ## Export stored features and apply the local Feast repo for DATASET=$(DATASET)
	cd $(ROOT_DIR) && ./scripts/prepare-feast-local.sh $(DATASET)
