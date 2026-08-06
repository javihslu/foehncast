#!/usr/bin/env bash

payload_check_require_pattern() {
  local failure_prefix="$1"
  local payload="$2"
  local pattern="$3"
  local description="$4"

  # A here-string rather than a pipe: grep -q exits on the first match, which
  # SIGPIPEs the writer of a payload larger than the pipe buffer, and pipefail
  # would then report a successful match as a failure.
  if ! grep -Eq "$pattern" <<<"$payload"; then
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