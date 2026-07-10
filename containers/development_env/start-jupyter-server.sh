#!/bin/sh

set -eu

kernel_python="${UV_PROJECT_ENVIRONMENT:-/home/appuser/.venv}/bin/python"
port="${JUPYTER_PORT:-8888}"
token="${JUPYTER_TOKEN:-foehncast-local}"

exec "$kernel_python" -m jupyterlab \
    --ServerApp.ip=0.0.0.0 \
    --ServerApp.port="$port" \
    --ServerApp.open_browser=False \
    --ServerApp.token="$token" \
    --ServerApp.password='' \
    --ServerApp.allow_remote_access=False \
    --ServerApp.root_dir=/workspace
