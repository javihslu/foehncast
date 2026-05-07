#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE=""
TFVARS_FILE=""
TARGET_REPO=""
PROJECT_ID=""
REGION="europe-west6"
REF=""
DRY_RUN=false
KEEP_ENVIRONMENT=false
KEEP_TEMP_FILES=false
ALLOW_SHARED_REPO=false
TEMP_WORK_DIR=""
CREATED_ENV_FILE=false
CREATED_TFVARS_FILE=false

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/terraform-platform-state.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/github-common.sh"

usage() {
  echo "Usage: $0 --repo owner/repo [--project-id id] [--region region] [--ref branch] [--env-file path] [--tfvars-file path] [--keep-environment] [--keep-temp-files] [--allow-shared-repo] [--dry-run]" >&2
  echo "Runs an interactive bootstrap-only setup, then drives remote apply, destroy, and cleanup for a disposable smoke environment." >&2
}

default_project_id() {
  printf 'fcast-smoke-%s-%04x\n' "$(date +%m%d%H%M)" "$((RANDOM % 65536))"
}

ensure_temp_workspace() {
  if [[ -n "$TEMP_WORK_DIR" ]]; then
    return
  fi

  TEMP_WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/foehncast-smoke.XXXXXX")"
}

ensure_safe_repo() {
  if [[ -z "$TARGET_REPO" ]]; then
    echo "--repo owner/repo is required. Use a fork or disposable repository for this smoke pass." >&2
    exit 1
  fi

  if [[ "$TARGET_REPO" != */* ]]; then
    echo "Repository must use owner/repo format, got: ${TARGET_REPO}" >&2
    exit 1
  fi

  if [[ "$TARGET_REPO" == "javihslu/foehncast" && "$ALLOW_SHARED_REPO" != "true" ]]; then
    echo "Refusing to target javihslu/foehncast because this smoke flow rewrites and later clears repository variables." >&2
    echo "Use a fork or disposable repository instead, or rerun with --allow-shared-repo if you explicitly want that behavior." >&2
    exit 1
  fi
}

validate_project_id() {
  if [[ ! "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
    echo "Project id must match GCP constraints: start with a letter, use lowercase letters, digits, or hyphens, and be 6-30 characters long." >&2
    exit 1
  fi
}

prepare_local_inputs() {
  local repo_owner repo_name artifact_repo artifact_bucket cloud_run_service

  repo_owner="${TARGET_REPO%%/*}"
  repo_name="${TARGET_REPO#*/}"
  artifact_repo="foehncast-docker"
  artifact_bucket="foehncast-artifacts-${PROJECT_ID}"
  cloud_run_service="foehncast-serve"

  if [[ -z "$ENV_FILE" ]]; then
    ensure_temp_workspace
    ENV_FILE="${TEMP_WORK_DIR}/foehncast-smoke.env"
    CREATED_ENV_FILE=true
  fi

  if [[ -z "$TFVARS_FILE" ]]; then
    ensure_temp_workspace
    TFVARS_FILE="${TEMP_WORK_DIR}/foehncast-smoke.tfvars"
    CREATED_TFVARS_FILE=true
  fi

  prepare_file_from_template "${ROOT_DIR}/.env.example" "$ENV_FILE"
  prepare_file_from_template "${ROOT_DIR}/terraform/terraform.tfvars.example" "$TFVARS_FILE"

  apply_foehncast_cloud_env_values \
    "$PROJECT_ID" \
    "$REGION" \
    "$artifact_bucket" \
    "foehncast" \
    "$REGION" \
    "forecast_features" \
    "feast-online" \
    "$cloud_run_service"

  apply_foehncast_cloud_tfvars_values \
    "$PROJECT_ID" \
    "$REGION" \
    "$artifact_repo" \
    "$artifact_bucket" \
    "foehncast" \
    "$REGION" \
    "forecast_features" \
    "$REGION" \
    "feast-online" \
    false \
    "$cloud_run_service" \
    "" \
    false
  set_tfvars_string github_owner "$repo_owner"
  set_tfvars_string github_repository "$repo_name"
}

print_command() {
  printf '+ '
  printf '%q ' "$@"
  printf '\n'
}

run_step() {
  local message="$1"
  shift

  echo
  echo "$message"
  print_command "$@"

  if [[ "$DRY_RUN" == "true" ]]; then
    return
  fi

  "$@"
}

cleanup_temp_files() {
  local status="$1"

  if [[ "$status" -ne 0 ]]; then
    KEEP_TEMP_FILES=true
  fi

  if [[ "$KEEP_TEMP_FILES" == "true" ]]; then
    echo
    echo "Smoke files kept for inspection:"
    echo "- env file: ${ENV_FILE}"
    echo "- tfvars file: ${TFVARS_FILE}"
    return
  fi

  if [[ "$CREATED_ENV_FILE" == "true" ]]; then
    rm -f "$ENV_FILE"
  fi
  if [[ "$CREATED_TFVARS_FILE" == "true" ]]; then
    rm -f "$TFVARS_FILE"
  fi
  if [[ -n "$TEMP_WORK_DIR" ]]; then
    rmdir "$TEMP_WORK_DIR" 2>/dev/null || true
  fi
}

on_exit() {
  local status=$?

  cleanup_temp_files "$status"
  exit "$status"
}

trap on_exit EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      shift
      TARGET_REPO="${1:-}"
      ;;
    --project-id)
      shift
      PROJECT_ID="${1:-}"
      ;;
    --region)
      shift
      REGION="${1:-}"
      ;;
    --ref)
      shift
      REF="${1:-}"
      ;;
    --env-file)
      shift
      ENV_FILE="${1:-}"
      ;;
    --tfvars-file)
      shift
      TFVARS_FILE="${1:-}"
      ;;
    --keep-environment)
      KEEP_ENVIRONMENT=true
      ;;
    --keep-temp-files)
      KEEP_TEMP_FILES=true
      ;;
    --allow-shared-repo)
      ALLOW_SHARED_REPO=true
      ;;
    --dry-run)
      DRY_RUN=true
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

