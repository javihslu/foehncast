#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
TFVARS_FILE="${ROOT_DIR}/terraform/terraform.tfvars"
CONFIGURE_GITHUB=false
TARGET_REPO=""
PLAN_ONLY=false
AUTO_APPROVE=false

usage() {
  echo "Usage: $0 [--env-file path] [--tfvars-file path] [--plan-only] [--auto-approve] [--configure-github-actions] [--repo owner/repo]" >&2
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required but not installed." >&2
    exit 1
  fi
}

require_file() {
  local file_path="$1"
  local help_message="$2"

  if [[ ! -f "$file_path" ]]; then
    echo "$help_message" >&2
    exit 1
  fi
}

load_env_file() {
  local file_path="$1"

  set -a
  # shellcheck disable=SC1090
  source "$file_path"
  set +a
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      shift
      ENV_FILE="${1:-}"
      ;;
    --tfvars-file)
      shift
      TFVARS_FILE="${1:-}"
      ;;
    --configure-github-actions)
      CONFIGURE_GITHUB=true
      ;;
    --repo)
      shift
      TARGET_REPO="${1:-}"
      ;;
    --plan-only)
      PLAN_ONLY=true
      ;;
    --auto-approve)
      AUTO_APPROVE=true
      ;;
    --help|-h)
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

require_command gcloud
require_command terraform

if [[ "$CONFIGURE_GITHUB" == "true" ]]; then
  require_command gh
fi

require_file "$ENV_FILE" "Env file not found: $ENV_FILE. Copy .env.example to .env and set GCP_PROJECT_ID and GCP_LOCATION first."
require_file "$TFVARS_FILE" "Terraform variables file not found: $TFVARS_FILE. Copy terraform/terraform.tfvars.example and fill the project-specific values first."

load_env_file "$ENV_FILE"

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env or the environment.}"
: "${GCP_LOCATION:?Set GCP_LOCATION in .env or the environment.}"

echo "Authenticating with Google Cloud via browser if needed..."
"${ROOT_DIR}/scripts/gcp-auth.sh" "$ENV_FILE"

echo "Checking access to GCP project ${GCP_PROJECT_ID}..."
if ! gcloud projects describe "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  echo "GCP project ${GCP_PROJECT_ID} is not accessible. Use an existing project with billing enabled before running this script." >&2
  exit 1
fi

echo "Initializing Terraform..."
terraform -chdir="${ROOT_DIR}/terraform" init

echo "Checking Terraform formatting and validation..."
terraform -chdir="${ROOT_DIR}/terraform" fmt -check
terraform -chdir="${ROOT_DIR}/terraform" validate

if [[ "$PLAN_ONLY" == "true" ]]; then
  echo "Running Terraform plan..."
  terraform -chdir="${ROOT_DIR}/terraform" plan -var-file="$TFVARS_FILE"
else
  apply_args=(apply -var-file="$TFVARS_FILE")

  if [[ "$AUTO_APPROVE" == "true" ]]; then
    apply_args+=( -auto-approve )
  fi

  echo "Running Terraform apply..."
  terraform -chdir="${ROOT_DIR}/terraform" "${apply_args[@]}"
fi

if [[ "$CONFIGURE_GITHUB" == "true" && "$PLAN_ONLY" != "true" ]]; then
  github_args=()

  if [[ -n "$TARGET_REPO" ]]; then
    github_args+=( --repo "$TARGET_REPO" )
  fi

  echo "Configuring GitHub Actions repository variables..."
  "${ROOT_DIR}/scripts/configure-github-actions.sh" "${github_args[@]}"
fi

echo "Bootstrap complete for ${GCP_PROJECT_ID}."
echo "This path assumes an existing GCP project with billing enabled. It does not create a new project for you."

if [[ "$CONFIGURE_GITHUB" == "true" && "$PLAN_ONLY" != "true" ]]; then
  echo "GitHub Actions variables were synchronized for repo-driven deployment automation."
else
  echo "GitHub Actions were not changed. That is fine for personal one-off environments."
fi
