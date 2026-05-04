#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is required but not installed." >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env or the environment.}"
: "${GCP_LOCATION:?Set GCP_LOCATION in .env or the environment.}"

gcloud config set project "$GCP_PROJECT_ID"

if ! gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q .; then
  gcloud auth login
fi

if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  gcloud auth application-default login
fi

gcloud auth configure-docker "${GCP_LOCATION}-docker.pkg.dev"

echo "Configured gcloud CLI, ADC, and Artifact Registry auth for ${GCP_PROJECT_ID} in ${GCP_LOCATION}."
echo "For local BigQuery-backed containers, run Docker Compose with -f docker-compose.yml -f docker-compose.gcp.yml so ADC is mounted into the Linux services."
echo "Use GitHub OIDC for CI/CD and avoid storing service account keys in this repository."
