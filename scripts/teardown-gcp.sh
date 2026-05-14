#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="${ROOT_DIR}/terraform"
ENV_FILE="${ROOT_DIR}/.env"
TARGET_REPO=""
CLEAR_GITHUB_ACTIONS=false
DELETE_STATE_BUCKET=false
DELETE_PROJECT=false
AUTO_APPROVE=false
PLAN_ONLY=false
GCP_CONTEXT_READY=false

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/terraform-platform-state.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/gcp-common.sh"
TFVARS_FILE="$(default_terraform_tfvars_file "$TERRAFORM_DIR")"

usage() {
  echo "Usage: $0 [--env-file path] [--tfvars-file path] [--plan-only] [--auto-approve] [--clear-github-actions] [--delete-state-bucket] [--delete-project] [--repo owner/repo]" >&2
}

require_destroy_tfvars_file() {
  require_file "$TFVARS_FILE" "Terraform variables file not found: $TFVARS_FILE. Reuse the file created for provisioning so destroy targets the same settings."
}

print_enabled_message() {
  local flag_value="$1"
  local enabled_message="$2"

  if [[ "$flag_value" == "true" ]]; then
    echo "$enabled_message"
  fi
}

print_state_message() {
  local flag_value="$1"
  local enabled_message="$2"
  local disabled_message="$3"

  if [[ "$flag_value" == "true" ]]; then
    echo "$enabled_message"
    return
  fi

  echo "$disabled_message"
}

print_remote_backend_destroy_guidance() {
  echo "Use ./scripts/terraform-remote.sh destroy when the active environment is managed through the remote backend."
}

print_no_local_terraform_state_message() {
  local state_message="$1"

  echo "No local Terraform state was found in ${ROOT_DIR}/terraform. ${state_message}"
  print_remote_backend_destroy_guidance
}

print_missing_destroy_tfvars_preview_message() {
  echo "Terraform variables file not found: $TFVARS_FILE. Nothing to preview in this working copy."
  echo "Reuse the file created for provisioning to preview local destroy targets, or use ./scripts/terraform-remote.sh destroy when the active environment is managed through the remote backend."
}

has_local_terraform_state() {
  [[ -f "${ROOT_DIR}/terraform/terraform.tfstate" || -f "${ROOT_DIR}/terraform/terraform.tfstate.backup" ]]
}

ensure_gcp_context() {
  local require_initialized_env="$1"

  if [[ "$GCP_CONTEXT_READY" == "true" ]]; then
    return
  fi

  require_command gcloud

  if [[ "$require_initialized_env" == "true" ]]; then
    require_file "$ENV_FILE" "Env file not found: $ENV_FILE. Initialize it with ./scripts/bootstrap-gcp.sh first."
  fi

  verify_gcp_project_access "$ENV_FILE" "${ROOT_DIR}/scripts/gcp-auth.sh"

  GCP_CONTEXT_READY=true
}

delete_state_bucket() {
  local state_bucket="${GCP_TERRAFORM_STATE_BUCKET:-${GCP_PROJECT_ID}-foehncast-tfstate}"

  if ! gcloud storage buckets describe "gs://${state_bucket}" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    echo "Terraform state bucket gs://${state_bucket} was not found. Skipping delete."
    return
  fi

  echo "Deleting Terraform state bucket gs://${state_bucket}..."
  gcloud storage rm --recursive "gs://${state_bucket}/**" >/dev/null 2>&1 || true
  gcloud storage buckets delete "gs://${state_bucket}" --project "$GCP_PROJECT_ID" --quiet
}

delete_project() {
  local lifecycle_state

  lifecycle_state="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(lifecycleState)' 2>/dev/null || true)"

  if [[ -z "$lifecycle_state" ]]; then
    echo "GCP project ${GCP_PROJECT_ID} was not found. Skipping delete."
    return
  fi

  if [[ "$lifecycle_state" == "DELETE_REQUESTED" ]]; then
    echo "GCP project ${GCP_PROJECT_ID} is already pending deletion. Skipping delete."
    return
  fi

  echo "Deleting GCP project ${GCP_PROJECT_ID}..."
  gcloud projects delete "$GCP_PROJECT_ID" --quiet
}

