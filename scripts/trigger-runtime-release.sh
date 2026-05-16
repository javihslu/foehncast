#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST_FILE=""
DAG_ID="runtime_release"
AIRFLOW_API_BASE_URL="${FOEHNCAST_AIRFLOW_API_BASE_URL:-http://127.0.0.1:8080/api/v2}"
AIRFLOW_API_HEALTH_ENDPOINT="${FOEHNCAST_AIRFLOW_API_HEALTH_ENDPOINT:-/monitor/health}"
AIRFLOW_API_AUTH_TOKEN="${FOEHNCAST_AIRFLOW_AUTH_TOKEN:-}"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/airflow-api-common.sh"

usage() {
  echo "Usage: $0 --request-file path [--airflow-api-base-url url] [--airflow-api-health-endpoint path]" >&2
}

run_runtime_release_helper() {
  env PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m foehncast.runtime_release "$@"
}

airflow_api_health_url() {
  printf '%s%s\n' "${AIRFLOW_API_BASE_URL%/}" "$AIRFLOW_API_HEALTH_ENDPOINT"
}

verify_airflow_api_health() {
  airflow_api_verify_health \
    "$(airflow_api_health_url)" \
    "Timed out waiting for Airflow API health." \
    "${1:-90}" \
    "${2:-2}" \
    "$AIRFLOW_API_AUTH_TOKEN"
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
    "$AIRFLOW_API_AUTH_TOKEN" \
    --expected-run-id "$dag_run_id"
}

normalize_request_payload() {
  run_runtime_release_helper normalize-request --request-file "$REQUEST_FILE"
}

build_airflow_api_dag_run_payload() {
  local dag_run_id="$1"
  local logical_date="$2"
  local normalized_request="$3"

  python3 -c 'import json, sys; print(json.dumps({"dag_run_id": sys.argv[1], "logical_date": sys.argv[2], "conf": json.loads(sys.argv[3])}, sort_keys=True))' \
    "$dag_run_id" \
    "$logical_date" \
    "$normalized_request"
}

trigger_airflow_dag_run() {
  local normalized_request="$1"
  local dag_run_id="$2"
  local logical_date="$3"
  local request_url payload
  local -a curl_args=(
    --retry 1
    --retry-all-errors
    --retry-delay 0
    -fsS
    -X POST
    -H "Accept: application/json"
    -H "Content-Type: application/json"
  )

  if [[ -n "$AIRFLOW_API_AUTH_TOKEN" ]]; then
    curl_args+=(-H "Authorization: Bearer ${AIRFLOW_API_AUTH_TOKEN}")
  fi

  request_url="${AIRFLOW_API_BASE_URL%/}/dags/${DAG_ID}/dagRuns"
  payload="$(build_airflow_api_dag_run_payload "$dag_run_id" "$logical_date" "$normalized_request")"

  curl "${curl_args[@]}" "$request_url" --data "$payload" >/dev/null
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --request-file)
      shift
      REQUEST_FILE="$(require_cli_option_value "--request-file" "${1:-}" usage)"
      ;;
    --airflow-api-base-url)
      shift
      AIRFLOW_API_BASE_URL="$(require_cli_option_value "--airflow-api-base-url" "${1:-}" usage)"
      ;;
    --airflow-api-health-endpoint)
      shift
      AIRFLOW_API_HEALTH_ENDPOINT="$(require_cli_option_value "--airflow-api-health-endpoint" "${1:-}" usage)"
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

if [[ "${AIRFLOW_API_HEALTH_ENDPOINT}" != /* ]]; then
  AIRFLOW_API_HEALTH_ENDPOINT="/${AIRFLOW_API_HEALTH_ENDPOINT}"
fi

if [[ -z "$REQUEST_FILE" || ! -f "$REQUEST_FILE" ]]; then
  usage
  exit 1
fi

normalized_request="$(normalize_request_payload)"
dag_run_id="runtime_release__$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
logical_date="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

verify_airflow_api_health 90 2 >&2
trigger_airflow_dag_run "$normalized_request" "$dag_run_id" "$logical_date"

wait_for_airflow_dag_run_state "$DAG_ID" "$dag_run_id" success 120 2 >&2

run_runtime_release_helper verify-report --expected-run-id "$dag_run_id"
