#!/usr/bin/env bash

install_hint() {
  local command_name="$1"

  case "$command_name" in
    curl)
      echo "Install curl first. On macOS it is usually available by default." >&2
      ;;
    docker)
      echo "Install Docker first. On macOS: brew install --cask docker" >&2
      ;;
    gcloud)
      echo "Install Google Cloud CLI first. On macOS with Homebrew: brew install --cask google-cloud-sdk" >&2
      echo "Alternative: run the cloud bootstrap from Google Cloud Shell instead of installing it locally." >&2
      ;;
    gh)
      echo "Install GitHub CLI first. On macOS with Homebrew: brew install gh" >&2
      ;;
    terraform)
      echo "Install Terraform first if you want a local admin shell. On macOS with Homebrew: brew tap hashicorp/tap && brew install hashicorp/tap/terraform" >&2
      echo "Supported no-local-install path: run the cloud bootstrap from Google Cloud Shell, then use the remote GitHub Actions Terraform workflow for day-2 operations." >&2
      ;;
    uv)
      echo "Install uv first. On macOS with Homebrew: brew install uv" >&2
      ;;
  esac
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required but not installed." >&2
    install_hint "$command_name"
    exit 1
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

require_cli_option_value() {
  local option_name="$1"
  local option_value="$2"
  local usage_callback="$3"

  if [[ -n "$option_value" && "$option_value" != -* ]]; then
    printf '%s\n' "$option_value"
    return
  fi

  echo "Missing value for ${option_name}" >&2
  "$usage_callback"
  exit 1
}

export_feast_runtime_config_path() {
  local config_path="$1"

  export FOEHNCAST_FEAST_CONFIG_PATH="$config_path"
  export FEAST_FS_YAML_FILE_PATH="$config_path"
}

render_feast_runtime_config_path() {
  local root_dir="$1"

  (
    cd "$root_dir" || exit 1
    uv run python -m foehncast.feast_runtime
  )
}

run_feast_repo_apply_and_maybe_materialize() {
  local repo_dir="$1"
  local materialize="$2"
  local materialize_ts="$3"

  (
    cd "$repo_dir" || exit 1

    # `feast apply` reads the offline parquet to infer its schema. Under CI the
    # freshly exported file occasionally races filesystem visibility, surfacing
    # as FileNotFoundError / "No such file or directory". Retry only that
    # specific, known-transient case; any other failure is a real
    # configuration error and should fail fast instead of repeating the same
    # failure several times.
    apply_attempts=0
    apply_max_attempts=3
    while true; do
      apply_attempts=$((apply_attempts + 1))
      if apply_output="$(uv run --group feast feast apply 2>&1)"; then
        break
      fi

      if (( apply_attempts >= apply_max_attempts )); then
        printf '%s\n' "$apply_output" >&2
        echo "feast apply failed after ${apply_max_attempts} attempts" >&2
        exit 1
      fi

      if ! grep -qE 'FileNotFoundError|No such file or directory' <<< "$apply_output"; then
        printf '%s\n' "$apply_output" >&2
        exit 1
      fi

      echo "feast apply attempt ${apply_attempts} failed with the known transient parquet-visibility race; retrying..." >&2
      sleep 2
    done

    if [[ "$materialize" == "true" ]]; then
      uv run --group feast feast materialize-incremental "$materialize_ts" >/dev/null
    fi
  )
}

print_feast_materialize_status() {
  local root_dir="$1"
  local materialize="$2"
  local materialize_ts="$3"

  if [[ "$materialize" == "true" ]]; then
    printf 'Materialized through: %s\n' "$materialize_ts"
  else
    printf 'Next: cd %s/feature_repo && uv run --group feast feast materialize-incremental "%s"\n' "$root_dir" "$materialize_ts"
  fi
}

require_docker_compose() {
  require_command docker

  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose is required but not available." >&2
    exit 1
  fi
}

require_file_variable() {
  local variable_name="$1"
  local file_path="${!variable_name:-}"

  if [[ -z "$file_path" ]]; then
    echo "${variable_name} must be set before calling this helper." >&2
    exit 1
  fi
}

ensure_terraform_command() {
  require_command terraform
}

run_terraform() {
  ensure_terraform_command
  terraform "$@"
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

prepare_file_from_template() {
  local template_path="$1"
  local destination_path="$2"

  mkdir -p "$(dirname "$destination_path")"
  if [[ ! -f "$destination_path" ]]; then
    cp "$template_path" "$destination_path"
  fi
}

escape_tfvars_string() {
  local value="$1"

  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "$value"
}

set_env_value() {
  local key="$1"
  local value="$2"

  require_file_variable ENV_FILE
  replace_or_append_line "$ENV_FILE" "^${key}=" "${key}=${value}"
}

set_tfvars_string() {
  local key="$1"
  local value="$2"

  require_file_variable TFVARS_FILE
  value="$(escape_tfvars_string "$value")"
  replace_or_append_line "$TFVARS_FILE" "^[[:space:]]*${key}[[:space:]]*=" "${key} = \"${value}\""
}

set_tfvars_bool() {
  local key="$1"
  local value="$2"

  require_file_variable TFVARS_FILE
  replace_or_append_line "$TFVARS_FILE" "^[[:space:]]*${key}[[:space:]]*=" "${key} = ${value}"
}

set_tfvars_number() {
  local key="$1"
  local value="$2"

  require_file_variable TFVARS_FILE
  replace_or_append_line "$TFVARS_FILE" "^[[:space:]]*${key}[[:space:]]*=" "${key} = ${value}"
}
