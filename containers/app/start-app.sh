#!/bin/sh

# Start the FastAPI inference service inside the local container stack.

set -eu

host="${UVICORN_HOST:-0.0.0.0}"
port="${UVICORN_PORT:-${PORT:-8000}}"

exec uvicorn foehncast.inference_pipeline.serve:app \
  --host "$host" \
  --port "$port"
