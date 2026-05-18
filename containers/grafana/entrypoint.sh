#!/bin/sh
# Entrypoint wrapper for Grafana on Cloud Run.
#
# GRAFANA_PROMETHEUS_URL should point to the FoehnCast serve endpoint which
# exposes a Prometheus-compatible query API (/api/v1/query, /query_range).
# On GCP the serve endpoint is public (allUsers invoker), so no auth is needed.

set -e

echo "[entrypoint] GRAFANA_PROMETHEUS_URL=${GRAFANA_PROMETHEUS_URL:-<not set>}"

exec /run.sh "$@"
