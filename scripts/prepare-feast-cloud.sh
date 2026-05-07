#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/gcp-common.sh"

require_command uv
load_env_file "$ENV_FILE"

MATERIALIZE=true
MATERIALIZE_TS="${FEAST_MATERIALIZE_TIMESTAMP:-$(date -u +"%Y-%m-%dT%H:%M:%S")}"

usage() {
  echo "Usage: $0 [--skip-materialize] [--materialize-to timestamp]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-materialize)
      MATERIALIZE=false
      ;;
    --materialize-to)
      shift
      if [[ $# -eq 0 ]]; then
        echo "Missing value for --materialize-to" >&2
        usage
        exit 1
      fi
      MATERIALIZE_TS="$1"
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
      echo "Unexpected argument: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

export FOEHNCAST_FEAST_SOURCE="${FOEHNCAST_FEAST_SOURCE:-bigquery}"

if [[ "$FOEHNCAST_FEAST_SOURCE" != "bigquery" ]]; then
  echo "prepare-feast-cloud.sh requires FOEHNCAST_FEAST_SOURCE=bigquery" >&2
  exit 1
fi

require_env_var FOEHNCAST_FEAST_BIGQUERY_TABLE "Set FOEHNCAST_FEAST_BIGQUERY_TABLE in .env or the environment."

if [[ -z "${FOEHNCAST_FEAST_PROJECT_ID:-}" && -z "${GCP_PROJECT_ID:-}" && -z "${STORAGE_BIGQUERY_PROJECT_ID:-}" && -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
  echo "Set GCP_PROJECT_ID or FOEHNCAST_FEAST_PROJECT_ID in .env or the environment." >&2
  exit 1
fi

if [[ -z "${FOEHNCAST_FEAST_GCS_BUCKET:-}" && -z "${GCP_BUCKET_NAME:-}" && -z "${FOEHNCAST_FEAST_REGISTRY:-}" ]]; then
  echo "Set GCP_BUCKET_NAME, FOEHNCAST_FEAST_GCS_BUCKET, or FOEHNCAST_FEAST_REGISTRY in .env or the environment." >&2
  exit 1
fi

CONFIG_PATH="$(cd "$ROOT_DIR" && uv run python -m foehncast.feast_runtime)"
export FOEHNCAST_FEAST_CONFIG_PATH="$CONFIG_PATH"
export FEAST_FS_YAML_FILE_PATH="$CONFIG_PATH"

cd "$ROOT_DIR/feature_repo"
uv run --group feast feast apply >/dev/null

if [[ "$MATERIALIZE" == "true" ]]; then
  uv run --group feast feast materialize-incremental "$MATERIALIZE_TS" >/dev/null
fi

printf 'Prepared hosted Feast runtime\n'
printf 'Runtime config: %s\n' "$CONFIG_PATH"
printf 'Offline source table: %s\n' "$FOEHNCAST_FEAST_BIGQUERY_TABLE"
printf 'Online store database: %s\n' "${FOEHNCAST_FEAST_DATASTORE_DATABASE:-feast-online}"

if [[ "$MATERIALIZE" == "true" ]]; then
  printf 'Materialized through: %s\n' "$MATERIALIZE_TS"
else
  printf 'Next: cd %s/feature_repo && uv run --group feast feast materialize-incremental "%s"\n' "$ROOT_DIR" "$MATERIALIZE_TS"
fi
