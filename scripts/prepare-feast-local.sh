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

uv run python -m foehncast.feature_pipeline.feast export \
  --dataset "$DATASET" \
  --output "$OUTPUT_PATH" >/dev/null

run_feast_repo_apply_and_maybe_materialize "$ROOT_DIR/feature_repo" "$MATERIALIZE" "$MATERIALIZE_TS"

printf 'Prepared Feast repo for dataset %s\n' "$DATASET"
printf 'Runtime config: %s\n' "$CONFIG_PATH"
printf 'Offline source: %s\n' "$OUTPUT_PATH"
printf 'Local Feast state: %s\n' "$STATE_DIR"
printf 'Online store: Datastore emulator at %s\n' "$DATASTORE_EMULATOR_HOST"

print_feast_materialize_status "$ROOT_DIR" "$MATERIALIZE" "$MATERIALIZE_TS"
