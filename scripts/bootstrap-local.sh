#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ENV_FILE="${ROOT_DIR}/.env"
EXAMPLE_ENV_FILE="${ROOT_DIR}/.env.example"
FEATURE_DATE="${FEATURE_DATE:-2024-01-01}"
TRAINING_DATE="${TRAINING_DATE:-2024-01-02}"
AIRFLOW_API_BASE_URL="${AIRFLOW_API_BASE_URL:-http://127.0.0.1:8080/api/v2}"
AIRFLOW_HEALTH_URL="${AIRFLOW_HEALTH_URL:-http://127.0.0.1:8080/api/v2/monitor/health}"
APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:8000/health}"
APP_METRICS_URL="${APP_METRICS_URL:-http://127.0.0.1:8000/metrics}"
ONLINE_FEATURES_URL="${ONLINE_FEATURES_URL:-http://127.0.0.1:8000/features/online}"
GRAFANA_BASE_URL="${GRAFANA_BASE_URL:-http://127.0.0.1:3000}"
GRAFANA_HEALTH_URL="${GRAFANA_HEALTH_URL:-${GRAFANA_BASE_URL}/api/health}"
CI_SMOKE_INGEST_FIXTURE_DIR="${CI_SMOKE_INGEST_FIXTURE_DIR:-/workspace/data/unit_contract_eval}"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/env-file-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/airflow-api-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/payload-check-common.sh"

usage() {
  echo "Usage: $0 [--ci-smoke] [env-file]" >&2
}

CI_SMOKE=false
SMOKE_STACK_STARTED=false
TEMP_DOCKER_CONFIG=""

cleanup_temporary_docker_config() {
  if [[ -n "$TEMP_DOCKER_CONFIG" && -d "$TEMP_DOCKER_CONFIG" ]]; then
    rm -rf "$TEMP_DOCKER_CONFIG"
  fi
}

cleanup_ci_smoke_stack() {
  if [[ "$CI_SMOKE" != "true" || "$SMOKE_STACK_STARTED" != "true" ]]; then
    return
  fi

  echo "Stopping CI smoke stack..."
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}

on_exit() {
  local status=$?

  cleanup_ci_smoke_stack || true
  cleanup_temporary_docker_config
  exit "$status"
}


configure_docker_client_for_bootstrap() {
  local source_docker_config="${HOME}/.docker"
  local config_file="${DOCKER_CONFIG:-${source_docker_config}}/config.json"
  local current_context="desktop-linux"

  if [[ -n "${DOCKER_CONFIG:-}" ]]; then
    return
  fi

  if [[ ! -f "$config_file" ]]; then
    return
  fi

  if ! grep -Eq '"credsStore"[[:space:]]*:[[:space:]]*"desktop"' "$config_file"; then
    return
  fi

  if command -v docker-credential-desktop >/dev/null 2>&1; then
    return
  fi

  current_context="$(sed -nE 's/.*"currentContext"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$config_file" | head -n 1)"
  current_context="${current_context:-desktop-linux}"
  TEMP_DOCKER_CONFIG="$(mktemp -d "${TMPDIR:-/tmp}/foehncast-docker-config.XXXXXX")"

  if [[ -d "$source_docker_config/cli-plugins" ]]; then
    ln -s "$source_docker_config/cli-plugins" "$TEMP_DOCKER_CONFIG/cli-plugins"
  fi
  if [[ -d "$source_docker_config/contexts" ]]; then
    ln -s "$source_docker_config/contexts" "$TEMP_DOCKER_CONFIG/contexts"
  fi
  if [[ -d "$source_docker_config/buildx" ]]; then
    ln -s "$source_docker_config/buildx" "$TEMP_DOCKER_CONFIG/buildx"
  fi
  if [[ -d "$source_docker_config/desktop-build" ]]; then
    ln -s "$source_docker_config/desktop-build" "$TEMP_DOCKER_CONFIG/desktop-build"
  fi

  printf '{\n  "currentContext": "%s",\n  "features": {\n    "hooks": "true"\n  }\n}\n' \
    "$current_context" > "$TEMP_DOCKER_CONFIG/config.json"

  export DOCKER_CONFIG="$TEMP_DOCKER_CONFIG"
  echo "Docker credential helper 'docker-credential-desktop' is unavailable; using a temporary Docker client config for this bootstrap run."
}

