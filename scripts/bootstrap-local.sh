#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ENV_FILE="${ROOT_DIR}/.env"
EXAMPLE_ENV_FILE="${ROOT_DIR}/.env.example"
ENV_FILE="${1:-$DEFAULT_ENV_FILE}"
FEATURE_DATE="${FEATURE_DATE:-2024-01-01}"
TRAINING_DATE="${TRAINING_DATE:-2024-01-02}"
AIRFLOW_HEALTH_URL="${AIRFLOW_HEALTH_URL:-http://127.0.0.1:8080/health}"
APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:8000/health}"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"

require_docker_compose
require_command curl

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ "$ENV_FILE" == "$DEFAULT_ENV_FILE" && $# -eq 0 && -f "$EXAMPLE_ENV_FILE" ]]; then
    cp "$EXAMPLE_ENV_FILE" "$ENV_FILE"
    echo "Created $ENV_FILE from $EXAMPLE_ENV_FILE"
  else
    echo "Env file not found: $ENV_FILE" >&2
    exit 1
  fi
fi

cd "$ROOT_DIR"

compose() {
  docker compose --env-file "$ENV_FILE" "$@"
}

echo "Resetting local stack state for a clean run..."
compose down -v --remove-orphans >/dev/null 2>&1 || true

echo "Starting local stack..."
compose up --build -d --remove-orphans

echo "Waiting for Airflow webserver health..."
curl --retry 60 --retry-all-errors --retry-delay 2 -fsS "$AIRFLOW_HEALTH_URL" >/dev/null

echo "Running feature pipeline for ${FEATURE_DATE}..."
compose exec -T airflow-webserver airflow dags test feature_pipeline "$FEATURE_DATE"

echo "Running training pipeline for ${TRAINING_DATE}..."
compose exec -T airflow-webserver airflow dags test training_pipeline "$TRAINING_DATE"

echo "Waiting for app health..."
curl --retry 60 --retry-all-errors --retry-delay 2 -fsS "$APP_HEALTH_URL" >/dev/null

echo "Local stack is ready."
echo "Runtime env: $ENV_FILE"
echo "App:      http://127.0.0.1:8000"
echo "Airflow:  http://127.0.0.1:8080"
echo "MLflow:   http://127.0.0.1:5001"
echo "Airflow and MLflow open directly in local mode."
echo "This bootstrap path resets local Docker volumes so MLflow and Airflow start from a clean state."
echo "Feature storage defaults to local files; optional S3-compatible settings are only needed for non-default experiments."
echo
echo "Sample check:"
echo "curl -fsS -X POST http://127.0.0.1:8000/rank -H 'content-type: application/json' -d '{\"spot_ids\":[\"silvaplana\",\"urnersee\"]}'"
