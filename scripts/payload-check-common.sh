#!/usr/bin/env bash

payload_check_require_pattern() {
  local failure_prefix="$1"
  local payload="$2"
  local pattern="$3"
  local description="$4"

  if ! printf '%s' "$payload" | grep -Eq "$pattern"; then
    echo "${failure_prefix}: expected ${description}." >&2
    printf '%s\n' "$payload" >&2
    return 1
  fi
}

payload_check_require_patterns() {
  local failure_prefix="$1"
  local payload="$2"
  shift 2

  while [[ $# -gt 1 ]]; do
    payload_check_require_pattern "$failure_prefix" "$payload" "$1" "$2" || return 1
    shift 2
  done
}