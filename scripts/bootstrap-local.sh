#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ENV_FILE="${ROOT_DIR}/.env"
EXAMPLE_ENV_FILE="${ROOT_DIR}/.env.example"
FEATURE_DATE="${FEATURE_DATE:-2024-01-01}"
TRAINING_DATE="${TRAINING_DATE:-2024-01-02}"
AIRFLOW_HEALTH_URL="${AIRFLOW_HEALTH_URL:-http://127.0.0.1:8080/health}"
APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:8000/health}"
ONLINE_FEATURES_URL="${ONLINE_FEATURES_URL:-http://127.0.0.1:8000/features/online}"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"

usage() {
  echo "Usage: $0 [env-file]" >&2
}

ENV_FILE="$DEFAULT_ENV_FILE"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ "$ENV_FILE" != "$DEFAULT_ENV_FILE" ]]; then
        echo "Only one env file may be provided" >&2
        usage
        exit 1
      fi
      ENV_FILE="$1"
      ;;
  esac
  shift
done

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

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.objectstore.yml)

compose() {
  docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"
}

env_file_value() {
  local key="$1"
  local line value

  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    return
  fi

  value="${line#*=}"
  value="${value#\"}"
  value="${value%\"}"
  printf '%s\n' "$value"
}

resolved_env_value() {
  local key="$1"

  if [[ -n "${!key:-}" ]]; then
    printf '%s\n' "${!key}"
    return
  fi

  env_file_value "$key"
}

port_in_use() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi

  return 1
}

next_available_port() {
  local requested_port="$1"
  local candidate="$requested_port"
  local reserved_port="${2:-}"

  while port_in_use "$candidate" || [[ -n "$reserved_port" && "$candidate" == "$reserved_port" ]]; do
    candidate=$((candidate + 1))
  done

  printf '%s\n' "$candidate"
}

cleanup_local_runtime_state() {
  local dataset="$1"

  rm -rf "$ROOT_DIR/airflow/reports"
  rm -rf "$ROOT_DIR/.state/feast"
  rm -rf "$ROOT_DIR/data/$dataset"
  rm -f "$ROOT_DIR/data/feast/$dataset.parquet"
}

wait_for_service_health() {
  local service="$1"
  local max_attempts="${2:-90}"
  local sleep_seconds="${3:-2}"
  local container_id=""
  local status=""
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    container_id="$(compose ps -q "$service" 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      if [[ "$status" == "healthy" || "$status" == "running" ]]; then
        return 0
      fi
    fi

    sleep "$sleep_seconds"
  done

  echo "Timed out waiting for service '$service' to become ready (last status: ${status:-unknown})." >&2
  compose logs "$service" >&2 || true
  return 1
}

RUN_MODE_LABEL="local MinIO-backed objectstore baseline"

export STORAGE_BACKEND="s3"
export OBJECTSTORE_BIND_HOST="${OBJECTSTORE_BIND_HOST:-$(resolved_env_value OBJECTSTORE_BIND_HOST)}"
export OBJECTSTORE_ACCESS_KEY="${OBJECTSTORE_ACCESS_KEY:-$(resolved_env_value OBJECTSTORE_ACCESS_KEY)}"
export OBJECTSTORE_SECRET_KEY="${OBJECTSTORE_SECRET_KEY:-$(resolved_env_value OBJECTSTORE_SECRET_KEY)}"
export OBJECTSTORE_BUCKET="${OBJECTSTORE_BUCKET:-$(resolved_env_value OBJECTSTORE_BUCKET)}"
export OBJECTSTORE_PORT="${OBJECTSTORE_PORT:-$(resolved_env_value OBJECTSTORE_PORT)}"
export OBJECTSTORE_CONSOLE_PORT="${OBJECTSTORE_CONSOLE_PORT:-$(resolved_env_value OBJECTSTORE_CONSOLE_PORT)}"

