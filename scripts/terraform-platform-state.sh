#!/usr/bin/env bash

terraform_outputs_available() {
  local terraform_dir="$1"
  local outputs_json

  outputs_json="$(run_terraform -chdir="$terraform_dir" output -json 2>/dev/null || true)"
  [[ -n "$outputs_json" && "$outputs_json" != "{}" ]]
}

terraform_output_value() {
  local terraform_dir="$1"
  local output_name="$2"

  run_terraform -chdir="$terraform_dir" output -raw "$output_name"
}

optional_terraform_output_value() {
  local terraform_dir="$1"
  local output_name="$2"

  run_terraform -chdir="$terraform_dir" output -raw "$output_name" 2>/dev/null || true
}

trim_terraform_platform_value() {
  local value="$1"

  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

terraform_platform_tfvars_file() {
  local terraform_dir="$1"

  if [[ -n "${FOEHNCAST_TERRAFORM_TFVARS_FILE:-}" ]]; then
    printf '%s\n' "$FOEHNCAST_TERRAFORM_TFVARS_FILE"
    return
  fi

  printf '%s/terraform.tfvars\n' "$terraform_dir"
}

read_tfvars_value_from_file() {
  local tfvars_file="$1"
  local key="$2"
  local line value

  if [[ ! -f "$tfvars_file" ]]; then
    return
  fi

  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$tfvars_file" | tail -n 1 || true)"

  if [[ -z "$line" ]]; then
    return
  fi

  value="${line#*=}"
  value="$(trim_terraform_platform_value "$value")"

  if [[ "$value" == \"*\" ]]; then
    value="${value#\"}"
    value="${value%\"}"
  fi

  printf '%s\n' "$value"
}

terraform_output_or_tfvars_value() {
  local terraform_dir="$1"
  local output_name="$2"
  local tfvars_key="$3"
  local output_value tfvars_file

  output_value="$(optional_terraform_output_value "$terraform_dir" "$output_name")"
  output_value="$(trim_terraform_platform_value "$output_value")"

  if [[ -n "$output_value" && "$output_value" != "null" ]]; then
    printf '%s\n' "$output_value"
    return
  fi

  tfvars_file="$(terraform_platform_tfvars_file "$terraform_dir")"
  read_tfvars_value_from_file "$tfvars_file" "$tfvars_key"
}

foehncast_default_cloud_run_image() {
  local location="$1"
  local project_id="$2"
  local artifact_repository="$3"

  printf '%s-docker.pkg.dev/%s/%s/foehncast-app:latest\n' "$location" "$project_id" "$artifact_repository"
}

foehncast_default_online_compose_host_zone() {
  local location="$1"

  printf '%s-b\n' "$location"
}

foehncast_cloud_env_pairs() {
  local project_id="$1"
  local location="$2"
  local artifact_bucket_name="$3"
  local bigquery_dataset="$4"
  local bigquery_location="$5"
  local bigquery_table="$6"
  local feast_online_store_database="$7"
  local cloud_run_service="${8:-}"
  local feast_bigquery_table feast_registry feast_staging_location

  feast_bigquery_table="${project_id}.${bigquery_dataset}.${bigquery_table}"
  feast_registry="gs://${artifact_bucket_name}/feast/registry.db"
  feast_staging_location="gs://${artifact_bucket_name}/feast/staging"

  printf 'GCP_PROJECT_ID\t%s\n' "$project_id"
  printf 'GCP_LOCATION\t%s\n' "$location"
  printf 'GCP_BUCKET_NAME\t%s\n' "$artifact_bucket_name"
  printf 'MLFLOW_ARTIFACT_DESTINATION\t%s\n' "gs://${artifact_bucket_name}/mlflow/artifacts"
  printf 'STORAGE_BIGQUERY_PROJECT_ID\t%s\n' "$project_id"
  printf 'STORAGE_BIGQUERY_DATASET\t%s\n' "$bigquery_dataset"
  printf 'STORAGE_BIGQUERY_TABLE\t%s\n' "$bigquery_table"
  printf 'FOEHNCAST_FEAST_SOURCE\t%s\n' 'bigquery'
  printf 'FOEHNCAST_FEAST_PROJECT\t%s\n' 'foehncast'
  printf 'FOEHNCAST_FEAST_PROJECT_ID\t%s\n' "$project_id"
  printf 'FOEHNCAST_FEAST_REGISTRY\t%s\n' "$feast_registry"
  printf 'FOEHNCAST_FEAST_GCS_BUCKET\t%s\n' "$artifact_bucket_name"
  printf 'FOEHNCAST_FEAST_GCS_STAGING_LOCATION\t%s\n' "$feast_staging_location"
  printf 'FOEHNCAST_FEAST_BIGQUERY_DATASET\t%s\n' "$bigquery_dataset"
  printf 'FOEHNCAST_FEAST_BIGQUERY_LOCATION\t%s\n' "$bigquery_location"
  printf 'FOEHNCAST_FEAST_BIGQUERY_TABLE\t%s\n' "$feast_bigquery_table"
  printf 'FOEHNCAST_FEAST_DATASTORE_DATABASE\t%s\n' "$feast_online_store_database"

  if [[ -n "$cloud_run_service" ]]; then
    printf 'CLOUD_RUN_SERVICE_NAME\t%s\n' "$cloud_run_service"
  fi
}

apply_foehncast_cloud_env_values() {
  while IFS=$'\t' read -r key value; do
    set_env_value "$key" "$value"
  done < <(foehncast_cloud_env_pairs "$@")
}

apply_foehncast_cloud_tfvars_values() {
  local project_id="$1"
  local location="$2"
  local artifact_repository="$3"
  local artifact_bucket_name="$4"
  local bigquery_dataset="$5"
  local bigquery_location="$6"
  local bigquery_table="$7"
  local feast_online_store_location="$8"
  local feast_online_store_database="$9"
  local provision_cloud_run_service="${10}"
  local cloud_run_service_name="${11}"
  local mlflow_tracking_uri="${12}"
  local provision_online_compose_host="${13}"
  local online_compose_host_name="${14:-foehncast-online}"
  local online_compose_host_zone="${15:-$(foehncast_default_online_compose_host_zone "$location")}"
  local online_compose_machine_type="${16:-e2-standard-4}"
  local online_compose_disk_size_gb="${17:-40}"

  set_tfvars_string project_id "$project_id"
  set_tfvars_string region "$location"
  set_tfvars_string artifact_registry_repository_id "$artifact_repository"
  set_tfvars_string artifact_bucket_name "$artifact_bucket_name"
  set_tfvars_string bigquery_dataset_id "$bigquery_dataset"
  set_tfvars_string bigquery_location "$bigquery_location"
  set_tfvars_string bigquery_feature_table_id "$bigquery_table"
  set_tfvars_string feast_online_store_location "$feast_online_store_location"
  set_tfvars_string feast_online_store_database_name "$feast_online_store_database"
  set_tfvars_bool provision_cloud_run_service "$provision_cloud_run_service"
  set_tfvars_string cloud_run_service_name "$cloud_run_service_name"
  set_tfvars_string cloud_run_image "$(foehncast_default_cloud_run_image "$location" "$project_id" "$artifact_repository")"
  set_tfvars_string mlflow_tracking_uri "$mlflow_tracking_uri"
  set_tfvars_bool provision_online_compose_host "$provision_online_compose_host"
  set_tfvars_string online_compose_host_name "$online_compose_host_name"
  set_tfvars_string online_compose_host_zone "$online_compose_host_zone"
  set_tfvars_string online_compose_machine_type "$online_compose_machine_type"
  set_tfvars_number online_compose_disk_size_gb "$online_compose_disk_size_gb"
}

load_terraform_platform_state() {
  local terraform_dir="$1"

  FOEHNCAST_TF_PROJECT_ID="$(terraform_output_or_tfvars_value "$terraform_dir" project_id project_id)"
  FOEHNCAST_TF_LOCATION="$(terraform_output_or_tfvars_value "$terraform_dir" region region)"
  FOEHNCAST_TF_ARTIFACT_REPOSITORY="$(terraform_output_or_tfvars_value "$terraform_dir" artifact_registry_repository_id artifact_registry_repository_id)"
  FOEHNCAST_TF_ARTIFACT_BUCKET_NAME="$(terraform_output_or_tfvars_value "$terraform_dir" artifact_bucket_name artifact_bucket_name)"
  FOEHNCAST_TF_BIGQUERY_DATASET="$(terraform_output_or_tfvars_value "$terraform_dir" bigquery_dataset_id bigquery_dataset_id)"
  FOEHNCAST_TF_BIGQUERY_LOCATION="$(terraform_output_or_tfvars_value "$terraform_dir" bigquery_location bigquery_location)"
  FOEHNCAST_TF_BIGQUERY_TABLE="$(terraform_output_or_tfvars_value "$terraform_dir" bigquery_feature_table_id bigquery_feature_table_id)"
  FOEHNCAST_TF_FEAST_ONLINE_STORE_LOCATION="$(terraform_output_or_tfvars_value "$terraform_dir" feast_online_store_location feast_online_store_location)"
  FOEHNCAST_TF_FEAST_ONLINE_STORE_DATABASE="$(terraform_output_or_tfvars_value "$terraform_dir" feast_online_store_database_name feast_online_store_database_name)"
  FOEHNCAST_TF_WORKLOAD_IDENTITY_PROVIDER="$(optional_terraform_output_value "$terraform_dir" github_workload_identity_provider)"
  FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL="$(optional_terraform_output_value "$terraform_dir" github_deployer_service_account)"
  FOEHNCAST_TF_RUNTIME_SERVICE_ACCOUNT="$(optional_terraform_output_value "$terraform_dir" cloud_run_runtime_service_account)"
  FOEHNCAST_TF_PROVISION_CLOUD_RUN_SERVICE="$(terraform_output_or_tfvars_value "$terraform_dir" provision_cloud_run_service provision_cloud_run_service)"
  FOEHNCAST_TF_CLOUD_RUN_SERVICE_NAME="$(terraform_output_or_tfvars_value "$terraform_dir" configured_cloud_run_service_name cloud_run_service_name)"
  FOEHNCAST_TF_CLOUD_RUN_CONTAINER_PORT="$(terraform_output_or_tfvars_value "$terraform_dir" configured_cloud_run_container_port cloud_run_container_port)"
  FOEHNCAST_TF_CLOUD_RUN_ALLOW_UNAUTHENTICATED="$(terraform_output_or_tfvars_value "$terraform_dir" configured_cloud_run_allow_unauthenticated cloud_run_allow_unauthenticated)"
  FOEHNCAST_TF_CLOUD_RUN_MIN_INSTANCE_COUNT="$(terraform_output_or_tfvars_value "$terraform_dir" configured_cloud_run_min_instance_count cloud_run_min_instance_count)"
  FOEHNCAST_TF_CLOUD_RUN_MAX_INSTANCE_COUNT="$(terraform_output_or_tfvars_value "$terraform_dir" configured_cloud_run_max_instance_count cloud_run_max_instance_count)"
  FOEHNCAST_TF_CLOUD_RUN_CPU="$(terraform_output_or_tfvars_value "$terraform_dir" configured_cloud_run_cpu cloud_run_cpu)"
  FOEHNCAST_TF_CLOUD_RUN_MEMORY="$(terraform_output_or_tfvars_value "$terraform_dir" configured_cloud_run_memory cloud_run_memory)"
  FOEHNCAST_TF_MLFLOW_TRACKING_URI="$(terraform_output_or_tfvars_value "$terraform_dir" mlflow_tracking_uri mlflow_tracking_uri)"
  FOEHNCAST_TF_CLOUD_RUN_SERVICE="$(optional_terraform_output_value "$terraform_dir" cloud_run_service_name)"
  FOEHNCAST_TF_PROVISION_ONLINE_COMPOSE_HOST="$(terraform_output_or_tfvars_value "$terraform_dir" provision_online_compose_host provision_online_compose_host)"
  FOEHNCAST_TF_ONLINE_COMPOSE_HOST_NAME="$(terraform_output_or_tfvars_value "$terraform_dir" online_compose_host_name online_compose_host_name)"
  FOEHNCAST_TF_ONLINE_COMPOSE_HOST_ZONE="$(terraform_output_or_tfvars_value "$terraform_dir" online_compose_host_zone online_compose_host_zone)"
  FOEHNCAST_TF_ONLINE_COMPOSE_MACHINE_TYPE="$(terraform_output_or_tfvars_value "$terraform_dir" online_compose_machine_type online_compose_machine_type)"
  FOEHNCAST_TF_ONLINE_COMPOSE_DISK_SIZE_GB="$(terraform_output_or_tfvars_value "$terraform_dir" online_compose_disk_size_gb online_compose_disk_size_gb)"
  FOEHNCAST_TF_STATE_BUCKET="${FOEHNCAST_TF_PROJECT_ID}-foehncast-tfstate"
  FOEHNCAST_TF_STATE_PREFIX="terraform/state"
}

terraform_repo_variable_names() {
  printf '%s\n' \
    GCP_PROJECT_ID \
    GCP_LOCATION \
    GCP_ARTIFACT_REPOSITORY \
    GCP_ARTIFACT_BUCKET_NAME \
    GCP_BIGQUERY_DATASET \
    GCP_BIGQUERY_LOCATION \
    GCP_BIGQUERY_TABLE \
    GCP_FEAST_ONLINE_STORE_LOCATION \
    GCP_FEAST_ONLINE_STORE_DATABASE_NAME \
    GCP_WORKLOAD_IDENTITY_PROVIDER \
    GCP_SERVICE_ACCOUNT_EMAIL \
    GCP_TERRAFORM_STATE_BUCKET \
    GCP_TERRAFORM_STATE_PREFIX \
    GCP_PROVISION_CLOUD_RUN_SERVICE \
    GCP_CLOUD_RUN_SERVICE_NAME \
    GCP_CLOUD_RUN_CONTAINER_PORT \
    GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED \
    GCP_CLOUD_RUN_MIN_INSTANCE_COUNT \
    GCP_CLOUD_RUN_MAX_INSTANCE_COUNT \
    GCP_CLOUD_RUN_CPU \
    GCP_CLOUD_RUN_MEMORY \
    GCP_MLFLOW_TRACKING_URI \
    GCP_PROVISION_ONLINE_COMPOSE_HOST \
    GCP_ONLINE_COMPOSE_HOST_NAME \
    GCP_ONLINE_COMPOSE_HOST_ZONE \
    GCP_ONLINE_COMPOSE_MACHINE_TYPE \
    GCP_ONLINE_COMPOSE_DISK_SIZE_GB \
    GCP_CLOUD_RUN_SERVICE
}

terraform_repo_variable_pairs() {
  local terraform_dir="$1"

  load_terraform_platform_state "$terraform_dir"

  printf 'GCP_PROJECT_ID\t%s\n' "$FOEHNCAST_TF_PROJECT_ID"
  printf 'GCP_LOCATION\t%s\n' "$FOEHNCAST_TF_LOCATION"
  printf 'GCP_ARTIFACT_REPOSITORY\t%s\n' "$FOEHNCAST_TF_ARTIFACT_REPOSITORY"
  printf 'GCP_ARTIFACT_BUCKET_NAME\t%s\n' "$FOEHNCAST_TF_ARTIFACT_BUCKET_NAME"
  printf 'GCP_BIGQUERY_DATASET\t%s\n' "$FOEHNCAST_TF_BIGQUERY_DATASET"
  printf 'GCP_BIGQUERY_LOCATION\t%s\n' "$FOEHNCAST_TF_BIGQUERY_LOCATION"
  printf 'GCP_BIGQUERY_TABLE\t%s\n' "$FOEHNCAST_TF_BIGQUERY_TABLE"
  printf 'GCP_FEAST_ONLINE_STORE_LOCATION\t%s\n' "$FOEHNCAST_TF_FEAST_ONLINE_STORE_LOCATION"
  printf 'GCP_FEAST_ONLINE_STORE_DATABASE_NAME\t%s\n' "$FOEHNCAST_TF_FEAST_ONLINE_STORE_DATABASE"
  printf 'GCP_WORKLOAD_IDENTITY_PROVIDER\t%s\n' "$FOEHNCAST_TF_WORKLOAD_IDENTITY_PROVIDER"
  printf 'GCP_SERVICE_ACCOUNT_EMAIL\t%s\n' "$FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL"
  printf 'GCP_TERRAFORM_STATE_BUCKET\t%s\n' "$FOEHNCAST_TF_STATE_BUCKET"
  printf 'GCP_TERRAFORM_STATE_PREFIX\t%s\n' "$FOEHNCAST_TF_STATE_PREFIX"
  printf 'GCP_PROVISION_CLOUD_RUN_SERVICE\t%s\n' "$FOEHNCAST_TF_PROVISION_CLOUD_RUN_SERVICE"
  printf 'GCP_CLOUD_RUN_SERVICE_NAME\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_SERVICE_NAME"
  printf 'GCP_CLOUD_RUN_CONTAINER_PORT\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_CONTAINER_PORT"
  printf 'GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_ALLOW_UNAUTHENTICATED"
  printf 'GCP_CLOUD_RUN_MIN_INSTANCE_COUNT\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_MIN_INSTANCE_COUNT"
  printf 'GCP_CLOUD_RUN_MAX_INSTANCE_COUNT\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_MAX_INSTANCE_COUNT"
  printf 'GCP_CLOUD_RUN_CPU\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_CPU"
  printf 'GCP_CLOUD_RUN_MEMORY\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_MEMORY"
  printf 'GCP_PROVISION_ONLINE_COMPOSE_HOST\t%s\n' "$FOEHNCAST_TF_PROVISION_ONLINE_COMPOSE_HOST"
  printf 'GCP_ONLINE_COMPOSE_HOST_NAME\t%s\n' "$FOEHNCAST_TF_ONLINE_COMPOSE_HOST_NAME"
  printf 'GCP_ONLINE_COMPOSE_HOST_ZONE\t%s\n' "$FOEHNCAST_TF_ONLINE_COMPOSE_HOST_ZONE"
  printf 'GCP_ONLINE_COMPOSE_MACHINE_TYPE\t%s\n' "$FOEHNCAST_TF_ONLINE_COMPOSE_MACHINE_TYPE"
  printf 'GCP_ONLINE_COMPOSE_DISK_SIZE_GB\t%s\n' "$FOEHNCAST_TF_ONLINE_COMPOSE_DISK_SIZE_GB"

  if [[ -n "$FOEHNCAST_TF_MLFLOW_TRACKING_URI" ]]; then
    printf 'GCP_MLFLOW_TRACKING_URI\t%s\n' "$FOEHNCAST_TF_MLFLOW_TRACKING_URI"
  fi

  if [[ -n "$FOEHNCAST_TF_CLOUD_RUN_SERVICE" ]]; then
    printf 'GCP_CLOUD_RUN_SERVICE\t%s\n' "$FOEHNCAST_TF_CLOUD_RUN_SERVICE"
  fi
}
