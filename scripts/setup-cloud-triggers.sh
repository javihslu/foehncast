#!/usr/bin/env bash
# Automates Cloud Build trigger provisioning via Developer Connect.
#
# This script handles everything except the one-time OAuth browser click:
#   1. Enables the Developer Connect API
#   2. Runs terraform apply to create the connection resource
#   3. Opens the GCP Console for the user to complete the OAuth handshake
#   4. Waits for the connection to become ACTIVE
#   5. Re-applies terraform to create triggers and repository link
#
# Prerequisites:
#   - gcloud authenticated with project access
#   - terraform.tfvars exists with project_id, region, github_owner, github_repository
#   - GitHub Cloud Build app installed on the repository (the OAuth flow links it)
#
# Usage:
#   ./scripts/setup-cloud-triggers.sh [--auto-approve] [--installation-id ID]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="${ROOT_DIR}/terraform"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/gcp-common.sh"

AUTO_APPROVE=false
INSTALLATION_ID=""
TFVARS_FILE="${TERRAFORM_DIR}/terraform.tfvars"

usage() {
  echo "Usage: $0 [--auto-approve] [--installation-id ID] [--tfvars-file path]" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --auto-approve       Skip terraform apply confirmation prompts" >&2
  echo "  --installation-id    GitHub App installation ID (skips interactive lookup)" >&2
  echo "  --tfvars-file        Path to terraform.tfvars (default: terraform/terraform.tfvars)" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto-approve)
      AUTO_APPROVE=true
      ;;
    --installation-id)
      shift
      INSTALLATION_ID="${1:-}"
      if [[ -z "$INSTALLATION_ID" ]]; then
        echo "Error: --installation-id requires a value" >&2
        exit 1
      fi
      ;;
    --tfvars-file)
      shift
      TFVARS_FILE="${1:-}"
      if [[ -z "$TFVARS_FILE" ]]; then
        echo "Error: --tfvars-file requires a value" >&2
        exit 1
      fi
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

require_command gcloud
require_command terraform

# Read project from tfvars
PROJECT_ID="$(grep 'project_id' "$TFVARS_FILE" | head -1 | sed 's/.*=\s*"\([^"]*\)".*/\1/')"
REGION="$(grep 'region' "$TFVARS_FILE" | head -1 | sed 's/.*=\s*"\([^"]*\)".*/\1/')"

if [[ -z "$PROJECT_ID" || -z "$REGION" ]]; then
  echo "Error: Could not read project_id or region from $TFVARS_FILE" >&2
  exit 1
fi

echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo ""

# Step 1: Enable Developer Connect API
echo "Step 1/5: Enabling Developer Connect API..."
gcloud services enable developerconnect.googleapis.com --project="$PROJECT_ID" --quiet

# Step 2: Get or prompt for GitHub App Installation ID
if [[ -z "$INSTALLATION_ID" ]]; then
  echo ""
  echo "Step 2/5: GitHub App Installation ID required."
  echo ""
  echo "To find your installation ID:"
  echo "  1. Go to https://github.com/settings/installations"
  echo "  2. Click 'Configure' on the 'Google Cloud Build' app"
  echo "  3. The URL will be: https://github.com/settings/installations/<ID>"
  echo "  4. If not installed, install it first: https://github.com/apps/google-cloud-build"
  echo ""
  read -r -p "GitHub App installation ID: " INSTALLATION_ID

  if [[ -z "$INSTALLATION_ID" ]]; then
    echo "Error: Installation ID is required" >&2
    exit 1
  fi
fi

echo "Installation ID: $INSTALLATION_ID"

# Step 3: Update tfvars and run initial terraform apply (creates connection)
echo ""
echo "Step 3/5: Updating terraform.tfvars and applying Developer Connect resources..."

# Add or update the cloud build trigger variables in tfvars
if grep -q "provision_cloud_build_triggers" "$TFVARS_FILE"; then
  sed -i '' "s/provision_cloud_build_triggers.*/provision_cloud_build_triggers = true/" "$TFVARS_FILE"
else
  printf '\n# --- Cloud Build Triggers (Developer Connect) ---\nprovision_cloud_build_triggers = true\n' >> "$TFVARS_FILE"
fi

if grep -q "github_app_installation_id" "$TFVARS_FILE"; then
  sed -i '' "s/github_app_installation_id.*/github_app_installation_id = \"${INSTALLATION_ID}\"/" "$TFVARS_FILE"
else
  printf 'github_app_installation_id = "%s"\n' "$INSTALLATION_ID" >> "$TFVARS_FILE"
fi

# Run targeted apply for just the connection resource
APPLY_ARGS=(-var-file="$TFVARS_FILE" -target=google_developer_connect_connection.github)
if [[ "$AUTO_APPROVE" == "true" ]]; then
  APPLY_ARGS+=(-auto-approve)
fi

terraform -chdir="$TERRAFORM_DIR" apply "${APPLY_ARGS[@]}"

# Step 4: Wait for OAuth handshake
echo ""
echo "Step 4/5: Complete the OAuth handshake in the GCP Console."
echo ""
CONSOLE_URL="https://console.cloud.google.com/developer-connect/connections?project=${PROJECT_ID}"
echo "Opening: $CONSOLE_URL"
echo ""
echo "Instructions:"
echo "  1. Click on the 'foehncast-github' connection"
echo "  2. Click 'Authorize' or 'Complete setup'"
echo "  3. Grant access to the repository: ${PROJECT_ID}"
echo ""

# Try to open the browser
if command -v open >/dev/null 2>&1; then
  open "$CONSOLE_URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$CONSOLE_URL"
fi

echo "Waiting for connection to become ACTIVE..."
echo "(This will poll every 10 seconds. Press Ctrl+C to abort.)"
echo ""

MAX_WAIT=600  # 10 minutes
ELAPSED=0
while (( ELAPSED < MAX_WAIT )); do
  STATUS="$(gcloud developer-connect connections describe foehncast-github \
    --location="$REGION" --project="$PROJECT_ID" \
    --format='value(installationState.stage)' 2>/dev/null || echo "PENDING")"

  if [[ "$STATUS" == "COMPLETE" ]]; then
    echo "Connection is ACTIVE."
    break
  fi

  printf "  Status: %s (waiting...)\r" "$STATUS"
  sleep 10
  ELAPSED=$((ELAPSED + 10))
done

if (( ELAPSED >= MAX_WAIT )); then
  echo ""
  echo "Timed out waiting for connection. Complete the OAuth manually, then rerun:"
  echo "  terraform -chdir=terraform apply -var-file=terraform/terraform.tfvars"
  exit 1
fi

# Step 5: Full apply to create triggers and repository link
echo ""
echo "Step 5/5: Applying full Terraform configuration (triggers + repository link)..."

FULL_APPLY_ARGS=(-var-file="$TFVARS_FILE")
if [[ "$AUTO_APPROVE" == "true" ]]; then
  FULL_APPLY_ARGS+=(-auto-approve)
fi

terraform -chdir="$TERRAFORM_DIR" apply "${FULL_APPLY_ARGS[@]}"

echo ""
echo "Cloud Build triggers provisioned successfully."
echo ""
echo "Triggers created:"
echo "  - publish-app: builds foehncast-app on src/ or Dockerfile changes"
echo "  - publish-mlflow: builds foehncast-mlflow on containers/mlflow/ changes"
echo "  - publish-ui: builds foehncast-ui on ui/ changes"
echo "  - publish-airflow: builds foehncast-airflow on containers/airflow/ changes"
echo ""
echo "Push to main to trigger image builds automatically."
