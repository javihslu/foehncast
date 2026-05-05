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
      ;;
    gh)
      echo "Install GitHub CLI first. On macOS with Homebrew: brew install gh" >&2
      ;;
    terraform)
      echo "Install Terraform first. On macOS with Homebrew: brew tap hashicorp/tap && brew install hashicorp/tap/terraform" >&2
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

require_docker_compose() {
  require_command docker

  if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose is required but not available." >&2
    exit 1
  fi
}
