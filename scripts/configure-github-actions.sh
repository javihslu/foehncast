#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="${ROOT_DIR}/terraform"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/terraform-platform-state.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/github-common.sh"
TARGET_REPO="${TARGET_REPO:-}"
DRY_RUN=false
CLEAR=false

usage() {
  echo "Usage: $0 [--dry-run] [--clear] [--repo owner/repo] [--terraform-dir path]" >&2
}

resolve_repo() {
  if [[ -n "$TARGET_REPO" ]]; then
    printf '%s\n' "$TARGET_REPO"
    return
  fi

  require_repo_from_remote "$ROOT_DIR"
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

delete_variable() {
  local repository_path="$1"
  local variable_name="$2"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "Would delete ${variable_name} from ${repository_path} if it exists"
    return
  fi

  gh variable delete "$variable_name" --repo "$repository_path" >/dev/null 2>&1 || true
  echo "Deleted ${variable_name} from ${repository_path} if it existed"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      ;;
    --clear)
      CLEAR=true
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

if [[ "$DRY_RUN" != "true" ]]; then
  require_command gh

  if ! gh auth status >/dev/null 2>&1; then
    echo "gh is installed but not authenticated. Run 'gh auth login' first." >&2
    exit 1
  fi
fi

REPOSITORY_PATH="$(resolve_repo)"

if [[ "$CLEAR" == "true" ]]; then
  while IFS= read -r variable_name; do
    delete_variable "$REPOSITORY_PATH" "$variable_name"
  done < <(terraform_repo_variable_names)

  echo "GitHub Actions variables were cleared for ${REPOSITORY_PATH}."
  exit 0
fi

require_command terraform

if ! terraform_outputs_available "$TERRAFORM_DIR"; then
  echo "Terraform outputs are not available in ${TERRAFORM_DIR}. Run 'terraform apply' first." >&2
  exit 1
fi

cloud_run_synced=false
mlflow_tracking_uri_synced=false
while IFS=$'\t' read -r variable_name variable_value; do
  set_variable "$REPOSITORY_PATH" "$variable_name" "$variable_value"

  if [[ "$variable_name" == "GCP_CLOUD_RUN_SERVICE" ]]; then
    cloud_run_synced=true
  fi

  if [[ "$variable_name" == "GCP_MLFLOW_TRACKING_URI" ]]; then
    mlflow_tracking_uri_synced=true
  fi
done < <(terraform_repo_variable_pairs "$TERRAFORM_DIR")

if [[ "$cloud_run_synced" != "true" ]]; then
  delete_variable "$REPOSITORY_PATH" GCP_CLOUD_RUN_SERVICE
  echo "Skipping GCP_CLOUD_RUN_SERVICE because Terraform has not provisioned a Cloud Run service yet."
fi

if [[ "$mlflow_tracking_uri_synced" != "true" ]]; then
  delete_variable "$REPOSITORY_PATH" GCP_MLFLOW_TRACKING_URI
  echo "Skipping GCP_MLFLOW_TRACKING_URI because Terraform does not currently define an MLflow tracking URI."
fi

echo "GitHub Actions variables are configured for ${REPOSITORY_PATH}."
echo "Use ./scripts/terraform-remote.sh for common remote Terraform plan, apply, destroy, and cleanup commands."
