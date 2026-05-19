#!/usr/bin/env bash
# resolve-terraform-inputs.sh — Resolves Terraform variable values from workflow
# inputs and repository variables, applying defaults and validation.
#
# Expects environment variables:
#   REPO_GCP_*       — Repository variables (loaded by load-gcp-repo-config action)
#   INPUT_*          — Workflow dispatch inputs (optional overrides)
#   GITHUB_OWNER     — Repository owner
#   GITHUB_REPOSITORY_NAME — Repository name
#
# Outputs TF_VAR_* and TF_* lines to stdout. Append to $GITHUB_ENV in CI.
#
# Usage:
#   ./scripts/resolve-terraform-inputs.sh >> "$GITHUB_ENV"
set -euo pipefail

# ─── Helpers ──────────────────────────────────────────────────────────────────

normalize_bool() {
  local name="$1"
  local value="$2"
  case "$value" in
    true|false) printf '%s\n' "$value" ;;
    *) echo "${name} must resolve to true or false, got '${value}'." >&2; exit 1 ;;
  esac
}

normalize_non_negative_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "${name} must resolve to a non-negative integer, got '${value}'." >&2
    exit 1
  fi
  printf '%s\n' "$value"
}

normalize_positive_integer() {
  local name="$1"
  local value="$2"
  value="$(normalize_non_negative_integer "$name" "$value")"
  if [[ "$value" -lt 1 ]]; then
    echo "${name} must resolve to an integer greater than zero, got '${value}'." >&2
    exit 1
  fi
  printf '%s\n' "$value"
}

# ─── Resolve each variable (input > repo var > default) ──────────────────────

project_id="${INPUT_PROJECT_ID:-$REPO_GCP_PROJECT_ID}"
if [[ -z "$project_id" ]]; then
  echo "Set project_id in the workflow input or repository variable GCP_PROJECT_ID." >&2
  exit 1
fi

region="${INPUT_REGION:-${REPO_GCP_LOCATION:-europe-west6}}"

artifact_bucket_name="${INPUT_ARTIFACT_BUCKET_NAME:-${REPO_GCP_ARTIFACT_BUCKET_NAME:-foehncast-artifacts-${project_id}}}"

state_bucket="${REPO_GCP_TERRAFORM_STATE_BUCKET:-${project_id}-foehncast-tfstate}"
state_prefix="${REPO_GCP_TERRAFORM_STATE_PREFIX:-terraform/state}"

artifact_registry_repository_id="${INPUT_ARTIFACT_REGISTRY_REPOSITORY_ID:-${REPO_GCP_ARTIFACT_REPOSITORY:-foehncast-docker}}"

bigquery_dataset_id="${INPUT_BIGQUERY_DATASET_ID:-${REPO_GCP_BIGQUERY_DATASET:-foehncast}}"
bigquery_location="${INPUT_BIGQUERY_LOCATION:-${REPO_GCP_BIGQUERY_LOCATION:-$region}}"
bigquery_feature_table_id="${INPUT_BIGQUERY_FEATURE_TABLE_ID:-${REPO_GCP_BIGQUERY_TABLE:-forecast_features}}"

feast_online_store_location="${INPUT_FEAST_ONLINE_STORE_LOCATION:-${REPO_GCP_FEAST_ONLINE_STORE_LOCATION:-$region}}"
feast_online_store_database_name="${INPUT_FEAST_ONLINE_STORE_DATABASE_NAME:-${REPO_GCP_FEAST_ONLINE_STORE_DATABASE_NAME:-feast-online}}"

# ─── Cloud Run settings ──────────────────────────────────────────────────────

provision_cloud_run_service="${INPUT_PROVISION_CLOUD_RUN_SERVICE:-${REPO_GCP_PROVISION_CLOUD_RUN_SERVICE:-false}}"
provision_cloud_run_service="$(normalize_bool provision_cloud_run_service "$provision_cloud_run_service")"

mlflow_tracking_uri="${INPUT_MLFLOW_TRACKING_URI:-$REPO_GCP_MLFLOW_TRACKING_URI}"

cloud_run_service_name="${INPUT_CLOUD_RUN_SERVICE_NAME:-${REPO_GCP_CLOUD_RUN_SERVICE_NAME:-${REPO_GCP_CLOUD_RUN_SERVICE:-foehncast-serve}}}"

cloud_run_container_port="${REPO_GCP_CLOUD_RUN_CONTAINER_PORT:-8080}"
cloud_run_container_port="$(normalize_positive_integer cloud_run_container_port "$cloud_run_container_port")"

cloud_run_allow_unauthenticated="${INPUT_CLOUD_RUN_ALLOW_UNAUTHENTICATED:-${REPO_GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED:-true}}"
cloud_run_allow_unauthenticated="$(normalize_bool cloud_run_allow_unauthenticated "$cloud_run_allow_unauthenticated")"

cloud_run_min_instance_count="${REPO_GCP_CLOUD_RUN_MIN_INSTANCE_COUNT:-0}"
cloud_run_min_instance_count="$(normalize_non_negative_integer cloud_run_min_instance_count "$cloud_run_min_instance_count")"