confirm_project_delete() {
  local confirmation

  if [[ "$AUTO_APPROVE" == "true" ]]; then
    return
  fi

  if [[ ! -t 0 ]]; then
    echo "--delete-project requires --auto-approve when stdin is not interactive." >&2
    exit 1
  fi

  read -r -p "Type the GCP project id (${GCP_PROJECT_ID}) to confirm deletion: " confirmation
  if [[ "$confirmation" != "$GCP_PROJECT_ID" ]]; then
    echo "Project deletion cancelled." >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      shift
      ENV_FILE="$(require_cli_option_value "--env-file" "${1:-}" usage)"
      ;;
    --tfvars-file)
      shift
      TFVARS_FILE="$(require_cli_option_value "--tfvars-file" "${1:-}" usage)"
      ;;
    --plan-only)
      PLAN_ONLY=true
      ;;
    --auto-approve)
      AUTO_APPROVE=true
      ;;
    --clear-github-actions)
      CLEAR_GITHUB_ACTIONS=true
      ;;
    --delete-state-bucket)
      DELETE_STATE_BUCKET=true
      ;;
    --delete-project)
      DELETE_PROJECT=true
      ;;
    --repo)
      shift
      TARGET_REPO="$(require_cli_option_value "--repo" "${1:-}" usage)"
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

if [[ "$PLAN_ONLY" == "true" && "$AUTO_APPROVE" == "true" ]]; then
  echo "--plan-only and --auto-approve cannot be used together." >&2
  exit 1
fi

HAS_LOCAL_TERRAFORM_STATE=false
if has_local_terraform_state; then
  HAS_LOCAL_TERRAFORM_STATE=true
fi

if [[ "$PLAN_ONLY" == "true" ]]; then
  if [[ "$HAS_LOCAL_TERRAFORM_STATE" == "false" ]]; then
    print_no_local_terraform_state_message "Nothing to preview in this working copy."
  elif [[ ! -f "$TFVARS_FILE" ]]; then
    print_missing_destroy_tfvars_preview_message
  else
    ensure_terraform_command
    require_destroy_tfvars_file
    ensure_gcp_context true

    echo "Initializing Terraform..."
    run_terraform -chdir="${ROOT_DIR}/terraform" init

    echo "Previewing Terraform destroy plan..."
    run_terraform -chdir="${ROOT_DIR}/terraform" plan -destroy -var-file="$TFVARS_FILE"

    echo "Teardown preview complete for ${GCP_PROJECT_ID}."
  fi

  echo "Terraform-managed resources were not destroyed."
  print_enabled_message "$CLEAR_GITHUB_ACTIONS" "GitHub Actions variables were not changed because --plan-only was set."
  print_enabled_message "$DELETE_STATE_BUCKET" "The Terraform state bucket was not changed because --plan-only was set."
  print_enabled_message "$DELETE_PROJECT" "The GCP project was not changed because --plan-only was set."

  exit 0
fi

if [[ "$HAS_LOCAL_TERRAFORM_STATE" == "false" && "$CLEAR_GITHUB_ACTIONS" != "true" && "$DELETE_STATE_BUCKET" != "true" && "$DELETE_PROJECT" != "true" ]]; then
  print_no_local_terraform_state_message "Nothing to destroy in this working copy."
  exit 0
fi

TERRAFORM_DESTROYED=false

if [[ "$HAS_LOCAL_TERRAFORM_STATE" == "true" ]]; then
  ensure_terraform_command
  require_destroy_tfvars_file
  ensure_gcp_context true

  echo "Initializing Terraform..."
  run_terraform -chdir="${ROOT_DIR}/terraform" init

  destroy_args=(destroy -var-file="$TFVARS_FILE")
  if [[ "$AUTO_APPROVE" == "true" ]]; then
    destroy_args+=(-auto-approve)
  fi

  echo "Destroying Terraform-managed resources..."
  run_terraform -chdir="${ROOT_DIR}/terraform" "${destroy_args[@]}"
  TERRAFORM_DESTROYED=true
else
  print_no_local_terraform_state_message "Skipping Terraform destroy path."
fi

if [[ "$CLEAR_GITHUB_ACTIONS" == "true" ]]; then
  github_args=(--clear)
  if [[ -n "$TARGET_REPO" ]]; then
    github_args+=(--repo "$TARGET_REPO")
  fi

  echo "Clearing GitHub Actions repository variables..."
  "${ROOT_DIR}/scripts/configure-github-actions.sh" "${github_args[@]}"
fi

if [[ "$DELETE_STATE_BUCKET" == "true" ]]; then
  ensure_gcp_context false
  delete_state_bucket
fi

if [[ "$DELETE_PROJECT" == "true" ]]; then
  ensure_gcp_context false
  confirm_project_delete
  delete_project
fi

echo "Teardown complete."
print_state_message "$TERRAFORM_DESTROYED" "Terraform destroy completed using ${TFVARS_FILE}." "Terraform-managed resources were left unchanged."
print_state_message "$CLEAR_GITHUB_ACTIONS" "GitHub Actions variables were cleared." "GitHub Actions variables were left unchanged."
print_state_message "$DELETE_STATE_BUCKET" "The Terraform state bucket cleanup path was executed." "The Terraform state bucket was left unchanged."
print_state_message "$DELETE_PROJECT" "The GCP project delete path was executed." "The GCP project was left unchanged."