export OBJECTSTORE_BIND_HOST="${OBJECTSTORE_BIND_HOST:-127.0.0.1}"
export OBJECTSTORE_ACCESS_KEY="${OBJECTSTORE_ACCESS_KEY:-minioadmin}"
export OBJECTSTORE_SECRET_KEY="${OBJECTSTORE_SECRET_KEY:-minioadmin123}"
export OBJECTSTORE_BUCKET="${OBJECTSTORE_BUCKET:-foehncast-data}"
export OBJECTSTORE_PORT="${OBJECTSTORE_PORT:-9000}"
export OBJECTSTORE_CONSOLE_PORT="${OBJECTSTORE_CONSOLE_PORT:-9001}"

resolved_objectstore_port="$(next_available_port "$OBJECTSTORE_PORT")"
resolved_objectstore_console_port="$(next_available_port "$OBJECTSTORE_CONSOLE_PORT" "$resolved_objectstore_port")"

if [[ "$resolved_objectstore_port" != "$OBJECTSTORE_PORT" ]]; then
  echo "Objectstore port $OBJECTSTORE_PORT is busy; using $resolved_objectstore_port instead."
fi
if [[ "$resolved_objectstore_console_port" != "$OBJECTSTORE_CONSOLE_PORT" ]]; then
  echo "Objectstore console port $OBJECTSTORE_CONSOLE_PORT is busy; using $resolved_objectstore_console_port instead."
fi

export OBJECTSTORE_PORT="$resolved_objectstore_port"
export OBJECTSTORE_CONSOLE_PORT="$resolved_objectstore_console_port"
export STORAGE_S3_BUCKET="${STORAGE_S3_BUCKET:-$OBJECTSTORE_BUCKET}"
export STORAGE_S3_ENDPOINT="${STORAGE_S3_ENDPOINT:-http://${OBJECTSTORE_BIND_HOST}:${OBJECTSTORE_PORT}}"
export OBJECTSTORE_ENDPOINT="${OBJECTSTORE_ENDPOINT:-$STORAGE_S3_ENDPOINT}"
export MLFLOW_ARTIFACT_DESTINATION="${MLFLOW_ARTIFACT_DESTINATION:-s3://${OBJECTSTORE_BUCKET}/mlflow/artifacts}"
export MLFLOW_S3_ENDPOINT_URL="${MLFLOW_S3_ENDPOINT_URL:-$OBJECTSTORE_ENDPOINT}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-$OBJECTSTORE_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-$OBJECTSTORE_SECRET_KEY}"
export FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID="${FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID:-$(resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID)}"
export FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE="${FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE:-$(resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE)}"
export FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE="${FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE:-$(resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE)}"
export FEAST_DATASTORE_EMULATOR_BIND_HOST="${FEAST_DATASTORE_EMULATOR_BIND_HOST:-$(resolved_env_value FEAST_DATASTORE_EMULATOR_BIND_HOST)}"
export FEAST_DATASTORE_EMULATOR_PORT="${FEAST_DATASTORE_EMULATOR_PORT:-$(resolved_env_value FEAST_DATASTORE_EMULATOR_PORT)}"

export FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID="${FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID:-foehncast-local}"
export FEAST_DATASTORE_EMULATOR_BIND_HOST="${FEAST_DATASTORE_EMULATOR_BIND_HOST:-127.0.0.1}"
export FEAST_DATASTORE_EMULATOR_PORT="${FEAST_DATASTORE_EMULATOR_PORT:-8181}"

resolved_feast_datastore_port="$(next_available_port "$FEAST_DATASTORE_EMULATOR_PORT")"
if [[ "$resolved_feast_datastore_port" != "$FEAST_DATASTORE_EMULATOR_PORT" ]]; then
  echo "Feast Datastore emulator port $FEAST_DATASTORE_EMULATOR_PORT is busy; using $resolved_feast_datastore_port instead."
fi