cloud_run_max_instance_count="${REPO_GCP_CLOUD_RUN_MAX_INSTANCE_COUNT:-2}"
cloud_run_max_instance_count="$(normalize_non_negative_integer cloud_run_max_instance_count "$cloud_run_max_instance_count")"
if [[ "$cloud_run_max_instance_count" -lt "$cloud_run_min_instance_count" ]]; then
  echo "cloud_run_max_instance_count must be >= cloud_run_min_instance_count." >&2
  exit 1
fi

cloud_run_cpu="${REPO_GCP_CLOUD_RUN_CPU:-1}"
cloud_run_memory="${REPO_GCP_CLOUD_RUN_MEMORY:-512Mi}"

# ─── MLflow and UI ───────────────────────────────────────────────────────────

provision_cloud_run_mlflow="${REPO_GCP_PROVISION_CLOUD_RUN_MLFLOW:-false}"
provision_cloud_run_mlflow="$(normalize_bool provision_cloud_run_mlflow "$provision_cloud_run_mlflow")"

if [[ "$provision_cloud_run_service" == 'true' && "$provision_cloud_run_mlflow" != 'true' && -z "$mlflow_tracking_uri" ]]; then
  echo "Resolve mlflow_tracking_uri when provision_cloud_run_service is true and provision_cloud_run_mlflow is false." >&2
  exit 1
fi

cloud_run_ui_prometheus_url="${REPO_GCP_CLOUD_RUN_UI_PROMETHEUS_URL:-}"

provision_cloud_run_ui="${REPO_GCP_PROVISION_CLOUD_RUN_UI:-false}"
provision_cloud_run_ui="$(normalize_bool provision_cloud_run_ui "$provision_cloud_run_ui")"

provision_cloud_workflows="${REPO_GCP_PROVISION_CLOUD_WORKFLOWS:-false}"
provision_cloud_workflows="$(normalize_bool provision_cloud_workflows "$provision_cloud_workflows")"

cloud_run_image="${REPO_GCP_CLOUD_RUN_IMAGE:-}"

# ─── Command and confirmations ───────────────────────────────────────────────

terraform_command="${INPUT_COMMAND:-plan}"
destroy_confirmation="${INPUT_DESTROY_CONFIRMATION:-}"
cleanup_confirmation="${INPUT_CLEANUP_CONFIRMATION:-}"
cleanup_clear_github_actions="${INPUT_CLEANUP_CLEAR_GITHUB_ACTIONS:-false}"
cleanup_delete_state_bucket="${INPUT_CLEANUP_DELETE_STATE_BUCKET:-false}"

# ─── Output ──────────────────────────────────────────────────────────────────

cat <<ENVVARS
TF_COMMAND=${terraform_command}
TF_DESTROY_CONFIRMATION=${destroy_confirmation}
TF_CLEANUP_CONFIRMATION=${cleanup_confirmation}
TF_CLEANUP_CLEAR_GITHUB_ACTIONS=${cleanup_clear_github_actions}
TF_CLEANUP_DELETE_STATE_BUCKET=${cleanup_delete_state_bucket}
TF_VAR_cloud_run_image=${cloud_run_image}
TF_VAR_project_id=${project_id}
TF_VAR_region=${region}
TF_VAR_artifact_bucket_name=${artifact_bucket_name}
TF_VAR_artifact_registry_repository_id=${artifact_registry_repository_id}
TF_VAR_bigquery_dataset_id=${bigquery_dataset_id}
TF_VAR_bigquery_location=${bigquery_location}
TF_VAR_bigquery_feature_table_id=${bigquery_feature_table_id}
TF_VAR_feast_online_store_location=${feast_online_store_location}
TF_VAR_feast_online_store_database_name=${feast_online_store_database_name}
TF_VAR_provision_cloud_run_service=${provision_cloud_run_service}
TF_VAR_mlflow_tracking_uri=${mlflow_tracking_uri}
TF_VAR_cloud_run_service_name=${cloud_run_service_name}
TF_VAR_cloud_run_container_port=${cloud_run_container_port}
TF_VAR_cloud_run_allow_unauthenticated=${cloud_run_allow_unauthenticated}
TF_VAR_cloud_run_min_instance_count=${cloud_run_min_instance_count}
TF_VAR_cloud_run_max_instance_count=${cloud_run_max_instance_count}
TF_VAR_cloud_run_cpu=${cloud_run_cpu}
TF_VAR_cloud_run_memory=${cloud_run_memory}
TF_VAR_provision_cloud_run_mlflow=${provision_cloud_run_mlflow}
TF_VAR_cloud_run_ui_prometheus_url=${cloud_run_ui_prometheus_url}
TF_VAR_provision_cloud_run_ui=${provision_cloud_run_ui}
TF_VAR_provision_cloud_workflows=${provision_cloud_workflows}
TF_VAR_github_owner=${GITHUB_OWNER}
TF_VAR_github_repository=${GITHUB_REPOSITORY_NAME}
TF_STATE_BUCKET=${state_bucket}
TF_STATE_PREFIX=${state_prefix}
ENVVARS
