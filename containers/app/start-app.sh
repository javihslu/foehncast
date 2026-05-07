#!/bin/sh

# Start the FastAPI inference service inside the local container stack.

set -eu

host="${UVICORN_HOST:-0.0.0.0}"
port="${UVICORN_PORT:-${PORT:-8000}}"
repo_path="${FOEHNCAST_FEAST_REPO_PATH:-/workspace/feature_repo}"

python -c "import feast" >/dev/null 2>&1 || {
  echo >&2 "Feast runtime dependency is missing from this image"
  exit 1
}

if [ ! -d "$repo_path" ] || [ ! -f "$repo_path/feature_store.yaml" ]; then
  echo >&2 "Configured Feast repo is not available at $repo_path"
  exit 1
fi

config_path="$(python -m foehncast.feast_runtime)"
export FOEHNCAST_FEAST_CONFIG_PATH="$config_path"
export FEAST_FS_YAML_FILE_PATH="$config_path"

exec uvicorn foehncast.inference_pipeline.serve:app \
  --host "$host" \
  --port "$port"