ensure_safe_repo

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(default_project_id)"
fi

validate_project_id

if [[ "$DRY_RUN" == "true" || "$KEEP_ENVIRONMENT" == "true" ]]; then
  KEEP_TEMP_FILES=true
fi

prepare_local_inputs

echo "Disposable bootstrap-only smoke configuration:"
echo "- repository: ${TARGET_REPO}"
echo "- project_id: ${PROJECT_ID}"
echo "- region: ${REGION}"
echo "- env file: ${ENV_FILE}"
echo "- tfvars file: ${TFVARS_FILE}"
if [[ -n "$REF" ]]; then
  echo "- workflow ref: ${REF}"
fi
if [[ "$KEEP_ENVIRONMENT" == "true" ]]; then
  echo "- keep environment: true"
fi
if [[ "$DRY_RUN" == "true" ]]; then
  echo "- dry run: true"
fi

echo
echo "The bootstrap step may still prompt for gcloud login, project creation, or billing linkage if the disposable project does not exist yet."

bootstrap_args=("${ROOT_DIR}/scripts/bootstrap-gcp.sh" --bootstrap-only --configure-github-actions --repo "$TARGET_REPO" --env-file "$ENV_FILE" --tfvars-file "$TFVARS_FILE" --auto-approve)
run_step "Bootstrapping the remote-control-plane prerequisites" "${bootstrap_args[@]}"

remote_common_args=(--repo "$TARGET_REPO" --env-file "$ENV_FILE" --project-id "$PROJECT_ID" --region "$REGION" --wait)
if [[ -n "$REF" ]]; then
  remote_common_args+=(--ref "$REF")
fi

run_step "Applying the broader platform through the remote Terraform workflow" "${ROOT_DIR}/scripts/terraform-remote.sh" apply "${remote_common_args[@]}"

if [[ "$KEEP_ENVIRONMENT" == "true" ]]; then
  echo
  echo "Bootstrap-only smoke apply completed. The environment was kept for inspection."
  exit 0
fi

run_step "Destroying the remote Terraform-managed resources" "${ROOT_DIR}/scripts/terraform-remote.sh" destroy "${remote_common_args[@]}"
run_step "Clearing the remote backend state bucket and repository variables" "${ROOT_DIR}/scripts/terraform-remote.sh" cleanup "${remote_common_args[@]}" --cleanup-delete-state-bucket --cleanup-clear-github-actions
run_step "Queuing the disposable GCP project for deletion" "${ROOT_DIR}/scripts/teardown-gcp.sh" --env-file "$ENV_FILE" --tfvars-file "$TFVARS_FILE" --delete-project --auto-approve

echo
echo "Bootstrap-only smoke pass completed."
