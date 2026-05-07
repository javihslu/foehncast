#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="$ROOT_DIR/.state/feast"
DEFAULT_ENV_FILE="$ROOT_DIR/.env"
EXAMPLE_ENV_FILE="$ROOT_DIR/.env.example"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"

require_command uv

DATASET="train"
RESET_STATE=false
MATERIALIZE=true

usage() {
  echo "Usage: $0 [--reset-state] [--skip-materialize] [--dataset name|name]" >&2
}

env_file_value() {
  local key="$1"
  local file_path="$2"
  local line value

  if [[ ! -f "$file_path" ]]; then
    return
  fi

  line="$(grep -E "^${key}=" "$file_path" | tail -n 1 || true)"
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

  env_file_value "$key" "$DEFAULT_ENV_FILE"
  if [[ -n "$(env_file_value "$key" "$DEFAULT_ENV_FILE")" ]]; then
    return
  fi

  env_file_value "$key" "$EXAMPLE_ENV_FILE"
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
      if [[ $# -eq 0 ]]; then
        echo "Missing value for --dataset" >&2
        usage
        exit 1
      fi
      DATASET="$1"
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

export FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID="${FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID:-$(resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID)}"
export FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE="${FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE:-$(resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE)}"
export FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE="${FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE:-$(resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE)}"
export FEAST_DATASTORE_EMULATOR_BIND_HOST="${FEAST_DATASTORE_EMULATOR_BIND_HOST:-$(resolved_env_value FEAST_DATASTORE_EMULATOR_BIND_HOST)}"
export FEAST_DATASTORE_EMULATOR_PORT="${FEAST_DATASTORE_EMULATOR_PORT:-$(resolved_env_value FEAST_DATASTORE_EMULATOR_PORT)}"

export FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID="${FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID:-foehncast-local}"
export FEAST_DATASTORE_EMULATOR_BIND_HOST="${FEAST_DATASTORE_EMULATOR_BIND_HOST:-127.0.0.1}"
export FEAST_DATASTORE_EMULATOR_PORT="${FEAST_DATASTORE_EMULATOR_PORT:-8181}"

require_command curl
export DATASTORE_EMULATOR_HOST="${DATASTORE_EMULATOR_HOST:-${FEAST_DATASTORE_EMULATOR_BIND_HOST}:${FEAST_DATASTORE_EMULATOR_PORT}}"
FEAST_DATASTORE_EMULATOR_RESET_URL="http://${DATASTORE_EMULATOR_HOST}/reset"

cd "$ROOT_DIR"

if [[ "$RESET_STATE" == "true" ]]; then
  rm -rf "$STATE_DIR"
  curl --retry 30 --retry-all-errors --retry-delay 1 -fsS -X POST "$FEAST_DATASTORE_EMULATOR_RESET_URL" >/dev/null
fi

mkdir -p "$STATE_DIR"

CONFIG_PATH="$(uv run python -m foehncast.feast_runtime)"
export FOEHNCAST_FEAST_CONFIG_PATH="$CONFIG_PATH"
export FEAST_FS_YAML_FILE_PATH="$CONFIG_PATH"

uv run python -m foehncast.feature_pipeline.feast export \
  --dataset "$DATASET" \
  --output "$OUTPUT_PATH" >/dev/null

cd "$ROOT_DIR/feature_repo"
uv run --group feast feast apply >/dev/null

if [[ "$MATERIALIZE" == "true" ]]; then
  uv run --group feast feast materialize-incremental "$MATERIALIZE_TS" >/dev/null
fi

printf 'Prepared Feast repo for dataset %s\n' "$DATASET"
printf 'Runtime config: %s\n' "$CONFIG_PATH"
printf 'Offline source: %s\n' "$OUTPUT_PATH"
printf 'Local Feast state: %s\n' "$STATE_DIR"
printf 'Online store: Datastore emulator at %s\n' "$DATASTORE_EMULATOR_HOST"

if [[ "$MATERIALIZE" == "true" ]]; then
  printf 'Materialized through: %s\n' "$MATERIALIZE_TS"
else
  printf 'Next: cd %s/feature_repo && uv run --group feast feast materialize-incremental "%s"\n' "$ROOT_DIR" "$MATERIALIZE_TS"
fi
