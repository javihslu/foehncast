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
INPUT_BIGQUERY_DATASET_ID=""
INPUT_BIGQUERY_FEATURE_TABLE_ID=""
INPUT_FEAST_ONLINE_STORE_DATABASE_NAME=""
DRY_RUN=false
WAIT_FOR_COMPLETION=false
WATCH_INTERVAL=3
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
  echo "Usage: $0 <plan|apply|destroy|cleanup> [--repo owner/repo] [--ref branch] [--env-file path] [--project-id id] [--region region] [--input key=value] [--cleanup-clear-github-actions] [--cleanup-delete-state-bucket] [--wait] [--watch-interval seconds] [--dry-run]" >&2
}

resolve_watch_ref() {
  local repository_path="$1"

  if [[ -n "$REF" ]]; then
    printf '%s\n' "$REF"
    return
  fi

  gh repo view "$repository_path" --json defaultBranchRef --jq '.defaultBranchRef.name'
}

latest_workflow_run_id() {
  local repository_path="$1"
  local branch_ref="$2"
  local triggering_user="${3:-}"
  local args

  args=(run list --repo "$repository_path" --workflow "$WORKFLOW_FILE" --event workflow_dispatch --limit 1 --json databaseId)
  if [[ -n "$branch_ref" ]]; then
    args+=(--branch "$branch_ref")
  fi
  if [[ -n "$triggering_user" ]]; then
    args+=(--user "$triggering_user")
  fi

  gh "${args[@]}" --jq '.[0].databaseId // ""' 2>/dev/null || true
}

wait_for_dispatched_run() {
  local repository_path="$1"
  local branch_ref="$2"
  local previous_run_id="$3"
  local triggering_user="$4"
  local run_id=""
  local attempt=0
  local run_url=""

  while (( attempt < 20 )); do
    run_id="$(latest_workflow_run_id "$repository_path" "$branch_ref" "$triggering_user")"
    if [[ -n "$run_id" && "$run_id" != "$previous_run_id" ]]; then
      break
    fi

    attempt=$((attempt + 1))
    sleep "$WATCH_INTERVAL"
  done

  if [[ -z "$run_id" || "$run_id" == "$previous_run_id" ]]; then
    echo "Unable to resolve the newly triggered Terraform workflow run on ${repository_path}." >&2
    exit 1
  fi

  run_url="$(gh run view "$run_id" --repo "$repository_path" --json url --jq '.url' 2>/dev/null || true)"
  if [[ -n "$run_url" ]]; then
    echo "Watching workflow run: ${run_url}"
  else
    echo "Watching workflow run id: ${run_id}"
  fi

  gh run watch "$run_id" --repo "$repository_path" --interval "$WATCH_INTERVAL" --exit-status
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

remote_feast_bigquery_dataset() {
  local value

  value="${INPUT_BIGQUERY_DATASET_ID:-}"
  if [[ -z "$value" ]]; then
    value="$(repo_variable_value "$REPOSITORY_PATH" GCP_BIGQUERY_DATASET)"
  fi
  if [[ -z "$value" ]]; then
    value="${GCP_BIGQUERY_DATASET:-${STORAGE_BIGQUERY_DATASET:-${FOEHNCAST_FEAST_BIGQUERY_DATASET:-foehncast}}}"
  fi

  printf '%s\n' "$value"
}

remote_feast_bigquery_table() {
  local runtime_table dataset table_id project_id

  if [[ -z "$INPUT_BIGQUERY_DATASET_ID" && -z "$INPUT_BIGQUERY_FEATURE_TABLE_ID" ]]; then
    runtime_table="${FOEHNCAST_FEAST_BIGQUERY_TABLE:-}"
    if [[ -n "$runtime_table" ]]; then
      printf '%s\n' "$runtime_table"
      return
    fi
  fi

  dataset="$(remote_feast_bigquery_dataset)"
  table_id="${INPUT_BIGQUERY_FEATURE_TABLE_ID:-}"
  if [[ -z "$table_id" ]]; then
    table_id="$(repo_variable_value "$REPOSITORY_PATH" GCP_BIGQUERY_TABLE)"
  fi
  if [[ -z "$table_id" ]]; then
    table_id="${GCP_BIGQUERY_TABLE:-${STORAGE_BIGQUERY_TABLE:-forecast_features}}"
  fi

  project_id="${PROJECT_ID:-<project_id>}"
  printf '%s.%s.%s\n' "$project_id" "$dataset" "$table_id"
}

remote_feast_online_store_database() {
  local value

  value="${INPUT_FEAST_ONLINE_STORE_DATABASE_NAME:-}"
  if [[ -z "$value" ]]; then
    value="$(repo_variable_value "$REPOSITORY_PATH" GCP_FEAST_ONLINE_STORE_DATABASE_NAME)"
  fi
  if [[ -z "$value" ]]; then
    value="${GCP_FEAST_ONLINE_STORE_DATABASE_NAME:-${FOEHNCAST_FEAST_DATASTORE_DATABASE:-feast-online}}"
  fi

  printf '%s\n' "$value"
}

print_remote_feast_follow_up() {
  echo "Hosted Feast runtime source: bigquery"
  echo "Hosted Feast offline source table: $(remote_feast_bigquery_table)"
  echo "Hosted Feast online store database: $(remote_feast_online_store_database)"

  if [[ "$WAIT_FOR_COMPLETION" == "true" ]]; then
    echo "After curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."
    return
  fi

  echo "After the remote apply succeeds and curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."
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
    bigquery_dataset_id)
      INPUT_BIGQUERY_DATASET_ID="$value"
      EXTRA_INPUTS+=("$input")
      ;;
    bigquery_feature_table_id)
      INPUT_BIGQUERY_FEATURE_TABLE_ID="$value"
      EXTRA_INPUTS+=("$input")
      ;;
    feast_online_store_database_name)
      INPUT_FEAST_ONLINE_STORE_DATABASE_NAME="$value"
      EXTRA_INPUTS+=("$input")
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
    --wait)
      WAIT_FOR_COMPLETION=true
      ;;
    --watch-interval)
      shift
      WATCH_INTERVAL="${1:-}"
      if [[ -z "$WATCH_INTERVAL" || ! "$WATCH_INTERVAL" =~ ^[0-9]+$ || "$WATCH_INTERVAL" -lt 1 ]]; then
        echo "--watch-interval expects a positive integer number of seconds." >&2
        exit 1
      fi
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

WATCH_REF=""
PREVIOUS_RUN_ID=""
TRIGGERING_USER=""
if [[ "$WAIT_FOR_COMPLETION" == "true" ]]; then
  WATCH_REF="$(resolve_watch_ref "$REPOSITORY_PATH")"
  TRIGGERING_USER="$(gh api user --jq '.login' 2>/dev/null || true)"
  PREVIOUS_RUN_ID="$(latest_workflow_run_id "$REPOSITORY_PATH" "$WATCH_REF" "$TRIGGERING_USER")"
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

if (( ${#EXTRA_INPUTS[@]} > 0 )); then
  for input in "${EXTRA_INPUTS[@]}"; do
    run_args+=( -f "$input" )
  done
fi

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
if [[ "$WAIT_FOR_COMPLETION" == "true" ]]; then
  echo "- wait: true"
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

if [[ "$WAIT_FOR_COMPLETION" == "true" ]]; then
  wait_for_dispatched_run "$REPOSITORY_PATH" "$WATCH_REF" "$PREVIOUS_RUN_ID" "$TRIGGERING_USER"
fi

if [[ "$COMMAND" == "apply" ]]; then
  echo
  print_remote_feast_follow_up
fi
