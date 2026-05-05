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
