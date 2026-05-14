#!/usr/bin/env bash

env_file_value() {
  local key="$1"
  local file_path="$2"
  local line value

  if [[ ! -f "$file_path" ]]; then
    return
  fi

  line="$(grep -E "^${key}=" "$file_path" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    return
  fi

  value="${line#*=}"
  value="${value#\"}"
  value="${value%\"}"
  printf '%s\n' "$value"
}

resolved_env_value() {
  local key="$1"
  shift
  local value
  local file_path

  if [[ -n "${!key:-}" ]]; then
    printf '%s\n' "${!key}"
    return
  fi

  for file_path in "$@"; do
    value="$(env_file_value "$key" "$file_path")"
    if [[ -n "$value" ]]; then
      printf '%s\n' "$value"
      return
    fi
  done
}

export_resolved_env_value() {
  local key="$1"
  shift
  local value="${!key:-}"

  if [[ -z "$value" ]]; then
    value="$(resolved_env_value "$key" "$@")"
  fi

  if [[ -n "$value" ]]; then
    export "$key=$value"
  fi
}

ensure_env_default() {
  local key="$1"
  local fallback_value="$2"

  if [[ -z "${!key:-}" ]]; then
    export "$key=$fallback_value"
  fi
}

export_local_feast_datastore_env() {
  export_resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID "$@"
  export_resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE "$@"
  export_resolved_env_value FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE "$@"
  export_resolved_env_value FEAST_DATASTORE_EMULATOR_BIND_HOST "$@"
  export_resolved_env_value FEAST_DATASTORE_EMULATOR_PORT "$@"

  ensure_env_default FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID foehncast-local
  ensure_env_default FEAST_DATASTORE_EMULATOR_BIND_HOST 127.0.0.1
  ensure_env_default FEAST_DATASTORE_EMULATOR_PORT 8181
}