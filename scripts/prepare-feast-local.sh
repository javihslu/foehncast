#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATASET="${1:-train}"
OUTPUT_PATH="$ROOT_DIR/data/feast/${DATASET}.parquet"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"

require_command uv

cd "$ROOT_DIR"

uv run python -m foehncast.feature_pipeline.feast export \
  --dataset "$DATASET" \
  --output "$OUTPUT_PATH" >/dev/null

cd "$ROOT_DIR/feature_repo"
uv run --group feast feast apply

NEXT_TS='$(date -u +"%Y-%m-%dT%H:%M:%S")'

printf 'Prepared Feast repo for dataset %s\n' "$DATASET"
printf 'Offline source: %s\n' "$OUTPUT_PATH"
printf 'Next: cd %s/feature_repo && uv run --group feast feast materialize-incremental "%s"\n' "$ROOT_DIR" "$NEXT_TS"
