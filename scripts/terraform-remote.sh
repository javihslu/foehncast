#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
WORKFLOW_FILE="terraform.yml"
TARGET_REPO=""
REF=""
COMMAND=""
PROJECT_ID=""
REGION=""
DRY_RUN=false
CLEANUP_CLEAR_GITHUB_ACTIONS=false
CLEANUP_DELETE_STATE_BUCKET=false
EXTRA_INPUTS=()

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/github-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/gcp-common.sh"

usage() {
  echo "Usage: $0 <plan|apply|destroy|cleanup> [--repo owner/repo] [--ref branch] [--env-file path] [--project-id id] [--region region] [--input key=value] [--cleanup-clear-github-actions] [--cleanup-delete-state-bucket] [--dry-run]" >&2
}

normalize_bool() {
  local value="$1"

  case "$value" in
    true|false)
      printf '%s\n' "$value"
      ;;
    *)
      echo "Boolean value must be true or false, got: ${value}" >&2
      exit 1
      ;;
  esac
}

repo_variable_value() {
  local repository_path="$1"
  local variable_name="$2"
  local value

  value="$(gh variable list --repo "$repository_path" --json name,value --jq ".[] | select(.name == \"${variable_name}\").value" 2>/dev/null || true)"
  if [[ "$value" == "null" ]]; then
    value=""
  fi

  printf '%s\n' "$value"
}

record_input() {
  local input="$1"
  local key value

  if [[ "$input" != *=* ]]; then
    echo "--input expects key=value, got: ${input}" >&2
    exit 1
  fi

  key="${input%%=*}"
  value="${input#*=}"

  case "$key" in
    command|destroy_confirmation|cleanup_confirmation)
      echo "${key} is managed by this helper. Use the positional command and flags instead." >&2
      exit 1
      ;;
    project_id)
      PROJECT_ID="$value"
      ;;
    region)
      REGION="$value"
      ;;
    cleanup_clear_github_actions)
      CLEANUP_CLEAR_GITHUB_ACTIONS="$(normalize_bool "$value")"
      ;;
    cleanup_delete_state_bucket)
      CLEANUP_DELETE_STATE_BUCKET="$(normalize_bool "$value")"
      ;;
    *)
      EXTRA_INPUTS+=("$input")
      ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    plan|apply|destroy|cleanup)
      if [[ -n "$COMMAND" ]]; then
        usage
        exit 1
      fi
      COMMAND="$1"
      ;;
    --repo)
      shift
      TARGET_REPO="${1:-}"
      if [[ -z "$TARGET_REPO" ]]; then
        usage
        exit 1
      fi
      ;;
    --ref)
      shift
      REF="${1:-}"
      if [[ -z "$REF" ]]; then
        usage
        exit 1
      fi
      ;;
    --env-file)
      shift
      ENV_FILE="${1:-}"
      if [[ -z "$ENV_FILE" ]]; then
        usage
        exit 1
      fi
      ;;
    --project-id)
      shift
      PROJECT_ID="${1:-}"
      if [[ -z "$PROJECT_ID" ]]; then
        usage
        exit 1
      fi
      ;;
    --region)
      shift
      REGION="${1:-}"
      if [[ -z "$REGION" ]]; then
        usage
        exit 1
      fi
      ;;
    --input)
      shift
      if [[ -z "${1:-}" ]]; then
        usage
        exit 1
      fi
      record_input "$1"
      ;;
    --cleanup-clear-github-actions)
      CLEANUP_CLEAR_GITHUB_ACTIONS=true
      ;;
    --cleanup-delete-state-bucket)
      CLEANUP_DELETE_STATE_BUCKET=true
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

if [[ -z "$COMMAND" ]]; then
  usage
  exit 1
fi

if [[ "$COMMAND" != "cleanup" && ( "$CLEANUP_CLEAR_GITHUB_ACTIONS" == "true" || "$CLEANUP_DELETE_STATE_BUCKET" == "true" ) ]]; then
  echo "Cleanup flags can only be used with the cleanup command." >&2
  exit 1
