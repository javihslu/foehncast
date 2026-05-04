#!/bin/sh

# Sync the project environment with uv, then keep the container running for
# local development.

set -eu

uv sync
exec tail -f /dev/null
