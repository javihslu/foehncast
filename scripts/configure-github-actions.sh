#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="${ROOT_DIR}/terraform"
TARGET_REPO="${TARGET_REPO:-}"
DRY_RUN=false

usage() {
  echo "Usage: $0 [--dry-run] [--repo owner/repo] [--terraform-dir path]" >&2
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required but not installed." >&2
    exit 1
  fi
}

terraform_output() {
  local output_name="$1"

  terraform -chdir="$TERRAFORM_DIR" output -raw "$output_name"
}

optional_terraform_output() {
  local output_name="$1"

  terraform -chdir="$TERRAFORM_DIR" output -raw "$output_name" 2>/dev/null || true
}

resolve_repo() {
  local origin_url

  if [[ -n "$TARGET_REPO" ]]; then
    printf '%s\n' "$TARGET_REPO"
    return
  fi

  origin_url="$(git -C "$ROOT_DIR" config --get remote.origin.url || true)"

  if [[ "$origin_url" =~ ^git@github\.com:([^/]+)/([^.]+)(\.git)?$ ]]; then
    printf '%s/%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return
  fi

  if [[ "$origin_url" =~ ^https://github\.com/([^/]+)/([^.]+)(\.git)?$ ]]; then
    printf '%s/%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return
  fi

  echo "Unable to determine the GitHub repository from remote.origin.url. Use --repo owner/repo." >&2
  exit 1
}

set_variable() {
  local repository_path="$1"
  local variable_name="$2"
  local variable_value="$3"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "Would set ${variable_name}=${variable_value} on ${repository_path}"
    return
  fi

  gh variable set "$variable_name" --repo "$repository_path" --body "$variable_value"
  echo "Set ${variable_name} on ${repository_path}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      ;;
    --repo)
      shift
      TARGET_REPO="${1:-}"
      if [[ -z "$TARGET_REPO" ]]; then
        usage
        exit 1
      fi
      ;;
    --terraform-dir)
      shift
      TERRAFORM_DIR="${1:-}"
      if [[ -z "$TERRAFORM_DIR" ]]; then
        usage
        exit 1
      fi
      ;;
    *)
      usage
      exit 1
      ;;
  esac
  shift
done

require_command terraform

if [[ "$DRY_RUN" != "true" ]]; then
  require_command gh

  if ! gh auth status >/dev/null 2>&1; then
    echo "gh is installed but not authenticated. Run 'gh auth login' first." >&2
    exit 1
  fi
fi

TERRAFORM_OUTPUTS_JSON="$(terraform -chdir="$TERRAFORM_DIR" output -json 2>/dev/null || true)"

if [[ -z "$TERRAFORM_OUTPUTS_JSON" || "$TERRAFORM_OUTPUTS_JSON" == "{}" ]]; then
  echo "Terraform outputs are not available in ${TERRAFORM_DIR}. Run 'terraform apply' first." >&2
  exit 1
fi

REPOSITORY_PATH="$(resolve_repo)"
PROJECT_ID="$(terraform_output project_id)"
LOCATION="$(terraform_output region)"
ARTIFACT_REPOSITORY="$(terraform_output artifact_registry_repository_id)"
WORKLOAD_IDENTITY_PROVIDER="$(terraform_output github_workload_identity_provider)"
SERVICE_ACCOUNT_EMAIL="$(terraform_output github_deployer_service_account)"
CLOUD_RUN_SERVICE="$(optional_terraform_output cloud_run_service_name)"

set_variable "$REPOSITORY_PATH" GCP_PROJECT_ID "$PROJECT_ID"
set_variable "$REPOSITORY_PATH" GCP_LOCATION "$LOCATION"
set_variable "$REPOSITORY_PATH" GCP_ARTIFACT_REPOSITORY "$ARTIFACT_REPOSITORY"
set_variable "$REPOSITORY_PATH" GCP_WORKLOAD_IDENTITY_PROVIDER "$WORKLOAD_IDENTITY_PROVIDER"
set_variable "$REPOSITORY_PATH" GCP_SERVICE_ACCOUNT_EMAIL "$SERVICE_ACCOUNT_EMAIL"

if [[ -n "$CLOUD_RUN_SERVICE" ]]; then
  set_variable "$REPOSITORY_PATH" GCP_CLOUD_RUN_SERVICE "$CLOUD_RUN_SERVICE"
else
  echo "Skipping GCP_CLOUD_RUN_SERVICE because Terraform has not provisioned a Cloud Run service yet."
fi

echo "GitHub Actions variables are configured for ${REPOSITORY_PATH}."
