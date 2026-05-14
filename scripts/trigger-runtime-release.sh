#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST_FILE=""
DAG_ID="runtime_release"
AIRFLOW_API_BASE_URL="http://127.0.0.1:8080/api/v2"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/airflow-api-common.sh"

usage() {
  echo "Usage: $0 --request-file path" >&2
}

run_airflow_api_helper() {
  airflow_api_helper_run "$@"
}

run_runtime_release_helper() {
  env PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m foehncast.runtime_release "$@"
}

verify_airflow_api_health() {
  airflow_api_verify_health \
    "${AIRFLOW_API_BASE_URL}/monitor/health" \
    "Timed out waiting for Airflow API health." \
    "$@"
}

wait_for_airflow_dag_run_state() {
  local dag_id="$1"
  local dag_run_id="$2"
  local expected_state="$3"
  local max_attempts="${4:-120}"
  local sleep_seconds="${5:-2}"
  airflow_api_wait_for_dag_run_state \
    "$AIRFLOW_API_BASE_URL" \
    "$dag_id" \
    "$expected_state" \
    "Timed out waiting for Airflow DAG '${dag_id}' run '${dag_run_id}' to reach state '${expected_state}'." \
    "$max_attempts" \
    "$sleep_seconds" \
    --expected-run-id "$dag_run_id"
}

normalize_request_payload() {
  run_runtime_release_helper normalize-request --request-file "$REQUEST_FILE"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --request-file)
      shift
      REQUEST_FILE="$(require_cli_option_value "--request-file" "${1:-}" usage)"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac

  shift
done

if [[ -z "$REQUEST_FILE" || ! -f "$REQUEST_FILE" ]]; then
  usage
  exit 1
fi

normalized_request="$(normalize_request_payload)"
dag_run_id="runtime_release__$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
logical_date="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
compose_args=(
  -f "$ROOT_DIR/docker-compose.yml"
  -f "$ROOT_DIR/docker-compose.cloud.yml"
  --env-file "$ROOT_DIR/.env"
)

verify_airflow_api_health 90 2 >&2

docker compose "${compose_args[@]}" exec -T airflow-webserver \
  airflow dags trigger "$DAG_ID" \
  --logical-date "$logical_date" \
  --run-id "$dag_run_id" \
  --conf "$normalized_request" >/dev/null

wait_for_airflow_dag_run_state "$DAG_ID" "$dag_run_id" success 120 2 >&2

report_path="$ROOT_DIR/airflow/reports/runtime-release-latest.json"
run_runtime_release_helper verify-report --expected-run-id "$dag_run_id" --report-path "$report_path"
