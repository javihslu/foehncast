#!/usr/bin/env bash
# Automates Cloud Build trigger provisioning via Cloud Build 2nd-gen connections.
#
# Flow for new users (maximum automation, one browser step):
#   1. Enables the Cloud Build and Secret Manager APIs
#   2. Grants the Cloud Build service agent Secret Manager access
#   3. Creates a Cloud Build GitHub connection via gcloud
#   4. Opens the browser for the user to complete GitHub OAuth + app install
#   5. Polls until the connection becomes COMPLETE
#   6. Imports the connection into Terraform state and applies triggers
#
# The ONLY manual step is clicking through the GitHub OAuth in the browser.
# Everything else is fully automated.
#
# Prerequisites:
#   - gcloud authenticated with project access (gcloud auth login)
#   - terraform.tfvars exists with project_id, region, github_owner, github_repository
#
# Usage:
#   ./scripts/setup-cloud-triggers.sh [--auto-approve] [--skip-oauth]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="${ROOT_DIR}/terraform"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/cli-common.sh"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/gcp-common.sh"

AUTO_APPROVE=false
SKIP_OAUTH=false
TFVARS_FILE="${TERRAFORM_DIR}/terraform.tfvars"
CONNECTION_NAME="foehncast-github"

usage() {
  echo "Usage: $0 [--auto-approve] [--skip-oauth] [--tfvars-file path]" >&2
  echo "" >&2
  echo "Provisions Cloud Build triggers with a 2nd-gen GitHub connection." >&2
  echo "Only one browser click is required (GitHub OAuth consent)." >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --auto-approve   Skip terraform apply confirmation prompts" >&2
  echo "  --skip-oauth     Skip connection creation (reuse existing connection)" >&2
  echo "  --tfvars-file    Path to terraform.tfvars (default: terraform/terraform.tfvars)" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto-approve)
      AUTO_APPROVE=true
      ;;
    --skip-oauth)
      SKIP_OAUTH=true
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
PROJECT_ID="$(grep '^project_id' "$TFVARS_FILE" | awk -F'"' '{print $2}')"
REGION="$(grep '^region' "$TFVARS_FILE" | awk -F'"' '{print $2}')"

if [[ -z "$PROJECT_ID" || -z "$REGION" ]]; then
  echo "Error: Could not read project_id or region from $TFVARS_FILE" >&2
  exit 1
fi

echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo ""

# Step 1: Enable required APIs
echo "Step 1/5: Enabling Cloud Build and Secret Manager APIs..."
gcloud services enable cloudbuild.googleapis.com secretmanager.googleapis.com \
  --project="$PROJECT_ID" --quiet

# Step 2: Grant Cloud Build service agent Secret Manager access
echo "Step 2/5: Ensuring Cloud Build service agent has Secret Manager access..."
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
  --role="roles/secretmanager.admin" \
  --condition=None \
  --quiet >/dev/null 2>&1 || true

# Step 3: Create Cloud Build GitHub connection (or reuse existing)
if [[ "$SKIP_OAUTH" == "true" ]]; then
  echo ""
  echo "Step 3/5: Skipping connection creation (--skip-oauth)."
  echo ""
else
  echo ""
  echo "Step 3/5: Creating Cloud Build GitHub connection..."
  echo ""

  # Check if connection already exists and is complete
  EXISTING_STATE="$(gcloud builds connections describe "$CONNECTION_NAME" \
    --region="$REGION" --project="$PROJECT_ID" \
    --format='value(installationState.stage)' 2>/dev/null || echo "NOT_FOUND")"

  if [[ "$EXISTING_STATE" == "COMPLETE" ]]; then
    echo "Connection '$CONNECTION_NAME' already exists and is COMPLETE."
  else
    if [[ "$EXISTING_STATE" == "NOT_FOUND" ]]; then
      echo "Creating connection '$CONNECTION_NAME'..."
      gcloud builds connections create github "$CONNECTION_NAME" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --no-async 2>&1 || true
    fi

    # Step 4: Open browser for OAuth
    echo ""
    echo "Step 4/5: Complete the GitHub OAuth in your browser."
    echo ""
    echo "Instructions:"
    echo "  1. Click 'Authorize Google Cloud Build' in the GitHub consent screen"
    echo "  2. Install the Cloud Build GitHub App on your account/organization"
    echo "  3. Grant access to the foehncast repository"
    echo "  4. Return here — the script will detect completion automatically"
    echo ""

    CONSOLE_URL="https://console.cloud.google.com/cloud-build/repositories/2nd-gen?project=${PROJECT_ID}"
    if command -v open >/dev/null 2>&1; then
      open "$CONSOLE_URL"
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$CONSOLE_URL"
    else
      echo "Open this URL in your browser:"
      echo "  $CONSOLE_URL"
    fi

    echo "Waiting for OAuth to complete..."
    echo "(Polling every 10s. Press Ctrl+C to abort.)"
    echo ""

    MAX_WAIT=600
    ELAPSED=0
    while (( ELAPSED < MAX_WAIT )); do
      STATUS="$(gcloud builds connections describe "$CONNECTION_NAME" \
        --region="$REGION" --project="$PROJECT_ID" \
        --format='value(installationState.stage)' 2>/dev/null || echo "NOT_FOUND")"

      if [[ "$STATUS" == "COMPLETE" ]]; then
        echo "  Connection is COMPLETE."
        break
      fi

      printf "  Status: %s (elapsed: %ds)...\r" "$STATUS" "$ELAPSED"
      sleep 10
      ELAPSED=$((ELAPSED + 10))
    done

    if (( ELAPSED >= MAX_WAIT )); then
      echo ""
      echo "Timed out waiting for OAuth. Complete it in the Console, then rerun with --skip-oauth."
      exit 1
    fi
  fi
fi

# Step 5: Update tfvars and run terraform apply
echo ""
echo "Step 5/5: Applying Terraform (triggers + repository link)..."

# Ensure provision_cloud_build_triggers is set
if grep -q "provision_cloud_build_triggers" "$TFVARS_FILE"; then
  sed -i '' "s/provision_cloud_build_triggers.*/provision_cloud_build_triggers = true/" "$TFVARS_FILE"
else
  printf '\n# --- Cloud Build Triggers ---\nprovision_cloud_build_triggers = true\n' >> "$TFVARS_FILE"
fi

# Import the Cloud Build v2 connection into Terraform state if not already tracked
if ! terraform -chdir="$TERRAFORM_DIR" state show 'google_cloudbuildv2_connection.github[0]' >/dev/null 2>&1; then
  echo "  Importing existing connection into Terraform state..."
  terraform -chdir="$TERRAFORM_DIR" import \
    -var-file="$TFVARS_FILE" \
    'google_cloudbuildv2_connection.github[0]' \
    "projects/${PROJECT_ID}/locations/${REGION}/connections/${CONNECTION_NAME}" 2>/dev/null || true
fi

APPLY_ARGS=(-var-file="$TFVARS_FILE")
if [[ "$AUTO_APPROVE" == "true" ]]; then
  APPLY_ARGS+=(-auto-approve)
fi

terraform -chdir="$TERRAFORM_DIR" apply "${APPLY_ARGS[@]}"

echo ""
echo "Cloud Build triggers provisioned successfully."
echo ""
echo "Triggers created:"
echo "  - publish-app: builds foehncast-app on src/ or containers/app/ changes"
echo "  - publish-mlflow: builds foehncast-mlflow on containers/mlflow/ changes"
echo "  - publish-ui: builds foehncast-ui on ui/ or containers/ui/ changes"
echo ""
echo "Push to main to trigger image builds automatically."
