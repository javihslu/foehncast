#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="${ROOT_DIR}/terraform"
ENV_FILE="${ROOT_DIR}/.env"
TFVARS_FILE="${ROOT_DIR}/terraform/terraform.tfvars"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/terraform-platform-state.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/gcp-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/github-common.sh"
CONFIGURE_GITHUB=false
TARGET_REPO=""
PLAN_ONLY=false
AUTO_APPROVE=false
BOOTSTRAP_ONLY=false
INTERACTIVE=true
TEMP_TERRAFORM_DIR=""

usage() {
  echo "Usage: $0 [--env-file path] [--tfvars-file path] [--plan-only] [--auto-approve] [--bootstrap-only] [--configure-github-actions] [--repo owner/repo] [--non-interactive]" >&2
  echo "Use ./scripts/bootstrap-local.sh for the default local evaluator path." >&2
  echo "Maintainer-only cloud bootstrap. Supported no-local-install path: run this from Google Cloud Shell." >&2
}

require_payload_pattern() {
  local payload="$1"
  local pattern="$2"
  local description="$3"

  if ! printf '%s' "$payload" | grep -Eq "$pattern"; then
    echo "Hosted bootstrap verification failed: expected ${description}." >&2
    printf '%s\n' "$payload" >&2
    exit 1
  fi
}

in_cloud_shell() {
  [[ -n "${CLOUD_SHELL:-}" || -n "${DEVSHELL_PROJECT_ID:-}" ]]
}

cleanup_bootstrap_terraform_dir() {
  if [[ -n "$TEMP_TERRAFORM_DIR" && -d "$TEMP_TERRAFORM_DIR" ]]; then
    rm -rf "$TEMP_TERRAFORM_DIR"
  fi
}

prepare_bootstrap_terraform_dir() {
  if [[ "$BOOTSTRAP_ONLY" != "true" || -n "$TEMP_TERRAFORM_DIR" ]]; then
    return
  fi

  TEMP_TERRAFORM_DIR="$(mktemp -d "${TMPDIR:-/tmp}/foehncast-terraform.XXXXXX")"
  cp -R "${ROOT_DIR}/terraform/." "$TEMP_TERRAFORM_DIR/"
  rm -rf "$TEMP_TERRAFORM_DIR/.terraform"
  rm -f "$TEMP_TERRAFORM_DIR/terraform.tfstate" "$TEMP_TERRAFORM_DIR/terraform.tfstate.backup"
  TERRAFORM_DIR="$TEMP_TERRAFORM_DIR"

  if [[ -f "${ROOT_DIR}/terraform/terraform.tfstate" || -d "${ROOT_DIR}/terraform/.terraform" ]]; then
    echo "Using an isolated Terraform working directory for bootstrap-only so local state files do not interfere with remote backend initialization."
  fi
}

trap cleanup_bootstrap_terraform_dir EXIT

