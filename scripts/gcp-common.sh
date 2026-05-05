#!/usr/bin/env bash

load_env_file() {
  local file_path="$1"

  if [[ -f "$file_path" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file_path"
    set +a

    if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
      unset GOOGLE_APPLICATION_CREDENTIALS
    fi
  fi
}

require_env_var() {
  local variable_name="$1"
  local help_message="$2"
  local value="${!variable_name:-}"

  if [[ -z "$value" ]]; then
    echo "$help_message" >&2
    exit 1
  fi
}

require_gcp_project_and_location() {
  require_env_var GCP_PROJECT_ID "Set GCP_PROJECT_ID in .env or the environment."
  require_env_var GCP_LOCATION "Set GCP_LOCATION in .env or the environment."
}

ensure_gcloud_auth() {
  if ! gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q .; then
    echo "Opening browser-based gcloud login..."
    gcloud auth login
  fi

  if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
    echo "Opening browser-based application default credential login..."
    gcloud auth application-default login
  fi
}
