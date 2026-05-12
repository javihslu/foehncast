#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ENV_FILE="${ROOT_DIR}/.env"
EXAMPLE_ENV_FILE="${ROOT_DIR}/.env.example"
FEATURE_DATE="${FEATURE_DATE:-2024-01-01}"
TRAINING_DATE="${TRAINING_DATE:-2024-01-02}"
AIRFLOW_HEALTH_URL="${AIRFLOW_HEALTH_URL:-http://127.0.0.1:8080/api/v2/monitor/health}"
APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:8000/health}"
APP_METRICS_URL="${APP_METRICS_URL:-http://127.0.0.1:8000/metrics}"
ONLINE_FEATURES_URL="${ONLINE_FEATURES_URL:-http://127.0.0.1:8000/features/online}"
GRAFANA_BASE_URL="${GRAFANA_BASE_URL:-http://127.0.0.1:3000}"
GRAFANA_HEALTH_URL="${GRAFANA_HEALTH_URL:-${GRAFANA_BASE_URL}/api/health}"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"

usage() {
  echo "Usage: $0 [env-file]" >&2
}

TEMP_DOCKER_CONFIG=""

cleanup_temporary_docker_config() {
  if [[ -n "$TEMP_DOCKER_CONFIG" && -d "$TEMP_DOCKER_CONFIG" ]]; then
    rm -rf "$TEMP_DOCKER_CONFIG"
  fi
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

trap cleanup_temporary_docker_config EXIT
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

verify_airflow_api_health() {
  local max_attempts="${1:-60}"
  local sleep_seconds="${2:-2}"
  local payload=""
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if payload="$(curl --retry 1 --retry-all-errors --retry-delay 0 -fsS "$AIRFLOW_HEALTH_URL" 2>/dev/null)"; then
      if printf '%s' "$payload" | python3 -c $'import json, sys\npayload = json.load(sys.stdin)\nrequired = ("metadatabase", "scheduler", "dag_processor", "triggerer")\nfailed = []\nfor name in required:\n    status = (payload.get(name) or {}).get("status")\n    if status != "healthy":\n        failed.append(f"{name}={status!r}")\nif failed:\n    print(", ".join(failed), file=sys.stderr)\n    raise SystemExit(1)\n'; then
        return 0
      fi
    fi

    sleep "$sleep_seconds"
  done

  echo "Timed out waiting for Airflow health endpoint to report all required components healthy." >&2
  if [[ -n "$payload" ]]; then
    printf '%s\n' "$payload" >&2
  fi
  return 1
}

wait_for_airflow_dag_run_state() {
  local dag_id="$1"
  local expected_state="$2"
  local expected_run_type="${3:-}"
  local max_attempts="${4:-120}"
  local sleep_seconds="${5:-2}"
  local payload=""
  local status
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if payload="$(curl --retry 1 --retry-all-errors --retry-delay 0 -fsS "http://127.0.0.1:8080/api/v2/dags/${dag_id}/dagRuns?limit=20&order_by=-start_date" 2>/dev/null)"; then
      if printf '%s' "$payload" | EXPECTED_STATE="$expected_state" EXPECTED_RUN_TYPE="$expected_run_type" python3 -c $'import json, os, sys\npayload = json.load(sys.stdin)\nexpected_state = os.environ["EXPECTED_STATE"]\nexpected_run_type = os.environ.get("EXPECTED_RUN_TYPE", "").strip()\nruns = payload.get("dag_runs") or []\nif expected_run_type:\n    runs = [run for run in runs if run.get("run_type") == expected_run_type]\nif not runs:\n    raise SystemExit(1)\nrun = runs[0]\nstate = (run.get("state") or "").lower()\nif state == expected_state.lower():\n    print(run.get("dag_run_id") or "")\n    raise SystemExit(0)\nif state in {"failed", "error"}:\n    print(json.dumps(run), file=sys.stderr)\n    raise SystemExit(2)\nraise SystemExit(1)\n'; then
        return 0
      else
        status=$?
        if [[ "$status" -eq 2 ]]; then
          echo "Airflow DAG '$dag_id' reached a terminal failure state." >&2
          printf '%s\n' "$payload" >&2
          return 1
        fi
      fi
    fi

    sleep "$sleep_seconds"
  done

  echo "Timed out waiting for Airflow DAG '$dag_id' to reach state '$expected_state'." >&2
  if [[ -n "$payload" ]]; then
    printf '%s\n' "$payload" >&2
  fi
  return 1
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
  local payload="$1"
  local pattern="$2"
  local description="$3"

  if ! printf '%s' "$payload" | grep -Eq "$pattern"; then
    echo "Grafana provisioning check failed: expected ${description}." >&2
    printf '%s\n' "$payload" >&2
    return 1
  fi
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
  require_payload_pattern \
    "$dashboard_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast-monitoring"' \
    'dashboard uid foehncast-monitoring'
  require_payload_pattern \
    "$dashboard_payload" \
    '"title"[[:space:]]*:[[:space:]]*"FoehnCast Monitoring"' \
    'dashboard title FoehnCast Monitoring'

  echo "Checking Grafana alert-rule provisioning..."
  alert_rules_payload="$(grafana_api_get "/api/v1/provisioning/alert-rules")"
  require_payload_pattern \
    "$alert_rules_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_predmon_schedule_fail"' \
    'schedule failure alert rule'
  require_payload_pattern \
    "$alert_rules_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_predmon_execution_fail"' \
    'execution failure alert rule'
  require_payload_pattern \
    "$alert_rules_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_predmon_stale_success"' \
    'stale success alert rule'
  require_payload_pattern \
    "$alert_rules_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_feature_stage_failures"' \
    'feature stage failure alert rule'
  require_payload_pattern \
    "$alert_rules_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_training_stage_failures"' \
    'training stage failure alert rule'
  require_payload_pattern \
    "$alert_rules_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_hosted_sync_stale"' \
    'hosted sync stale alert rule'

  echo "Checking Grafana contact point provisioning..."
  contact_points_payload="$(grafana_api_get "/api/v1/provisioning/contact-points?name=foehncast-email")"
  require_payload_pattern \
    "$contact_points_payload" \
    '"uid"[[:space:]]*:[[:space:]]*"foehncast_email"' \
    'foehncast email contact point uid'
  require_payload_pattern \
    "$contact_points_payload" \
    '"name"[[:space:]]*:[[:space:]]*"foehncast-email"' \
    'foehncast email contact point name'

  echo "Checking Grafana notification policy provisioning..."
  policies_payload="$(grafana_api_get "/api/v1/provisioning/policies")"
  require_payload_pattern \
    "$policies_payload" \
    '"receiver"[[:space:]]*:[[:space:]]*"foehncast-email"' \
    'notification policy receiver foehncast-email'
  require_payload_pattern \
    "$policies_payload" \
    '"object_matchers"' \
    'notification policy route matchers'
  require_payload_pattern \
    "$policies_payload" \
    '"inference-monitoring"' \
    'notification policy inference-monitoring matcher'
  require_payload_pattern \
    "$policies_payload" \
    '"feature-pipeline"' \
    'notification policy feature-pipeline matcher'
  require_payload_pattern \
    "$policies_payload" \
    '"training-pipeline"' \
    'notification policy training-pipeline matcher'
  require_payload_pattern \
    "$policies_payload" \
    '"hosted-operator"' \
    'notification policy hosted-operator matcher'
}

verify_hosted_sync_metrics() {
  local metrics_payload

  echo "Checking hosted sync metrics exposure..."
  metrics_payload="$(curl --retry 60 --retry-all-errors --retry-delay 2 -fsS "$APP_METRICS_URL")"
  require_payload_pattern \
    "$metrics_payload" \
    'foehncast_online_compose_sync_status_file_present[[:space:]]+1(\.0)?' \
    'hosted sync status-file-present metric'
  require_payload_pattern \
    "$metrics_payload" \
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

export FOEHNCAST_GRAFANA_ADMIN_USER="${FOEHNCAST_GRAFANA_ADMIN_USER:-$(resolved_env_value FOEHNCAST_GRAFANA_ADMIN_USER)}"
export FOEHNCAST_GRAFANA_ADMIN_PASSWORD="${FOEHNCAST_GRAFANA_ADMIN_PASSWORD:-$(resolved_env_value FOEHNCAST_GRAFANA_ADMIN_PASSWORD)}"
export FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM="${FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM:-$(resolved_env_value FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM)}"
export FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED="${FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED:-$(resolved_env_value FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED)}"
export FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE="${FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE:-$(resolved_env_value FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE)}"
export GRAFANA_API_USER="${GRAFANA_API_USER:-$(resolved_env_value GRAFANA_API_USER)}"
export GRAFANA_API_PASSWORD="${GRAFANA_API_PASSWORD:-$(resolved_env_value GRAFANA_API_PASSWORD)}"

export FOEHNCAST_GRAFANA_ADMIN_USER="${FOEHNCAST_GRAFANA_ADMIN_USER:-admin}"
export FOEHNCAST_GRAFANA_ADMIN_PASSWORD="${FOEHNCAST_GRAFANA_ADMIN_PASSWORD:-foehncast-local}"
export FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM="${FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM:-true}"
export FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED="${FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED:-true}"
export FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE="${FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE:-Admin}"
export GRAFANA_API_USER="${GRAFANA_API_USER:-${FOEHNCAST_GRAFANA_ADMIN_USER}}"
export GRAFANA_API_PASSWORD="${GRAFANA_API_PASSWORD:-${FOEHNCAST_GRAFANA_ADMIN_PASSWORD}}"

echo "Resetting local stack state for a clean run..."
compose down -v --remove-orphans >/dev/null 2>&1 || true
echo "Removing disposable local runtime artifacts..."
cleanup_local_runtime_state "$FEAST_DATASET"
seed_local_online_compose_sync_status

echo "Starting local stack..."
compose up --build -d --remove-orphans "${BOOTSTRAP_SERVICES[@]}"

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
compose exec -T airflow-webserver airflow dags test feature_pipeline "$FEATURE_DATE"

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