print_bootstrap_context() {
  echo "Cloud bootstrap provisions a hosted GCP environment."
  echo "For the default local evaluator path, use ./scripts/bootstrap-local.sh instead."
  echo "This script is for the rare maintainer bootstrap case, not normal contributor onboarding."

  if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
    echo "Mode: bootstrap-only. This prepares the remote Terraform control plane and leaves the broader platform apply for the remote workflow."
  fi

  if in_cloud_shell; then
    echo "Execution context: Google Cloud Shell (supported first-time cloud bootstrap environment)."
  else
    echo "Execution context: local admin shell."
    echo "Tip: if you do not want local gcloud and Terraform installs, rerun this script from Google Cloud Shell."
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

trim_whitespace() {
  local value="$1"

  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

read_tfvars_value() {
  local key="$1"
  local line value

  if [[ ! -f "$TFVARS_FILE" ]]; then
    return
  fi

  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$TFVARS_FILE" | tail -n 1 || true)"

  if [[ -z "$line" ]]; then
    return
  fi

  value="${line#*=}"
  value="$(trim_whitespace "$value")"

  if [[ "$value" == \"*\" ]]; then
    value="${value#\"}"
    value="${value%\"}"
  fi

  printf '%s\n' "$value"
}

  terraform_fmt_supports_file() {
    local file_path="$1"

    case "$file_path" in
      *.tf|*.tfvars|*.tftest.hcl)
        return 0
        ;;
      *)
        return 1
        ;;
    esac
  }

  format_generated_tfvars_file() {
    local file_path="$1"

    if terraform_fmt_supports_file "$file_path"; then
      run_terraform fmt "$file_path" >/dev/null
      return
    fi

    echo "Skipping terraform fmt for ${file_path} because the filename does not end with .tf, .tfvars, or .tftest.hcl."
  }

  terraform_remote_state_bucket() {
    printf '%s\n' "${GCP_PROJECT_ID}-foehncast-tfstate"
  }

  terraform_remote_state_prefix() {
    printf '%s\n' "terraform/state"
  }

  ensure_remote_state_bucket() {
    local state_bucket

    state_bucket="$(terraform_remote_state_bucket)"

    if gcloud storage buckets describe "gs://${state_bucket}" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
      return
    fi

    echo "Creating remote Terraform state bucket gs://${state_bucket}..."
    gcloud storage buckets create "gs://${state_bucket}" \
      --project "$GCP_PROJECT_ID" \
      --location "$GCP_LOCATION" \
      --uniform-bucket-level-access
  }

  bootstrap_target_args() {
    printf '%s\n' \
      "-target=google_project_service.required" \
      "-target=google_service_account.github_deployer" \
      "-target=google_project_iam_member.github_project_admin" \
      "-target=google_project_iam_member.github_artifact_registry_writer" \
      "-target=google_project_iam_member.github_cloud_run_admin" \
      "-target=google_project_iam_member.github_service_account_user" \
      "-target=google_iam_workload_identity_pool.github" \
      "-target=google_iam_workload_identity_pool_provider.github" \
      "-target=google_service_account_iam_member.github_workload_identity_user"
  }

  sync_env_from_terraform_outputs() {
    local cloud_run_service

    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"
    cloud_run_service="${FOEHNCAST_TF_CLOUD_RUN_SERVICE}"

    if [[ -z "$cloud_run_service" ]]; then
      cloud_run_service="$(read_tfvars_value cloud_run_service_name)"
    fi

    apply_foehncast_cloud_env_values \
      "$FOEHNCAST_TF_PROJECT_ID" \
      "$FOEHNCAST_TF_LOCATION" \
      "$FOEHNCAST_TF_ARTIFACT_BUCKET_NAME" \
      "$FOEHNCAST_TF_BIGQUERY_DATASET" \
      "$FOEHNCAST_TF_BIGQUERY_LOCATION" \
      "$FOEHNCAST_TF_BIGQUERY_TABLE" \
      "$FOEHNCAST_TF_FEAST_ONLINE_STORE_DATABASE" \
      "$cloud_run_service"
  }

  print_auth_summary() {
    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"

    echo "Local auth: browser-based gcloud ADC on this machine"
    echo "Cloud Run runtime service account: ${FOEHNCAST_TF_RUNTIME_SERVICE_ACCOUNT}"
    if [[ "$FOEHNCAST_TF_PROVISION_ONLINE_COMPOSE_HOST" == "true" && -n "$FOEHNCAST_TF_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT" ]]; then
      echo "Online compose runtime service account: ${FOEHNCAST_TF_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT}"
    fi
    echo "GitHub deployer service account: ${FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL}"

    if [[ -n "$FOEHNCAST_TF_CLOUD_RUN_SERVICE" ]]; then
      echo "Cloud Run service: ${FOEHNCAST_TF_CLOUD_RUN_SERVICE}"
    fi
  }

  print_cloud_run_summary() {
    local service_url

    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"

    if [[ "$FOEHNCAST_TF_PROVISION_CLOUD_RUN_SERVICE" != "true" ]]; then
      return
    fi

    service_url="$(optional_terraform_output_value "$TERRAFORM_DIR" cloud_run_service_url)"
    service_url="$(trim_whitespace "$service_url")"

    if [[ -n "$service_url" && "$service_url" != "null" ]]; then
      echo "Cloud Run service URL: ${service_url}"
    fi

    echo "Cloud Run allows unauthenticated access: ${FOEHNCAST_TF_CLOUD_RUN_ALLOW_UNAUTHENTICATED}"
  }

  print_feast_runtime_summary() {
    local feast_bigquery_table

    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"
    feast_bigquery_table="${FOEHNCAST_TF_PROJECT_ID}.${FOEHNCAST_TF_BIGQUERY_DATASET}.${FOEHNCAST_TF_BIGQUERY_TABLE}"

    echo "Hosted Feast runtime source: bigquery"
    echo "Hosted Feast offline source table: ${feast_bigquery_table}"
    echo "Hosted Feast online store database: ${FOEHNCAST_TF_FEAST_ONLINE_STORE_DATABASE}"
    echo "After curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."
  }

  print_online_compose_summary() {
    local host_ip app_url airflow_url mlflow_url

    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"

    if [[ "$FOEHNCAST_TF_PROVISION_ONLINE_COMPOSE_HOST" != "true" ]]; then
      return
    fi

    host_ip="$(optional_terraform_output_value "$TERRAFORM_DIR" online_compose_host_ip)"
    host_ip="$(trim_whitespace "$host_ip")"
    app_url="$(optional_terraform_output_value "$TERRAFORM_DIR" online_compose_app_url)"
    app_url="$(trim_whitespace "$app_url")"
    airflow_url="$(optional_terraform_output_value "$TERRAFORM_DIR" online_compose_airflow_url)"
    airflow_url="$(trim_whitespace "$airflow_url")"
    mlflow_url="$(optional_terraform_output_value "$TERRAFORM_DIR" online_compose_mlflow_url)"
    mlflow_url="$(trim_whitespace "$mlflow_url")"

    if [[ -n "$host_ip" && "$host_ip" != "null" ]]; then
      echo "Online compose host IP: ${host_ip}"
    fi
    if [[ -n "$app_url" && "$app_url" != "null" ]]; then
      echo "Online compose app URL: ${app_url}"
    fi
    if [[ -n "$airflow_url" && "$airflow_url" != "null" ]]; then
      echo "Online compose Airflow URL: ${airflow_url}"
    fi
    if [[ -n "$mlflow_url" && "$mlflow_url" != "null" ]]; then
      echo "Online compose MLflow URL: ${mlflow_url}"
    fi
  }

  verify_online_compose_runtime() {
    local app_url health_url health_payload spots_url spots_payload metrics_url metrics_payload

    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"

    if [[ "$FOEHNCAST_TF_PROVISION_ONLINE_COMPOSE_HOST" != "true" ]]; then
      return
    fi

    app_url="$(optional_terraform_output_value "$TERRAFORM_DIR" online_compose_app_url)"
    app_url="$(trim_whitespace "$app_url")"

    if [[ -z "$app_url" || "$app_url" == "null" ]]; then
      echo "Hosted online compose app URL is not publicly exposed; skipping hosted runtime verification."
      return
    fi

    health_url="${app_url%/}/health"
    spots_url="${app_url%/}/spots"
    metrics_url="${app_url%/}/metrics"

    echo "Waiting for hosted app health at ${health_url}..."
    health_payload="$(curl --retry 90 --retry-all-errors --retry-delay 10 -fsS "$health_url")"
    require_payload_pattern \
      "$health_payload" \
      '"status"[[:space:]]*:[[:space:]]*"healthy"' \
      'hosted health payload status'
    require_payload_pattern \
      "$health_payload" \
      '"model_alias"[[:space:]]*:' \
      'hosted health payload model alias'
    require_payload_pattern \
      "$health_payload" \
      '"model_version"[[:space:]]*:' \
      'hosted health payload model version'

    echo "Checking hosted spots endpoint at ${spots_url}..."
    spots_payload="$(curl --retry 30 --retry-all-errors --retry-delay 10 -fsS "$spots_url")"
    require_payload_pattern \
      "$spots_payload" \
      '"id"[[:space:]]*:' \
      'hosted spots payload'

    echo "Checking hosted sync metrics at ${metrics_url}..."
    metrics_payload="$(curl --retry 30 --retry-all-errors --retry-delay 10 -fsS "$metrics_url")"
    require_payload_pattern \
      "$metrics_payload" \
      'foehncast_online_compose_sync_status_file_present' \
      'hosted metrics payload'
    require_payload_pattern \
      "$metrics_payload" \
      'foehncast_online_compose_sync_status_file_present[[:space:]]+1(\.0)?' \
      'hosted sync status-file-present metric'
    require_payload_pattern \
      "$metrics_payload" \
      'foehncast_online_compose_sync_last_success_timestamp_seconds\{' \
      'hosted sync last-success timestamp metric'
  }

  verify_cloud_run_runtime() {
    local service_url health_url health_payload spots_url spots_payload metrics_url metrics_payload identity_token
    local -a curl_args

    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"

    if [[ "$FOEHNCAST_TF_PROVISION_CLOUD_RUN_SERVICE" != "true" ]]; then
      return
    fi

    service_url="$(optional_terraform_output_value "$TERRAFORM_DIR" cloud_run_service_url)"
    service_url="$(trim_whitespace "$service_url")"

    if [[ -z "$service_url" || "$service_url" == "null" ]]; then
      echo "Cloud Run service URL is not available; skipping Cloud Run runtime verification."
      return
    fi

    health_url="${service_url%/}/health"
    spots_url="${service_url%/}/spots"
  metrics_url="${service_url%/}/metrics"
    curl_args=(--retry 90 --retry-all-errors --retry-delay 10 -fsS)

    if [[ "$FOEHNCAST_TF_CLOUD_RUN_ALLOW_UNAUTHENTICATED" != "true" ]]; then
      echo "Cloud Run service requires authenticated invocation; requesting identity token..."
      identity_token="$(gcloud auth print-identity-token --audiences="$service_url")"
      curl_args+=(-H "Authorization: Bearer ${identity_token}")
    fi

    echo "Waiting for Cloud Run health at ${health_url}..."
    health_payload="$(curl "${curl_args[@]}" "$health_url")"
    require_payload_pattern \
      "$health_payload" \
      '"status"[[:space:]]*:[[:space:]]*"healthy"' \
      'Cloud Run health payload status'
    require_payload_pattern \
      "$health_payload" \
      '"model_alias"[[:space:]]*:' \
      'Cloud Run health payload model alias'
    require_payload_pattern \
      "$health_payload" \
      '"model_version"[[:space:]]*:' \
      'Cloud Run health payload model version'

    echo "Checking Cloud Run spots endpoint at ${spots_url}..."
    spots_payload="$(curl "${curl_args[@]}" "$spots_url")"
    require_payload_pattern \
      "$spots_payload" \
      '"id"[[:space:]]*:' \
      'Cloud Run spots payload'

    echo "Checking Cloud Run metrics at ${metrics_url}..."
    metrics_payload="$(curl "${curl_args[@]}" "$metrics_url")"
    require_payload_pattern \
      "$metrics_payload" \
      'foehncast_online_compose_sync_status_file_present' \
      'Cloud Run metrics payload'
  }

  print_bootstrap_only_summary() {
    local state_bucket state_prefix

    FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" load_terraform_platform_state "$TERRAFORM_DIR"
    state_bucket="$(terraform_remote_state_bucket)"
    state_prefix="$(terraform_remote_state_prefix)"

    echo "Bootstrap-only remote state bucket: gs://${state_bucket}"
    echo "Bootstrap-only remote state prefix: ${state_prefix}"
    if [[ "$FOEHNCAST_TF_PROVISION_ONLINE_COMPOSE_HOST" == "true" && -n "$FOEHNCAST_TF_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT" ]]; then
      echo "Online compose runtime service account: ${FOEHNCAST_TF_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT}"
    fi
    echo "GitHub deployer service account: ${FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL}"
    echo "GitHub workload identity provider: ${FOEHNCAST_TF_WORKLOAD_IDENTITY_PROVIDER}"
    echo "Next step: run ./scripts/terraform-remote.sh apply to provision the broader platform through the remote backend."
  }

  prompt_with_default() {
    local prompt_text="$1"
    local default_value="$2"
    local response

    if [[ "$INTERACTIVE" != "true" ]]; then
      printf '%s\n' "$default_value"
      return
    fi

    if [[ -n "$default_value" ]]; then
      read -r -p "${prompt_text} [${default_value}]: " response
      printf '%s\n' "${response:-$default_value}"
      return
    fi

    while true; do
      read -r -p "${prompt_text}: " response
      if [[ -n "$response" ]]; then
        printf '%s\n' "$response"
        return
      fi
    done
  }

  prompt_yes_no() {
    local prompt_text="$1"
    local default_answer="$2"
    local response

    if [[ "$INTERACTIVE" != "true" ]]; then
      [[ "$default_answer" == "y" ]]
      return
    fi

    while true; do
      if [[ "$default_answer" == "y" ]]; then
        read -r -p "${prompt_text} [Y/n]: " response
        response="${response:-Y}"
      else
        read -r -p "${prompt_text} [y/N]: " response
        response="${response:-N}"
      fi

      case "$response" in
        Y|y|Yes|yes)
          return 0
          ;;
        N|n|No|no)
          return 1
          ;;
      esac
    done
  }

  ensure_project_exists() {
    local project_id="$1"
    local project_name

    if gcloud projects describe "$project_id" >/dev/null 2>&1; then
      return
    fi

    if [[ "$INTERACTIVE" != "true" ]]; then
      echo "GCP project ${project_id} is not accessible and non-interactive mode cannot create it." >&2
      exit 1
    fi

    if ! prompt_yes_no "Project ${project_id} is not accessible. Create it now?" y; then
      echo "Use an existing GCP project with billing enabled or rerun and create one interactively." >&2
      exit 1
    fi

    project_name="$(prompt_with_default "GCP project display name" "$project_id")"
    gcloud projects create "$project_id" --name "$project_name"
  }

  choose_project() {
    local default_project="$1"
    local choice project_id project_name
    local projects=()
    local index=1

    if [[ "$INTERACTIVE" != "true" ]]; then
      printf '%s\n' "$default_project"
      return
    fi

    while IFS= read -r project_id; do
      if [[ -n "$project_id" ]]; then
        projects+=("$project_id")
      fi
    done < <(gcloud projects list --format='value(projectId)')

    echo "Choose a GCP project for FoehnCast:" >&2
    for project_id in "${projects[@]}"; do
      echo "  ${index}) ${project_id}" >&2
      index=$((index + 1))
    done
    echo "  n) Create a new project" >&2

    while true; do
      choice="$(prompt_with_default "Project number, project id, or n" "$default_project")"

      if [[ "$choice" == "n" || "$choice" == "new" ]]; then
        project_id="$(prompt_with_default "New GCP project id" "$default_project")"
        project_name="$(prompt_with_default "GCP project display name" "$project_id")"
        gcloud projects create "$project_id" --name "$project_name"
        printf '%s\n' "$project_id"
        return
      fi

      if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#projects[@]} )); then
        printf '%s\n' "${projects[$((choice - 1))]}"
        return
      fi

      if [[ -n "$choice" ]]; then
        printf '%s\n' "$choice"
        return
      fi
    done
  }

  ensure_billing_linked() {
    local project_id="$1"
    local billing_enabled choice selected_id entry
    local billing_accounts=()
    local billing_labels=()
    local index=1

    billing_enabled="$(gcloud billing projects describe "$project_id" --format='value(billingEnabled)' 2>/dev/null || true)"

    if [[ "$billing_enabled" == "True" || "$billing_enabled" == "true" ]]; then
      return
    fi

    if [[ "$INTERACTIVE" != "true" ]]; then
      echo "Project ${project_id} does not have billing linked. Link billing before rerunning in non-interactive mode." >&2
      exit 1
    fi

    while IFS=$'\t' read -r entry label; do
      if [[ -n "$entry" ]]; then
        billing_accounts+=("${entry##*/}")
        billing_labels+=("$label")
      fi
    done < <(gcloud billing accounts list --filter='OPEN=true' --format='value(name,displayName)')

    if [[ ${#billing_accounts[@]} -eq 0 ]]; then
      echo "No open billing accounts are visible to the current gcloud user. Link billing manually and rerun." >&2
      exit 1
    fi

    echo "Project ${project_id} does not have billing linked."
    if ! prompt_yes_no "Link a billing account now?" y; then
      echo "Billing must be enabled before Terraform can provision cloud resources." >&2
      exit 1
    fi

    echo "Available billing accounts:"
    while (( index <= ${#billing_accounts[@]} )); do
      echo "  ${index}) ${billing_labels[$((index - 1))]} (${billing_accounts[$((index - 1))]})"
      index=$((index + 1))
    done

    while true; do
      choice="$(prompt_with_default "Billing account number or id" "1")"

      if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#billing_accounts[@]} )); then
        selected_id="${billing_accounts[$((choice - 1))]}"
        break
      fi

      if [[ -n "$choice" ]]; then
        selected_id="$choice"
        break
      fi
    done

    gcloud billing projects link "$project_id" --billing-account "$selected_id"
  }

  configure_local_files() {
    local current_project current_region artifact_bucket artifact_repo dataset_id table_id bigquery_location
    local feast_online_store_location feast_online_store_database_name
    local provision_cloud_run cloud_run_default cloud_run_service mlflow_tracking_uri
    local provision_online_compose_host provision_online_compose_host_default
    local online_compose_host_name online_compose_host_zone online_compose_machine_type online_compose_disk_size_gb
    local repo_default target_repo_owner target_repo_name

    prepare_file_from_template "${ROOT_DIR}/.env.example" "$ENV_FILE"
    prepare_file_from_template "${ROOT_DIR}/terraform/terraform.tfvars.example" "$TFVARS_FILE"
    load_env_file "$ENV_FILE"

    current_project="${GCP_PROJECT_ID:-$(read_tfvars_value project_id)}"
    current_region="${GCP_LOCATION:-$(read_tfvars_value region)}"

    if [[ -z "$current_region" ]]; then
      current_region="europe-west6"
    fi

    current_project="$(choose_project "$current_project")"
    ensure_project_exists "$current_project"
    ensure_billing_linked "$current_project"

    current_region="$(prompt_with_default "GCP region" "$current_region")"
    artifact_bucket="${GCP_BUCKET_NAME:-$(read_tfvars_value artifact_bucket_name)}"
    if [[ -z "$artifact_bucket" || "$artifact_bucket" == "foehncast-data" || "$artifact_bucket" == "foehncast-artifacts-your-gcp-project" ]]; then
      artifact_bucket="foehncast-artifacts-${current_project}"
    fi
    artifact_bucket="$(prompt_with_default "Artifact bucket name" "$artifact_bucket")"

    artifact_repo="$(read_tfvars_value artifact_registry_repository_id)"
    if [[ -z "$artifact_repo" ]]; then
      artifact_repo="foehncast-docker"
    fi
    artifact_repo="$(prompt_with_default "Artifact Registry repository id" "$artifact_repo")"

    dataset_id="$(read_tfvars_value bigquery_dataset_id)"
    if [[ -z "$dataset_id" ]]; then
      dataset_id="foehncast"
    fi
    dataset_id="$(prompt_with_default "BigQuery dataset id" "$dataset_id")"

    table_id="$(read_tfvars_value bigquery_feature_table_id)"
    if [[ -z "$table_id" ]]; then
      table_id="forecast_features"
    fi
    table_id="$(prompt_with_default "BigQuery feature table id" "$table_id")"

    bigquery_location="$(read_tfvars_value bigquery_location)"
    if [[ -z "$bigquery_location" ]]; then
      bigquery_location="$current_region"
    fi
    bigquery_location="$(prompt_with_default "BigQuery location" "$bigquery_location")"

    feast_online_store_location="$(read_tfvars_value feast_online_store_location)"
    if [[ -z "$feast_online_store_location" ]]; then
      feast_online_store_location="$current_region"
    fi

    feast_online_store_database_name="$(read_tfvars_value feast_online_store_database_name)"
    if [[ -z "$feast_online_store_database_name" ]]; then
      feast_online_store_database_name="feast-online"
    fi

    provision_cloud_run="$(read_tfvars_value provision_cloud_run_service)"
    if [[ "$provision_cloud_run" != "true" ]]; then
      provision_cloud_run=false
      cloud_run_default=n
    else
      cloud_run_default=y
    fi

    if prompt_yes_no "Provision Cloud Run service now? This needs a reachable MLflow endpoint." "$cloud_run_default"; then
      provision_cloud_run=true
    else
      provision_cloud_run=false
    fi

    cloud_run_service="$(read_tfvars_value cloud_run_service_name)"
    if [[ -z "$cloud_run_service" ]]; then
      cloud_run_service="foehncast-serve"
    fi
    cloud_run_service="$(prompt_with_default "Cloud Run service name" "$cloud_run_service")"

    mlflow_tracking_uri="$(read_tfvars_value mlflow_tracking_uri)"
    if [[ "$mlflow_tracking_uri" == "https://mlflow.example.com" ]]; then
      mlflow_tracking_uri=""
    fi

    if [[ "$provision_cloud_run" == "true" ]]; then
      mlflow_tracking_uri="$(prompt_with_default "MLflow tracking URI for Cloud Run" "$mlflow_tracking_uri")"
      if [[ -z "$mlflow_tracking_uri" ]]; then
        echo "A non-empty MLflow tracking URI is required when provisioning Cloud Run." >&2
        exit 1
      fi
    else
      mlflow_tracking_uri=""
    fi

    provision_online_compose_host="$(read_tfvars_value provision_online_compose_host)"
    if [[ "$provision_online_compose_host" != "true" ]]; then
      provision_online_compose_host=false
      provision_online_compose_host_default=n
    else
      provision_online_compose_host_default=y
    fi

    if prompt_yes_no "Provision the full online compose host now? This creates the hosted Airflow, MLflow, and app stack on one VM." "$provision_online_compose_host_default"; then
      provision_online_compose_host=true
    else
      provision_online_compose_host=false
    fi

    online_compose_host_name="$(read_tfvars_value online_compose_host_name)"
    if [[ -z "$online_compose_host_name" ]]; then
      online_compose_host_name="foehncast-online"
    fi

    online_compose_host_zone="$(read_tfvars_value online_compose_host_zone)"
    if [[ -z "$online_compose_host_zone" ]]; then
      online_compose_host_zone="$(foehncast_default_online_compose_host_zone "$current_region")"
    fi

    online_compose_machine_type="$(read_tfvars_value online_compose_machine_type)"
    if [[ -z "$online_compose_machine_type" ]]; then
      online_compose_machine_type="e2-standard-4"
    fi

    online_compose_disk_size_gb="$(read_tfvars_value online_compose_disk_size_gb)"
    if [[ -z "$online_compose_disk_size_gb" ]]; then
      online_compose_disk_size_gb="40"
    fi

    if [[ "$provision_online_compose_host" == "true" ]]; then
      online_compose_host_name="$(prompt_with_default "Online compose host name" "$online_compose_host_name")"
      online_compose_host_zone="$(prompt_with_default "Online compose host zone" "$online_compose_host_zone")"
      online_compose_machine_type="$(prompt_with_default "Online compose machine type" "$online_compose_machine_type")"
      online_compose_disk_size_gb="$(prompt_with_default "Online compose disk size in GB" "$online_compose_disk_size_gb")"
    fi

    if [[ "$CONFIGURE_GITHUB" != "true" && "$INTERACTIVE" == "true" ]]; then
      local github_default_answer="n"

      if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
        github_default_answer="y"
      fi

      if prompt_yes_no "Configure GitHub Actions variables for shared or fork-based redeploys after bootstrap?" "$github_default_answer"; then
        CONFIGURE_GITHUB=true
      fi
    fi

    repo_default="$(resolve_repo_from_remote "$ROOT_DIR")"
    if [[ "$CONFIGURE_GITHUB" == "true" ]]; then
      require_command gh
      TARGET_REPO="$(prompt_with_default "GitHub repository for deployment automation" "${TARGET_REPO:-$repo_default}")"

      if [[ "$TARGET_REPO" != */* ]]; then
        echo "GitHub repository must use owner/repo format." >&2
        exit 1
      fi

      target_repo_owner="${TARGET_REPO%%/*}"
      target_repo_name="${TARGET_REPO##*/}"
      set_tfvars_string github_owner "$target_repo_owner"
      set_tfvars_string github_repository "$target_repo_name"
    fi

    apply_foehncast_cloud_env_values \
      "$current_project" \
      "$current_region" \
      "$artifact_bucket" \
      "$dataset_id" \
      "$bigquery_location" \
      "$table_id" \
      "$feast_online_store_database_name"

    apply_foehncast_cloud_tfvars_values \
      "$current_project" \
      "$current_region" \
      "$artifact_repo" \
      "$artifact_bucket" \
      "$dataset_id" \
      "$bigquery_location" \
      "$table_id" \
      "$feast_online_store_location" \
      "$feast_online_store_database_name" \
      "$provision_cloud_run" \
      "$cloud_run_service" \
      "$mlflow_tracking_uri" \
      "$provision_online_compose_host" \
      "$online_compose_host_name" \
      "$online_compose_host_zone" \
      "$online_compose_machine_type" \
      "$online_compose_disk_size_gb"
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
    --bootstrap-only)
      BOOTSTRAP_ONLY=true
      ;;
    --non-interactive)
      INTERACTIVE=false
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

if [[ -n "$TARGET_REPO" ]]; then
  CONFIGURE_GITHUB=true
fi

print_bootstrap_context

require_command gcloud
ensure_terraform_command
require_command curl

if [[ "$CONFIGURE_GITHUB" == "true" ]]; then
  require_command gh
fi

if [[ "$INTERACTIVE" == "true" ]]; then
  ensure_gcloud_auth
  configure_local_files
else
  require_file "$ENV_FILE" "Env file not found: $ENV_FILE. Re-run without --non-interactive to generate it interactively."
  require_file "$TFVARS_FILE" "Terraform variables file not found: $TFVARS_FILE. Re-run without --non-interactive to generate it interactively."
fi

load_env_file "$ENV_FILE"

require_gcp_project_and_location
prepare_bootstrap_terraform_dir

echo "Authenticating with Google Cloud via browser if needed..."
"${ROOT_DIR}/scripts/gcp-auth.sh" "$ENV_FILE"

echo "Checking access to GCP project ${GCP_PROJECT_ID}..."
gcloud projects describe "$GCP_PROJECT_ID" >/dev/null

echo "Initializing Terraform..."
terraform_init_args=(init -reconfigure)

if [[ "$BOOTSTRAP_ONLY" == "true" && "$PLAN_ONLY" != "true" ]]; then
  ensure_remote_state_bucket
  terraform_init_args+=(
    -backend-config="bucket=$(terraform_remote_state_bucket)"
    -backend-config="prefix=$(terraform_remote_state_prefix)"
  )
fi

run_terraform -chdir="$TERRAFORM_DIR" "${terraform_init_args[@]}"

echo "Formatting generated Terraform variable files..."
format_generated_tfvars_file "$TFVARS_FILE"

echo "Checking Terraform formatting and validation..."
run_terraform -chdir="$TERRAFORM_DIR" fmt -check
run_terraform -chdir="$TERRAFORM_DIR" validate

target_args=()
if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
  while IFS= read -r target_arg; do
    target_args+=("$target_arg")
  done < <(bootstrap_target_args)
fi

if [[ "$PLAN_ONLY" == "true" ]]; then
  if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
    echo "Running bootstrap-only Terraform plan..."
  else
    echo "Running Terraform plan..."
  fi

  run_terraform -chdir="$TERRAFORM_DIR" plan -var-file="$TFVARS_FILE" "${target_args[@]}"
else
  apply_args=(apply -var-file="$TFVARS_FILE")

  apply_args+=("${target_args[@]}")

  if [[ "$AUTO_APPROVE" == "true" ]]; then
    apply_args+=( -auto-approve )
  fi

  if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
    echo "Running bootstrap-only Terraform apply against the remote backend..."
  else
    echo "Running Terraform apply..."
  fi

  run_terraform -chdir="$TERRAFORM_DIR" "${apply_args[@]}"

  if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
    print_bootstrap_only_summary
  else
    echo "Syncing local cloud identifiers into .env..."
    sync_env_from_terraform_outputs
    print_auth_summary
    print_cloud_run_summary
    print_online_compose_summary
    print_feast_runtime_summary
    verify_cloud_run_runtime
    verify_online_compose_runtime
  fi
fi

if [[ "$CONFIGURE_GITHUB" == "true" && "$PLAN_ONLY" != "true" ]]; then
  github_args=()

  if [[ -n "$TARGET_REPO" ]]; then
    github_args+=( --repo "$TARGET_REPO" )
  fi

  github_args+=( --terraform-dir "$TERRAFORM_DIR" )

  echo "Configuring GitHub Actions repository variables..."
  FOEHNCAST_TERRAFORM_TFVARS_FILE="$TFVARS_FILE" "${ROOT_DIR}/scripts/configure-github-actions.sh" "${github_args[@]}"
fi

if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
  echo "Bootstrap-only setup complete for ${GCP_PROJECT_ID}."
  echo "The initial bootstrap resources now live in the same remote backend used by the GitHub Actions Terraform workflow."
else
  echo "Bootstrap complete for ${GCP_PROJECT_ID}."
  echo "The interactive path can create or reuse a project and link billing when your gcloud account has permission to do so."
fi

echo "For local evaluation, keep using ./scripts/bootstrap-local.sh."

if [[ "$CONFIGURE_GITHUB" == "true" && "$PLAN_ONLY" != "true" ]]; then
  echo "GitHub Actions variables were synchronized for repo-driven deployment automation."
  if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
    echo "Run ./scripts/terraform-remote.sh apply to provision the broader platform through the remote backend."
  else
    echo "Prefer the remote GitHub Actions Terraform workflow for day-2 plan, apply, destroy, and cleanup."
    echo "Common remote command: ./scripts/terraform-remote.sh plan"
  fi
else
  echo "GitHub Actions were not changed. That is fine for personal one-off environments."
  if [[ "$BOOTSTRAP_ONLY" == "true" ]]; then
    echo "Sync GitHub Actions variables before handing off to ./scripts/terraform-remote.sh apply."
  else
    echo "When you later configure GitHub OIDC variables, prefer the remote GitHub Actions Terraform workflow for day-2 plan, apply, destroy, and cleanup."
    echo "After syncing GitHub Actions variables, use ./scripts/terraform-remote.sh for common remote Terraform commands."
  fi
fi
