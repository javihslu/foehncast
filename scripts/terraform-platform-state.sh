#!/usr/bin/env bash

terraform_outputs_available() {
  local terraform_dir="$1"
  local outputs_json

  outputs_json="$(terraform -chdir="$terraform_dir" output -json 2>/dev/null || true)"
  [[ -n "$outputs_json" && "$outputs_json" != "{}" ]]
}

terraform_output_value() {
  local terraform_dir="$1"
  local output_name="$2"

  terraform -chdir="$terraform_dir" output -raw "$output_name"
}

optional_terraform_output_value() {
  local terraform_dir="$1"
  local output_name="$2"

  terraform -chdir="$terraform_dir" output -raw "$output_name" 2>/dev/null || true
}

load_terraform_platform_state() {
  local terraform_dir="$1"

  FOEHNCAST_TF_PROJECT_ID="$(terraform_output_value "$terraform_dir" project_id)"
  FOEHNCAST_TF_LOCATION="$(terraform_output_value "$terraform_dir" region)"
  FOEHNCAST_TF_ARTIFACT_REPOSITORY="$(terraform_output_value "$terraform_dir" artifact_registry_repository_id)"
  FOEHNCAST_TF_ARTIFACT_BUCKET_NAME="$(terraform_output_value "$terraform_dir" artifact_bucket_name)"
  FOEHNCAST_TF_BIGQUERY_DATASET="$(terraform_output_value "$terraform_dir" bigquery_dataset_id)"
  FOEHNCAST_TF_BIGQUERY_TABLE="$(terraform_output_value "$terraform_dir" bigquery_feature_table_id)"
  FOEHNCAST_TF_WORKLOAD_IDENTITY_PROVIDER="$(terraform_output_value "$terraform_dir" github_workload_identity_provider)"
  FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL="$(terraform_output_value "$terraform_dir" github_deployer_service_account)"
  FOEHNCAST_TF_RUNTIME_SERVICE_ACCOUNT="$(terraform_output_value "$terraform_dir" cloud_run_runtime_service_account)"
  FOEHNCAST_TF_CLOUD_RUN_SERVICE="$(optional_terraform_output_value "$terraform_dir" cloud_run_service_name)"
  FOEHNCAST_TF_STATE_BUCKET="${FOEHNCAST_TF_PROJECT_ID}-foehncast-tfstate"
  FOEHNCAST_TF_STATE_PREFIX="terraform/state"
}
