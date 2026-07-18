.PHONY: help install install-docs install-feast lock lint format test coverage test-feature check dvc-validate alerts-check docs-build docs-serve bootstrap-local smoke-local-evaluator bootstrap-gcp terraform-remote smoke-bootstrap-only cloud-triggers cloud-data cloud-verify compose-up compose-down compose-ps compose-logs dev-build dev-rebuild dev-shell notebook-server notebook-stop feast-prepare notebook-review-compare

ROOT_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
DATASET ?= train
JUPYTER_TOKEN ?= foehncast-local
TF_REMOTE_ARGS ?= plan
SMOKE_BOOTSTRAP_ARGS ?=
NOTEBOOK_REVIEW_BACKEND ?= s3
NOTEBOOK_REVIEW_DIR ?=
LOCAL_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.objectstore.yml
LOCAL_ONLY_COMPOSE := COMPOSE_PROFILES=local-only docker compose -f docker-compose.yml -f docker-compose.objectstore.yml

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

coverage:  ## Run tests with coverage report
	cd $(ROOT_DIR) && uv run pytest --cov --cov-report=term-missing --cov-report=html:reports/htmlcov -q

test-feature:  ## Run focused feature-pipeline and orchestration tests
	cd $(ROOT_DIR) && uv run pytest tests/feature_pipeline/ tests/orchestration/ -q

check: lint test  ## Run lint and the full test suite

dvc-validate:  ## Validate DVC pipeline DAG, params, and lockfile
	cd $(ROOT_DIR) && uv run dvc dag
	cd $(ROOT_DIR) && uv run dvc params diff
	@test -f $(ROOT_DIR)/dvc.lock || (echo "dvc.lock missing" && exit 1)

alerts-check:  ## Validate Prometheus alerting rules and run their promtool unit tests
	cd $(ROOT_DIR) && promtool check rules prometheus_config/alerting_rules.yml
	cd $(ROOT_DIR) && promtool test rules prometheus_config/alerting_rules_test.yml

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

cloud-triggers:  ## Setup Cloud Build triggers via Developer Connect (one browser click required)
	cd $(ROOT_DIR) && ./scripts/setup-cloud-triggers.sh

cloud-data:  ## Backfill 1yr historical data to BigQuery (requires gcloud ADC)
	cd $(ROOT_DIR) && STORAGE_BACKEND=bigquery uv run python scripts/backfill-history.py --no-push

cloud-verify:  ## Verify Cloud Run services are healthy and BigQuery has data
	@echo "Checking Cloud Run inference API..."
	@curl -fsS "$$(terraform -chdir=$(ROOT_DIR)/terraform output -raw cloud_run_service_url)/health" | python3 -m json.tool
	@echo ""
	@echo "Checking BigQuery row count..."
	@bq query --project_id="$$(terraform -chdir=$(ROOT_DIR)/terraform output -raw project_id)" --use_legacy_sql=false \
		'SELECT spot_id, COUNT(*) as row_count FROM `'"$$(terraform -chdir=$(ROOT_DIR)/terraform output -raw project_id)"'.'"$$(terraform -chdir=$(ROOT_DIR)/terraform output -raw bigquery_dataset_id)"'.'"$$(terraform -chdir=$(ROOT_DIR)/terraform output -raw bigquery_feature_table_id)"'` GROUP BY spot_id ORDER BY spot_id'

terraform-remote:  ## Trigger the remote Terraform workflow with TF_REMOTE_ARGS='<command> [flags]'
	cd $(ROOT_DIR) && ./scripts/terraform-remote.sh $(TF_REMOTE_ARGS)

smoke-bootstrap-only:  ## Run the disposable bootstrap-only smoke driver with SMOKE_BOOTSTRAP_ARGS='--repo owner/repo'
	cd $(ROOT_DIR) && ./scripts/smoke-bootstrap-only.sh $(SMOKE_BOOTSTRAP_ARGS)

compose-up:  ## Start the default local runtime stack
	cd $(ROOT_DIR) && $(LOCAL_COMPOSE) up -d

compose-down:  ## Stop and remove the local compose stack
	cd $(ROOT_DIR) && $(LOCAL_COMPOSE) down

compose-ps:  ## List compose services
	cd $(ROOT_DIR) && $(LOCAL_COMPOSE) ps

compose-logs:  ## Tail compose logs
	cd $(ROOT_DIR) && $(LOCAL_COMPOSE) logs -f

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

notebook-review-compare:  ## Compare backend-tagged notebook review summaries for NOTEBOOK_REVIEW_BACKEND=$(NOTEBOOK_REVIEW_BACKEND)
	cd $(ROOT_DIR) && uv run python -m foehncast.feature_pipeline.notebook_review compare --backend $(NOTEBOOK_REVIEW_BACKEND) $(if $(NOTEBOOK_REVIEW_DIR),--review-dir $(NOTEBOOK_REVIEW_DIR),)
