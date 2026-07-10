#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="$ROOT_DIR/.state/feast"
DEFAULT_ENV_FILE="$ROOT_DIR/.env"
EXAMPLE_ENV_FILE="$ROOT_DIR/.env.example"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/env-file-common.sh"

require_command uv

DATASET="train"
RESET_STATE=false
MATERIALIZE=true

usage() {
  echo "Usage: $0 [--reset-state] [--skip-materialize] [--dataset name|name]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset-state)
      RESET_STATE=true
      ;;
    --skip-materialize)
      MATERIALIZE=false
      ;;
    --dataset)
      shift
      DATASET="$(require_cli_option_value "--dataset" "${1:-}" usage)"
      ;;
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
      DATASET="$1"
      ;;
  esac
  shift
done

OUTPUT_PATH="$ROOT_DIR/data/feast/${DATASET}.parquet"
MATERIALIZE_TS="${FEAST_MATERIALIZE_TIMESTAMP:-$(date -u +"%Y-%m-%dT%H:%M:%S")}"

export_local_feast_datastore_env "$DEFAULT_ENV_FILE" "$EXAMPLE_ENV_FILE"

require_command curl
export DATASTORE_EMULATOR_HOST="${DATASTORE_EMULATOR_HOST:-${FEAST_DATASTORE_EMULATOR_BIND_HOST}:${FEAST_DATASTORE_EMULATOR_PORT}}"
FEAST_DATASTORE_EMULATOR_RESET_URL="http://${DATASTORE_EMULATOR_HOST}/reset"

cd "$ROOT_DIR"

if [[ "$RESET_STATE" == "true" ]]; then
  rm -rf "$STATE_DIR"
  curl --retry 30 --retry-all-errors --retry-delay 1 -fsS -X POST "$FEAST_DATASTORE_EMULATOR_RESET_URL" >/dev/null
fi

mkdir -p "$STATE_DIR"

CONFIG_PATH="$(render_feast_runtime_config_path "$ROOT_DIR")"
export_feast_runtime_config_path "$CONFIG_PATH"

# Retry the offline export a few times: on CI the prior Airflow DAG run
# occasionally needs a moment for the S3-backed feature rows to be
# readable from the host, so a single export can race and produce a
# missing parquet that breaks `feast apply` downstream.
export_attempts=0
export_max_attempts=5
until uv run python -m foehncast.feature_pipeline.feast export \
  --dataset "$DATASET" \
  --output "$OUTPUT_PATH" >/dev/null && [[ -s "$OUTPUT_PATH" ]]; do
  export_attempts=$((export_attempts + 1))
  if (( export_attempts >= export_max_attempts )); then
    echo "Feast offline export did not produce $OUTPUT_PATH after ${export_max_attempts} attempts" >&2
    ls -la "$(dirname "$OUTPUT_PATH")" >&2 || true
    exit 1
  fi
  echo "Feast offline export attempt ${export_attempts} did not produce ${OUTPUT_PATH}; retrying..." >&2
  sleep 2
done

# Pin the Feast FileSource to the absolute parquet we just exported so
# `feast apply` cannot resolve a different relative path under CI.
export FOEHNCAST_FEAST_FILE_PATH="$OUTPUT_PATH"

run_feast_repo_apply_and_maybe_materialize "$ROOT_DIR/feature_repo" "$MATERIALIZE" "$MATERIALIZE_TS"

printf 'Prepared Feast repo for dataset %s\n' "$DATASET"
printf 'Runtime config: %s\n' "$CONFIG_PATH"
printf 'Offline source: %s\n' "$OUTPUT_PATH"
printf 'Local Feast state: %s\n' "$STATE_DIR"
printf 'Online store: Datastore emulator at %s\n' "$DATASTORE_EMULATOR_HOST"

print_feast_materialize_status "$ROOT_DIR" "$MATERIALIZE" "$MATERIALIZE_TS"