ENV_FILE="$DEFAULT_ENV_FILE"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --ci-smoke)
      CI_SMOKE=true
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

trap on_exit EXIT
configure_docker_client_for_bootstrap

require_docker_compose
require_command curl
require_command python3

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
BOOTSTRAP_SERVICES=(
  objectstore-init
  feast-online-store
  airflow-postgres
  airflow-webserver
  airflow-dag-processor
  airflow-scheduler
  airflow-triggerer
  app
  statsd
  prometheus
  grafana
)

compose() {
  docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"
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

  rm -f "$ROOT_DIR/airflow/.init-complete"
  rm -f "$ROOT_DIR/airflow/airflow.db"
  rm -f "$ROOT_DIR/airflow/airflow.db-shm"
  rm -f "$ROOT_DIR/airflow/airflow.db-wal"
  rm -f "$ROOT_DIR/airflow/airflow.cfg"
  rm -f "$ROOT_DIR/airflow"/*.log
  rm -f "$ROOT_DIR/airflow/simple_auth_manager_passwords.json"
  rm -f "$ROOT_DIR/airflow/simple_auth_manager_passwords.json.generated"
  rm -f "$ROOT_DIR/airflow/webserver_config.py"
  rm -rf "$ROOT_DIR/airflow/logs"
  rm -rf "$ROOT_DIR/airflow/reports"
  rm -rf "$ROOT_DIR/.state/feast"
  rm -rf "$ROOT_DIR/.state/monitoring"
  rm -rf "$ROOT_DIR/.state/online-compose-sync"
  rm -rf "$ROOT_DIR/data/$dataset"
  rm -f "$ROOT_DIR/data/feast/$dataset.parquet"
  rm -rf "$ROOT_DIR/grafana_work/data"
}

prepare_bind_mounted_runtime_paths() {
  local dataset="$1"
  local path
  local runtime_paths=(
    "$ROOT_DIR/airflow"
    "$ROOT_DIR/airflow/logs"
    "$ROOT_DIR/airflow/reports"
    "$ROOT_DIR/.state"
    "$ROOT_DIR/.state/airflow"
    "$ROOT_DIR/.state/feast"
    "$ROOT_DIR/.state/monitoring"
    "$ROOT_DIR/.state/online-compose-sync"
    "$ROOT_DIR/data/$dataset"
    "$ROOT_DIR/data/feast"
    "$ROOT_DIR/grafana_work/data"
    "$ROOT_DIR/.state/feast"
  )

  for path in "${runtime_paths[@]}"; do
    mkdir -p "$path"
    chmod 0777 "$path"
  done
}

seed_local_online_compose_sync_status() {
  local sync_dir="$ROOT_DIR/.state/online-compose-sync"
  local sync_status_file="$sync_dir/last-success.json"
  local sync_time

  sync_time="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  mkdir -p "$sync_dir"
  printf '{\n  "state": "succeeded",\n  "git_ref": "local-bootstrap",\n  "last_successful_sync_at": "%s",\n  "last_successful_commit": "local-smoke",\n  "compose_deploy_mode": "bootstrap"\n}\n' \
    "$sync_time" > "$sync_status_file"
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

run_airflow_api_helper() {
  airflow_api_helper_run "$@"
}

verify_airflow_api_health() {
  airflow_api_verify_health \
    "$AIRFLOW_HEALTH_URL" \
    "Timed out waiting for Airflow health endpoint to report all required components healthy." \
    "$@"
}

wait_for_airflow_dag_run_state() {
  local dag_id="$1"
  local expected_state="$2"
  local expected_run_type="${3:-}"
  local max_attempts="${4:-120}"
  local sleep_seconds="${5:-2}"
  local helper_args=()

  if [[ -n "$expected_run_type" ]]; then
    helper_args+=(--expected-run-type "$expected_run_type")
  fi

  airflow_api_wait_for_dag_run_state \
    "$AIRFLOW_API_BASE_URL" \
    "$dag_id" \
    "$expected_state" \
    "Timed out waiting for Airflow DAG '$dag_id' to reach state '$expected_state'." \
    "$max_attempts" \
    "$sleep_seconds" \
    "${helper_args[@]}"
}

grafana_api_get() {
  local path="$1"

  local auth_args=()
  if [[ -n "${GRAFANA_API_USER:-}" && -n "${GRAFANA_API_PASSWORD:-}" ]]; then
    auth_args=(--user "${GRAFANA_API_USER}:${GRAFANA_API_PASSWORD}")
  fi

  curl --retry 60 --retry-all-errors --retry-delay 2 -fsS \
    "${auth_args[@]}" \
    "${GRAFANA_BASE_URL}${path}"
}

require_payload_pattern() {
  payload_check_require_pattern "Grafana provisioning check failed" "$@"
}

require_payload_patterns() {
  payload_check_require_patterns "Grafana provisioning check failed" "$@"
}

verify_grafana_provisioning() {
  local dashboard_payload alert_rules_payload contact_points_payload policies_payload
  local health_auth_args=()

  if [[ -n "${GRAFANA_API_USER:-}" && -n "${GRAFANA_API_PASSWORD:-}" ]]; then
    health_auth_args=(--user "${GRAFANA_API_USER}:${GRAFANA_API_PASSWORD}")
  fi

  echo "Waiting for Grafana health..."
  curl --retry 60 --retry-all-errors --retry-delay 2 -fsS \
    "${health_auth_args[@]}" \
    "$GRAFANA_HEALTH_URL" >/dev/null

  echo "Checking Grafana dashboard provisioning..."
  dashboard_payload="$(grafana_api_get "/api/search?dashboardUIDs=foehncast-monitoring")"
  require_payload_patterns \
    "$dashboard_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast-monitoring"' \
    '"title"[[:space:]]*:[[:space:]]*"FoehnCast Monitoring"' \
    'dashboard title FoehnCast Monitoring'

  echo "Checking Grafana alert-rule provisioning..."
  alert_rules_payload="$(grafana_api_get "/api/v1/provisioning/alert-rules")"
  require_payload_patterns \
    "$alert_rules_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_predmon_schedule_fail"' \
    'schedule failure alert rule' \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_predmon_execution_fail"' \
    'execution failure alert rule' \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_predmon_stale_success"' \
    'stale success alert rule' \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_feature_stage_failures"' \
    'feature stage failure alert rule' \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_training_stage_failures"' \
    'training stage failure alert rule' \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_hosted_sync_stale"' \
    'hosted sync stale alert rule'

  echo "Checking Grafana contact point provisioning..."
  contact_points_payload="$(grafana_api_get "/api/v1/provisioning/contact-points?name=foehncast-email")"
  require_payload_patterns \
    "$contact_points_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_email"' \
    '"name"[[:space:]]*:[[:space:]]*"foehncast-email"' \
    'foehncast email contact point name'

  echo "Checking Grafana notification policy provisioning..."
  policies_payload="$(grafana_api_get "/api/v1/provisioning/policies")"
  require_payload_patterns \
    "$policies_payload" \
    '"receiver"[[:space:]]*:[[:space:]]*"foehncast-email"' \
    'notification policy receiver foehncast-email' \
    '"object_matchers"' \
    'notification policy route matchers' \
    '"inference-monitoring"' \
    'notification policy inference-monitoring matcher' \
    '"feature-pipeline"' \
    'notification policy feature-pipeline matcher' \
    '"training-pipeline"' \
    'notification policy training-pipeline matcher' \
    '"hosted-operator"' \
    'notification policy hosted-operator matcher'
}

verify_hosted_sync_metrics() {
  local metrics_payload

  echo "Checking hosted sync metrics exposure..."
  metrics_payload="$(curl --retry 60 --retry-all-errors --retry-delay 2 -fsS "$APP_METRICS_URL")"
  require_payload_patterns \
    "$metrics_payload" \
    'foehncast_online_compose_sync_status_file_present[[:space:]]+1(\.0)?' \
    'foehncast_online_compose_sync_last_success_timestamp_seconds\{compose_deploy_mode="bootstrap",git_ref="local-bootstrap"\}[[:space:]]+[0-9.e+-]+' \
    'hosted sync last-success timestamp metric'
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
export_local_feast_datastore_env "$ENV_FILE"

resolved_feast_datastore_port="$(next_available_port "$FEAST_DATASTORE_EMULATOR_PORT")"
if [[ "$resolved_feast_datastore_port" != "$FEAST_DATASTORE_EMULATOR_PORT" ]]; then
  echo "Feast Datastore emulator port $FEAST_DATASTORE_EMULATOR_PORT is busy; using $resolved_feast_datastore_port instead."
fi

export FEAST_DATASTORE_EMULATOR_PORT="$resolved_feast_datastore_port"
export DATASTORE_EMULATOR_HOST="${DATASTORE_EMULATOR_HOST:-${FEAST_DATASTORE_EMULATOR_BIND_HOST}:${FEAST_DATASTORE_EMULATOR_PORT}}"
FEAST_DATASTORE_EMULATOR_RESET_URL="http://${DATASTORE_EMULATOR_HOST}/reset"

FEAST_DATASET="${FEAST_DATASET:-$(resolved_env_value AIRFLOW_FEATURE_DATASET "$ENV_FILE")}"
FEAST_DATASET="${FEAST_DATASET:-train}"

export_resolved_env_value FOEHNCAST_GRAFANA_ADMIN_USER "$ENV_FILE"
export_resolved_env_value FOEHNCAST_GRAFANA_ADMIN_PASSWORD "$ENV_FILE"
export_resolved_env_value FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM "$ENV_FILE"
export_resolved_env_value FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED "$ENV_FILE"
export_resolved_env_value FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE "$ENV_FILE"
export_resolved_env_value GRAFANA_API_USER "$ENV_FILE"
export_resolved_env_value GRAFANA_API_PASSWORD "$ENV_FILE"

ensure_env_default FOEHNCAST_GRAFANA_ADMIN_USER admin
ensure_env_default FOEHNCAST_GRAFANA_ADMIN_PASSWORD foehncast-local
ensure_env_default FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM true
ensure_env_default FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED true
ensure_env_default FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE Admin
export GRAFANA_API_USER="${GRAFANA_API_USER:-${FOEHNCAST_GRAFANA_ADMIN_USER}}"
export GRAFANA_API_PASSWORD="${GRAFANA_API_PASSWORD:-${FOEHNCAST_GRAFANA_ADMIN_PASSWORD}}"

echo "Resetting local stack state for a clean run..."
compose down -v --remove-orphans >/dev/null 2>&1 || true
echo "Removing disposable local runtime artifacts..."
cleanup_local_runtime_state "$FEAST_DATASET"
prepare_bind_mounted_runtime_paths "$FEAST_DATASET"
seed_local_online_compose_sync_status

echo "Starting local stack..."
compose up --build -d --remove-orphans "${BOOTSTRAP_SERVICES[@]}"
SMOKE_STACK_STARTED=true

echo "Waiting for Feast Datastore emulator..."
wait_for_service_health feast-online-store 90 2
curl --retry 30 --retry-all-errors --retry-delay 2 -fsS -X POST "$FEAST_DATASTORE_EMULATOR_RESET_URL" >/dev/null

echo "Waiting for Airflow metadata database..."
wait_for_service_health airflow-postgres 90 2

echo "Waiting for Airflow component health checks..."
wait_for_service_health airflow-webserver 90 2
wait_for_service_health airflow-dag-processor 90 2
wait_for_service_health airflow-scheduler 90 2
wait_for_service_health airflow-triggerer 90 2

echo "Waiting for Airflow API server health..."
verify_airflow_api_health 60 2

verify_grafana_provisioning

echo "Running feature pipeline for ${FEATURE_DATE}..."
if [[ "$CI_SMOKE" == "true" ]]; then
  compose exec -T \
    -e FOEHNCAST_INGEST_FIXTURE_DIR="$CI_SMOKE_INGEST_FIXTURE_DIR" \
    airflow-webserver \
    airflow dags test feature_pipeline "$FEATURE_DATE"
else
  compose exec -T airflow-webserver airflow dags test feature_pipeline "$FEATURE_DATE"
fi

echo "Waiting for asset-triggered training pipeline..."
wait_for_airflow_dag_run_state training_pipeline success asset_triggered 120 2

echo "Preparing Feast serving state for ${FEAST_DATASET}..."
"${ROOT_DIR}/scripts/prepare-feast-local.sh" --reset-state "$FEAST_DATASET"

echo "Waiting for app health..."
curl --retry 60 --retry-all-errors --retry-delay 2 -fsS "$APP_HEALTH_URL" >/dev/null
verify_hosted_sync_metrics

echo "Checking Feast online features..."
curl --retry 30 --retry-all-errors --retry-delay 2 -fsS \
  -X POST "$ONLINE_FEATURES_URL" \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana"],"feature_names":["wind_speed_10m"]}' >/dev/null

if [[ "$CI_SMOKE" == "true" ]]; then
  echo "Local evaluator smoke passed."
  echo "Verified Airflow health, Grafana provisioning, feature pipeline execution, Feast serving state, app health, hosted sync metrics, and /features/online."
  echo "The stack will be torn down automatically."
  exit 0
fi

echo "Local stack is ready."
echo "Runtime env: $ENV_FILE"
echo "Profile:  ${RUN_MODE_LABEL}"
echo "App:      http://127.0.0.1:8000"
echo "Airflow:  http://127.0.0.1:8080"
echo "MLflow:   http://127.0.0.1:5001"
echo "Grafana:  ${GRAFANA_BASE_URL}"
echo "Feast:    /features/online verified"
echo "Airflow UI/API and MLflow open directly in local mode."
echo "This bootstrap path resets local Docker volumes, Airflow metadata, and disposable runtime artifacts so each run starts clean."
echo "Curated features and MLflow artifacts are using the MinIO-backed local objectstore baseline for this run."
echo "This keeps the local object-access layer aligned with the hosted GCS-facing architecture while Feast uses the local Datastore-mode emulator for online serving."
echo "Objectstore API: ${OBJECTSTORE_ENDPOINT}"
echo "Objectstore UI:  http://${OBJECTSTORE_BIND_HOST}:${OBJECTSTORE_CONSOLE_PORT}"
echo "Feast online store: http://${DATASTORE_EMULATOR_HOST}"
echo "The local bootstrap also prepares Feast state, verifies the online-feature route, and confirms Grafana loaded the checked-in dashboard and alerting resources."
echo "Grafana uses deployable-safe defaults in the checked-in config; this bootstrap applies local-only access overrides unless you provide stricter local settings in $ENV_FILE."
echo
echo "Sample check:"
echo "curl -fsS -X POST http://127.0.0.1:8000/rank -H 'content-type: application/json' -d '{\"spot_ids\":[\"silvaplana\",\"urnersee\"]}'"
echo "curl -fsS -X POST http://127.0.0.1:8000/features/online -H 'content-type: application/json' -d '{\"spot_ids\":[\"silvaplana\"],\"feature_names\":[\"wind_speed_10m\"]}'"
