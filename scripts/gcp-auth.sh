#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env}"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/gcp-common.sh"

require_command gcloud

load_env_file "$ENV_FILE"

require_gcp_project_and_location

gcloud config set project "$GCP_PROJECT_ID"

ensure_gcloud_auth

gcloud auth configure-docker "${GCP_LOCATION}-docker.pkg.dev"

echo "Configured gcloud CLI, ADC, and Artifact Registry auth for ${GCP_PROJECT_ID} in ${GCP_LOCATION}."
echo "For local BigQuery-backed containers, run Docker Compose with -f docker-compose.yml -f docker-compose.gcp.yml so ADC is mounted into the Linux services."
echo "Use GitHub OIDC for CI/CD and avoid storing service account keys in this repository."
