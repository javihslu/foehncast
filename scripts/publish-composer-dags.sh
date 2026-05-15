#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAG_GCS_PREFIX=""
BUNDLE_DIR=""
MANIFEST_PATH=""
TEMP_WORK_DIR=""
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"

usage() {
  echo "Usage: $0 --dag-gcs-prefix gs://bucket/path [--bundle-dir path] [--manifest-path path]" >&2
}

cleanup() {
  if [[ -n "$TEMP_WORK_DIR" && -d "$TEMP_WORK_DIR" ]]; then
    rm -rf "$TEMP_WORK_DIR"
  fi
}

trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dag-gcs-prefix)
      shift
      DAG_GCS_PREFIX="$(require_cli_option_value "--dag-gcs-prefix" "${1:-}" usage)"
      ;;
    --bundle-dir)
      shift
      BUNDLE_DIR="$(require_cli_option_value "--bundle-dir" "${1:-}" usage)"
      ;;
    --manifest-path)
      shift
      MANIFEST_PATH="$(require_cli_option_value "--manifest-path" "${1:-}" usage)"
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

if [[ -z "$DAG_GCS_PREFIX" ]]; then
  usage
  exit 1
fi

require_command gcloud
require_command python3

DAG_GCS_PREFIX="$(printf '%s' "$DAG_GCS_PREFIX" | tr -d '\r')"
DAG_GCS_PREFIX="${DAG_GCS_PREFIX%/}"

if [[ -z "$BUNDLE_DIR" ]]; then
  TEMP_WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/foehncast-composer-dags.XXXXXX")"
  BUNDLE_DIR="${TEMP_WORK_DIR}/bundle"
fi

if [[ -z "$MANIFEST_PATH" ]]; then
  MANIFEST_PATH="${BUNDLE_DIR}.manifest.json"
fi

mkdir -p "$(dirname "$MANIFEST_PATH")"

env PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m foehncast.composer_bundle build \
  --project-root "$ROOT_DIR" \
  --output-dir "$BUNDLE_DIR" \
  --manifest-path "$MANIFEST_PATH" >/dev/null

gcloud storage rsync --recursive "$BUNDLE_DIR" "$DAG_GCS_PREFIX"

printf 'Composer DAG bundle published to %s\n' "$DAG_GCS_PREFIX"
printf 'Bundle directory: %s\n' "$BUNDLE_DIR"
printf 'Manifest: %s\n' "$MANIFEST_PATH"