export FEAST_DATASTORE_EMULATOR_PORT="$resolved_feast_datastore_port"
export DATASTORE_EMULATOR_HOST="${DATASTORE_EMULATOR_HOST:-${FEAST_DATASTORE_EMULATOR_BIND_HOST}:${FEAST_DATASTORE_EMULATOR_PORT}}"
FEAST_DATASTORE_EMULATOR_RESET_URL="http://${DATASTORE_EMULATOR_HOST}/reset"

FEAST_DATASET="${FEAST_DATASET:-$(env_file_value AIRFLOW_FEATURE_DATASET)}"
FEAST_DATASET="${FEAST_DATASET:-train}"

echo "Resetting local stack state for a clean run..."
compose down -v --remove-orphans >/dev/null 2>&1 || true
echo "Removing disposable local runtime artifacts..."
cleanup_local_runtime_state "$FEAST_DATASET"

echo "Starting local stack..."
compose up --build -d --remove-orphans

echo "Waiting for Feast Datastore emulator..."
wait_for_service_health feast-online-store 90 2
curl --retry 30 --retry-all-errors --retry-delay 2 -fsS -X POST "$FEAST_DATASTORE_EMULATOR_RESET_URL" >/dev/null

echo "Waiting for Airflow webserver health..."
curl --retry 60 --retry-all-errors --retry-delay 2 -fsS "$AIRFLOW_HEALTH_URL" >/dev/null

echo "Running feature pipeline for ${FEATURE_DATE}..."
compose exec -T airflow-webserver airflow dags test feature_pipeline "$FEATURE_DATE"

echo "Running training pipeline for ${TRAINING_DATE}..."
compose exec -T airflow-webserver airflow dags test training_pipeline "$TRAINING_DATE"

echo "Preparing Feast serving state for ${FEAST_DATASET}..."
"${ROOT_DIR}/scripts/prepare-feast-local.sh" --reset-state "$FEAST_DATASET"

echo "Waiting for app health..."
curl --retry 60 --retry-all-errors --retry-delay 2 -fsS "$APP_HEALTH_URL" >/dev/null

echo "Checking Feast online features..."
curl --retry 30 --retry-all-errors --retry-delay 2 -fsS \
  -X POST "$ONLINE_FEATURES_URL" \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana"],"feature_names":["wind_speed_10m"]}' >/dev/null

echo "Local stack is ready."
echo "Runtime env: $ENV_FILE"
echo "Profile:  ${RUN_MODE_LABEL}"
echo "App:      http://127.0.0.1:8000"
echo "Airflow:  http://127.0.0.1:8080"
echo "MLflow:   http://127.0.0.1:5001"
echo "Feast:    /features/online verified"
echo "Airflow and MLflow open directly in local mode."
echo "This bootstrap path resets local Docker volumes and disposable local runtime artifacts so each run starts clean."
echo "Curated features and MLflow artifacts are using the MinIO-backed local objectstore baseline for this run."
echo "This keeps the local object-access layer aligned with the hosted GCS-facing architecture while Feast uses the local Datastore-mode emulator for online serving."
echo "Objectstore API: ${OBJECTSTORE_ENDPOINT}"
echo "Objectstore UI:  http://${OBJECTSTORE_BIND_HOST}:${OBJECTSTORE_CONSOLE_PORT}"
echo "Feast online store: http://${DATASTORE_EMULATOR_HOST}"
echo "The local bootstrap also prepares Feast state and verifies the online-feature route against the running app."
echo
echo "Sample check:"
echo "curl -fsS -X POST http://127.0.0.1:8000/rank -H 'content-type: application/json' -d '{\"spot_ids\":[\"silvaplana\",\"urnersee\"]}'"
echo "curl -fsS -X POST http://127.0.0.1:8000/features/online -H 'content-type: application/json' -d '{\"spot_ids\":[\"silvaplana\"],\"feature_names\":[\"wind_speed_10m\"]}'"
