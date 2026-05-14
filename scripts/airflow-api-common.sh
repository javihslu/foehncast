#!/usr/bin/env bash

airflow_api_helper_run() {
  env PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m foehncast.airflow_api "$@"
}

airflow_api_verify_health() {
  local health_url="$1"
  local timeout_message="$2"
  local max_attempts="${3:-60}"
  local sleep_seconds="${4:-2}"
  local payload=""
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if payload="$(curl --retry 1 --retry-all-errors --retry-delay 0 -fsS "$health_url" 2>/dev/null)"; then
      if printf '%s' "$payload" | airflow_api_helper_run health; then
        return 0
      fi
    fi

    sleep "$sleep_seconds"
  done

  echo "$timeout_message" >&2
  if [[ -n "$payload" ]]; then
    printf '%s\n' "$payload" >&2
  fi
  return 1
}

airflow_api_wait_for_dag_run_state() {
  local airflow_api_base_url="$1"
  local dag_id="$2"
  local expected_state="$3"
  local timeout_message="$4"
  local max_attempts="${5:-120}"
  local sleep_seconds="${6:-2}"
  shift 6
  local helper_args=("$@")
  local payload=""
  local status
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if payload="$(curl --retry 1 --retry-all-errors --retry-delay 0 -fsS "${airflow_api_base_url}/dags/${dag_id}/dagRuns?limit=20&order_by=-start_date" 2>/dev/null)"; then
      if printf '%s' "$payload" | airflow_api_helper_run dag-run --expected-state "$expected_state" "${helper_args[@]}"; then
        return 0
      else
        status=$?
        if [[ "$status" -eq 2 ]]; then
          echo "Airflow DAG '${dag_id}' reached a terminal failure state." >&2
          printf '%s\n' "$payload" >&2
          return 1
        fi
      fi
    fi

    sleep "$sleep_seconds"
  done

  echo "$timeout_message" >&2
  if [[ -n "$payload" ]]; then
    printf '%s\n' "$payload" >&2
  fi
  return 1
}