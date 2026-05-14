#!/usr/bin/env bash

resolve_repo_from_remote() {
  local root_dir="$1"
  local origin_url

  origin_url="$(git -C "$root_dir" config --get remote.origin.url || true)"

  if [[ "$origin_url" =~ ^git@github\.com:([^/]+)/([^.]+)(\.git)?$ ]]; then
    printf '%s/%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return
  fi

  if [[ "$origin_url" =~ ^https://github\.com/([^/]+)/([^.]+)(\.git)?$ ]]; then
    printf '%s/%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
  fi
}

require_repo_from_remote() {
  local root_dir="$1"
  local resolved_repo

  resolved_repo="$(resolve_repo_from_remote "$root_dir")"
  if [[ -n "$resolved_repo" ]]; then
    printf '%s\n' "$resolved_repo"
    return
  fi

  echo "Unable to determine the GitHub repository from remote.origin.url. Use --repo owner/repo." >&2
  exit 1
}

resolve_target_repo() {
  local root_dir="$1"
  local explicit_repo="${2:-}"

  if [[ -n "$explicit_repo" ]]; then
    printf '%s\n' "$explicit_repo"
    return
  fi

  require_repo_from_remote "$root_dir"
}

require_github_auth() {
  require_command gh

  if ! gh auth status >/dev/null 2>&1; then
    echo "gh is installed but not authenticated. Run 'gh auth login' first." >&2
    exit 1
  fi
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