fi

require_command gh

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is installed but not authenticated. Run 'gh auth login' first." >&2
  exit 1
fi

load_env_file "$ENV_FILE"

REPOSITORY_PATH="$TARGET_REPO"
if [[ -z "$REPOSITORY_PATH" ]]; then
  REPOSITORY_PATH="$(require_repo_from_remote "$ROOT_DIR")"
fi

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(repo_variable_value "$REPOSITORY_PATH" GCP_PROJECT_ID)"
fi
if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="${GCP_PROJECT_ID:-}"
fi

if [[ -z "$REGION" ]]; then
  REGION="$(repo_variable_value "$REPOSITORY_PATH" GCP_LOCATION)"
fi
if [[ -z "$REGION" ]]; then
  REGION="${GCP_LOCATION:-}"
fi

if [[ "$COMMAND" == "destroy" || "$COMMAND" == "cleanup" ]]; then
  if [[ -z "$PROJECT_ID" ]]; then
    echo "Resolve the GCP project id first with --project-id, repository variable GCP_PROJECT_ID, or .env before running ${COMMAND}." >&2
    exit 1
  fi
fi

if [[ "$COMMAND" == "cleanup" && "$CLEANUP_CLEAR_GITHUB_ACTIONS" != "true" && "$CLEANUP_DELETE_STATE_BUCKET" != "true" ]]; then
  echo "Cleanup requires at least one action: --cleanup-clear-github-actions or --cleanup-delete-state-bucket." >&2
  exit 1
fi

run_args=(gh workflow run "$WORKFLOW_FILE" --repo "$REPOSITORY_PATH")
if [[ -n "$REF" ]]; then
  run_args+=(--ref "$REF")
fi

if [[ -n "$COMMAND" ]]; then
  run_args+=( -f "command=${COMMAND}" )
fi

if [[ -n "$PROJECT_ID" ]]; then
  run_args+=( -f "project_id=${PROJECT_ID}" )
fi

if [[ -n "$REGION" ]]; then
  run_args+=( -f "region=${REGION}" )
fi

if [[ "$COMMAND" == "destroy" ]]; then
  run_args+=( -f "destroy_confirmation=${PROJECT_ID}" )
fi

if [[ "$COMMAND" == "cleanup" ]]; then
  run_args+=( -f "cleanup_confirmation=${PROJECT_ID}" )
  run_args+=( -f "cleanup_clear_github_actions=${CLEANUP_CLEAR_GITHUB_ACTIONS}" )
  run_args+=( -f "cleanup_delete_state_bucket=${CLEANUP_DELETE_STATE_BUCKET}" )
fi

for input in "${EXTRA_INPUTS[@]}"; do
  run_args+=( -f "$input" )
done

echo "Triggering remote Terraform workflow on ${REPOSITORY_PATH}"
echo "- command: ${COMMAND}"
if [[ -n "$REF" ]]; then
  echo "- ref: ${REF}"
fi
if [[ -n "$PROJECT_ID" ]]; then
  echo "- project_id: ${PROJECT_ID}"
else
  echo "- project_id: deferred to repository variables or explicit workflow inputs"
fi
if [[ -n "$REGION" ]]; then
  echo "- region: ${REGION}"
fi
if [[ "$COMMAND" == "cleanup" ]]; then
  echo "- cleanup_clear_github_actions: ${CLEANUP_CLEAR_GITHUB_ACTIONS}"
  echo "- cleanup_delete_state_bucket: ${CLEANUP_DELETE_STATE_BUCKET}"
fi

if [[ "$DRY_RUN" == "true" ]]; then
  printf 'Dry run: '
  printf '%q ' "${run_args[@]}"
  printf '\n'
  exit 0
fi

"${run_args[@]}"
