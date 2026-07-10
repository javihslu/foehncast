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

require_any_env_value() {
  local error_message="$1"
  shift
  local env_name

  for env_name in "$@"; do
    if [[ -n "${!env_name:-}" ]]; then
      return
    fi
  done

  echo "$error_message" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-materialize)
      MATERIALIZE=false
      ;;
    --materialize-to)
      shift
      MATERIALIZE_TS="$(require_cli_option_value "--materialize-to" "${1:-}" usage)"
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
require_any_env_value "Set GCP_PROJECT_ID or FOEHNCAST_FEAST_PROJECT_ID in .env or the environment." \
  FOEHNCAST_FEAST_PROJECT_ID GCP_PROJECT_ID STORAGE_BIGQUERY_PROJECT_ID GOOGLE_CLOUD_PROJECT
require_any_env_value "Set FOEHNCAST_FEAST_GCS_BUCKET or FOEHNCAST_FEAST_REGISTRY in .env or the environment." \
  FOEHNCAST_FEAST_GCS_BUCKET FOEHNCAST_FEAST_REGISTRY
require_any_env_value "Set FOEHNCAST_FEAST_GCS_BUCKET or FOEHNCAST_FEAST_GCS_STAGING_LOCATION in .env or the environment." \
  FOEHNCAST_FEAST_GCS_BUCKET FOEHNCAST_FEAST_GCS_STAGING_LOCATION

CONFIG_PATH="$(render_feast_runtime_config_path "$ROOT_DIR")"
export_feast_runtime_config_path "$CONFIG_PATH"

run_feast_repo_apply_and_maybe_materialize "$ROOT_DIR/feature_repo" "$MATERIALIZE" "$MATERIALIZE_TS"

printf 'Prepared hosted Feast runtime\n'
printf 'Runtime config: %s\n' "$CONFIG_PATH"
printf 'Offline source table: %s\n' "$FOEHNCAST_FEAST_BIGQUERY_TABLE"
printf 'Online store database: %s\n' "${FOEHNCAST_FEAST_DATASTORE_DATABASE:-feast-online}"

print_feast_materialize_status "$ROOT_DIR" "$MATERIALIZE" "$MATERIALIZE_TS"
