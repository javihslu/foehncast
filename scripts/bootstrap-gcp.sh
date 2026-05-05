#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
INTERACTIVE=true

usage() {
  echo "Usage: $0 [--env-file path] [--tfvars-file path] [--plan-only] [--auto-approve] [--configure-github-actions] [--repo owner/repo] [--non-interactive]" >&2
}

require_file() {
  local file_path="$1"
  local help_message="$2"

  if [[ ! -f "$file_path" ]]; then
    echo "$help_message" >&2
    exit 1
  fi
}

copy_example_if_missing() {
  local template_path="$1"
  local destination_path="$2"

  if [[ ! -f "$destination_path" ]]; then
    cp "$template_path" "$destination_path"
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

  replace_or_append_line() {
    local file_path="$1"
    local regex="$2"
    local replacement="$3"
    local temp_file line matched=false

    temp_file="$(mktemp)"

    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" =~ $regex ]]; then
        printf '%s\n' "$replacement" >> "$temp_file"
        matched=true
      else
        printf '%s\n' "$line" >> "$temp_file"
      fi
    done < "$file_path"

    if [[ "$matched" != "true" ]]; then
      printf '%s\n' "$replacement" >> "$temp_file"
    fi

    mv "$temp_file" "$file_path"
  }

  set_env_value() {
    local key="$1"
    local value="$2"

    replace_or_append_line "$ENV_FILE" "^${key}=" "${key}=${value}"
  }

  escape_tfvars_string() {
    local value="$1"

    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s' "$value"
  }

  set_tfvars_string() {
    local key="$1"
    local value="$2"

    value="$(escape_tfvars_string "$value")"
    replace_or_append_line "$TFVARS_FILE" "^[[:space:]]*${key}[[:space:]]*=" "${key} = \"${value}\""
  }

  set_tfvars_bool() {
    local key="$1"
    local value="$2"

    replace_or_append_line "$TFVARS_FILE" "^[[:space:]]*${key}[[:space:]]*=" "${key} = ${value}"
  }

  sync_env_from_terraform_outputs() {
    local cloud_run_service

    load_terraform_platform_state "${ROOT_DIR}/terraform"
    cloud_run_service="${FOEHNCAST_TF_CLOUD_RUN_SERVICE}"

    if [[ -z "$cloud_run_service" ]]; then
      cloud_run_service="$(read_tfvars_value cloud_run_service_name)"
    fi

    set_env_value GCP_PROJECT_ID "$FOEHNCAST_TF_PROJECT_ID"
    set_env_value GCP_LOCATION "$FOEHNCAST_TF_LOCATION"
    set_env_value GCP_BUCKET_NAME "$FOEHNCAST_TF_ARTIFACT_BUCKET_NAME"
    set_env_value STORAGE_BIGQUERY_PROJECT_ID "$FOEHNCAST_TF_PROJECT_ID"
    set_env_value STORAGE_BIGQUERY_DATASET "$FOEHNCAST_TF_BIGQUERY_DATASET"
    set_env_value STORAGE_BIGQUERY_TABLE "$FOEHNCAST_TF_BIGQUERY_TABLE"

    if [[ -n "$cloud_run_service" ]]; then
      set_env_value CLOUD_RUN_SERVICE_NAME "$cloud_run_service"
    fi
  }

  print_auth_summary() {
    load_terraform_platform_state "${ROOT_DIR}/terraform"

    echo "Local auth: browser-based gcloud ADC on this machine"
    echo "Cloud Run runtime service account: ${FOEHNCAST_TF_RUNTIME_SERVICE_ACCOUNT}"
    echo "GitHub deployer service account: ${FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL}"

    if [[ -n "$FOEHNCAST_TF_CLOUD_RUN_SERVICE" ]]; then
      echo "Cloud Run service: ${FOEHNCAST_TF_CLOUD_RUN_SERVICE}"
    fi
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
    local provision_cloud_run cloud_run_service mlflow_tracking_uri repo_default target_repo_owner target_repo_name

    copy_example_if_missing "${ROOT_DIR}/.env.example" "$ENV_FILE"
    copy_example_if_missing "${ROOT_DIR}/terraform/terraform.tfvars.example" "$TFVARS_FILE"
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

    provision_cloud_run=false
    if prompt_yes_no "Provision Cloud Run service now? This needs a reachable MLflow endpoint." n; then
      provision_cloud_run=true
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

    if [[ "$CONFIGURE_GITHUB" != "true" && "$INTERACTIVE" == "true" ]]; then
      if prompt_yes_no "Configure GitHub Actions variables for shared or fork-based redeploys after bootstrap?" n; then
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

    set_env_value GCP_PROJECT_ID "$current_project"
    set_env_value GCP_LOCATION "$current_region"
    set_env_value GCP_BUCKET_NAME "$artifact_bucket"
    set_env_value STORAGE_BIGQUERY_PROJECT_ID "$current_project"
    set_env_value STORAGE_BIGQUERY_DATASET "$dataset_id"
    set_env_value STORAGE_BIGQUERY_TABLE "$table_id"

    set_tfvars_string project_id "$current_project"
    set_tfvars_string region "$current_region"
    set_tfvars_string artifact_registry_repository_id "$artifact_repo"
    set_tfvars_string artifact_bucket_name "$artifact_bucket"
    set_tfvars_string bigquery_dataset_id "$dataset_id"
    set_tfvars_string bigquery_location "$bigquery_location"
    set_tfvars_string bigquery_feature_table_id "$table_id"
    set_tfvars_bool provision_cloud_run_service "$provision_cloud_run"
    set_tfvars_string cloud_run_service_name "$cloud_run_service"
    set_tfvars_string cloud_run_image "${current_region}-docker.pkg.dev/${current_project}/${artifact_repo}/foehncast-app:latest"
    set_tfvars_string mlflow_tracking_uri "$mlflow_tracking_uri"
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

require_command gcloud
require_command terraform

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

echo "Authenticating with Google Cloud via browser if needed..."
"${ROOT_DIR}/scripts/gcp-auth.sh" "$ENV_FILE"

echo "Checking access to GCP project ${GCP_PROJECT_ID}..."
gcloud projects describe "$GCP_PROJECT_ID" >/dev/null

echo "Initializing Terraform..."
terraform -chdir="${ROOT_DIR}/terraform" init

echo "Formatting generated Terraform variable files..."
terraform fmt "$TFVARS_FILE" >/dev/null

echo "Checking Terraform formatting and validation..."
terraform -chdir="${ROOT_DIR}/terraform" fmt -check
terraform -chdir="${ROOT_DIR}/terraform" validate

if [[ "$PLAN_ONLY" == "true" ]]; then
  echo "Running Terraform plan..."
  terraform -chdir="${ROOT_DIR}/terraform" plan -var-file="$TFVARS_FILE"
else
  apply_args=(apply -var-file="$TFVARS_FILE")

  if [[ "$AUTO_APPROVE" == "true" ]]; then
    apply_args+=( -auto-approve )
  fi

  echo "Running Terraform apply..."
  terraform -chdir="${ROOT_DIR}/terraform" "${apply_args[@]}"

  echo "Syncing local cloud identifiers into .env..."
  sync_env_from_terraform_outputs
  print_auth_summary
fi

if [[ "$CONFIGURE_GITHUB" == "true" && "$PLAN_ONLY" != "true" ]]; then
  github_args=()

  if [[ -n "$TARGET_REPO" ]]; then
    github_args+=( --repo "$TARGET_REPO" )
  fi

  echo "Configuring GitHub Actions repository variables..."
  "${ROOT_DIR}/scripts/configure-github-actions.sh" "${github_args[@]}"
fi

echo "Bootstrap complete for ${GCP_PROJECT_ID}."
echo "The interactive path can create or reuse a project and link billing when your gcloud account has permission to do so."

if [[ "$CONFIGURE_GITHUB" == "true" && "$PLAN_ONLY" != "true" ]]; then
  echo "GitHub Actions variables were synchronized for repo-driven deployment automation."
else
  echo "GitHub Actions were not changed. That is fine for personal one-off environments."
fi
