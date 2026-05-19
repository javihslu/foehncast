"""Regression tests for the cloud operator contract surfaces."""

from __future__ import annotations

import re

from tests.repo_helpers import (
    read_repo_text as _read_text,
    read_repo_yaml as _read_yaml,
    read_workflow_yaml as _workflow_yaml,
)

REPO_VARIABLE_OUTPUTS: list[tuple[str, str]] = [
    ("GCP_PROJECT_ID", "project_id"),
    ("GCP_LOCATION", "location"),
    ("GCP_ARTIFACT_REPOSITORY", "artifact_repository"),
    ("GCP_ARTIFACT_BUCKET_NAME", "artifact_bucket_name"),
    ("GCP_BIGQUERY_DATASET", "bigquery_dataset"),
    ("GCP_BIGQUERY_LOCATION", "bigquery_location"),
    ("GCP_BIGQUERY_TABLE", "bigquery_table"),
    ("GCP_FEAST_ONLINE_STORE_LOCATION", "feast_online_store_location"),
    ("GCP_FEAST_ONLINE_STORE_DATABASE_NAME", "feast_online_store_database_name"),
    ("GCP_WORKLOAD_IDENTITY_PROVIDER", "workload_identity_provider"),
    ("GCP_SERVICE_ACCOUNT_EMAIL", "service_account_email"),
    ("GCP_TERRAFORM_STATE_BUCKET", "state_bucket"),
    ("GCP_TERRAFORM_STATE_PREFIX", "state_prefix"),
    ("GCP_PROVISION_CLOUD_RUN_SERVICE", "provision_cloud_run_service"),
    ("GCP_CLOUD_RUN_SERVICE_NAME", "cloud_run_service_name"),
    ("GCP_CLOUD_RUN_CONTAINER_PORT", "cloud_run_container_port"),
    ("GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED", "cloud_run_allow_unauthenticated"),
    ("GCP_CLOUD_RUN_MIN_INSTANCE_COUNT", "cloud_run_min_instance_count"),
    ("GCP_CLOUD_RUN_MAX_INSTANCE_COUNT", "cloud_run_max_instance_count"),
    ("GCP_CLOUD_RUN_CPU", "cloud_run_cpu"),
    ("GCP_CLOUD_RUN_MEMORY", "cloud_run_memory"),
    ("GCP_MLFLOW_TRACKING_URI", "mlflow_tracking_uri"),
    ("GCP_PROVISION_CLOUD_RUN_MLFLOW", "provision_cloud_run_mlflow"),
    ("GCP_PROVISION_CLOUD_RUN_UI", "provision_cloud_run_ui"),
    ("GCP_CLOUD_RUN_UI_PROMETHEUS_URL", "cloud_run_ui_prometheus_url"),
    ("GCP_PROVISION_CLOUD_WORKFLOWS", "provision_cloud_workflows"),
    ("GCP_CLOUD_RUN_IMAGE", "cloud_run_image"),
    ("GCP_CLOUD_RUN_SERVICE", "cloud_run_service"),
]

WORKFLOW_REPO_ENV_OUTPUTS: list[tuple[str, str]] = [
    ("REPO_GCP_PROJECT_ID", "project_id"),
    ("REPO_GCP_LOCATION", "location"),
    ("REPO_GCP_ARTIFACT_BUCKET_NAME", "artifact_bucket_name"),
    ("REPO_GCP_TERRAFORM_STATE_BUCKET", "state_bucket"),
    ("REPO_GCP_TERRAFORM_STATE_PREFIX", "state_prefix"),
    ("REPO_GCP_ARTIFACT_REPOSITORY", "artifact_repository"),
    ("REPO_GCP_BIGQUERY_DATASET", "bigquery_dataset"),
    ("REPO_GCP_BIGQUERY_LOCATION", "bigquery_location"),
    ("REPO_GCP_BIGQUERY_TABLE", "bigquery_table"),
    ("REPO_GCP_FEAST_ONLINE_STORE_LOCATION", "feast_online_store_location"),
    ("REPO_GCP_FEAST_ONLINE_STORE_DATABASE_NAME", "feast_online_store_database_name"),
    ("REPO_GCP_PROVISION_CLOUD_RUN_SERVICE", "provision_cloud_run_service"),
    ("REPO_GCP_CLOUD_RUN_SERVICE_NAME", "cloud_run_service_name"),
    ("REPO_GCP_CLOUD_RUN_CONTAINER_PORT", "cloud_run_container_port"),
    ("REPO_GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED", "cloud_run_allow_unauthenticated"),
    ("REPO_GCP_CLOUD_RUN_MIN_INSTANCE_COUNT", "cloud_run_min_instance_count"),
    ("REPO_GCP_CLOUD_RUN_MAX_INSTANCE_COUNT", "cloud_run_max_instance_count"),
    ("REPO_GCP_CLOUD_RUN_CPU", "cloud_run_cpu"),
    ("REPO_GCP_CLOUD_RUN_MEMORY", "cloud_run_memory"),
    ("REPO_GCP_MLFLOW_TRACKING_URI", "mlflow_tracking_uri"),
    ("REPO_GCP_CLOUD_RUN_SERVICE", "cloud_run_service"),
]

REPO_BACKED_WORKFLOW_INPUTS = {
    "project_id",
    "region",
    "artifact_bucket_name",
    "artifact_registry_repository_id",
    "bigquery_dataset_id",
    "bigquery_location",
    "bigquery_feature_table_id",
    "feast_online_store_location",
    "feast_online_store_database_name",
    "provision_cloud_run_service",
    "mlflow_tracking_uri",
    "cloud_run_service_name",
    "cloud_run_allow_unauthenticated",
}

FEAST_CLOUD_ENV_KEYS = {
    "FOEHNCAST_FEAST_SOURCE",
    "FOEHNCAST_FEAST_PROJECT",
    "FOEHNCAST_FEAST_PROJECT_ID",
    "FOEHNCAST_FEAST_REGISTRY",
    "FOEHNCAST_FEAST_GCS_BUCKET",
    "FOEHNCAST_FEAST_GCS_STAGING_LOCATION",
    "FOEHNCAST_FEAST_BIGQUERY_DATASET",
    "FOEHNCAST_FEAST_BIGQUERY_LOCATION",
    "FOEHNCAST_FEAST_BIGQUERY_TABLE",
    "FOEHNCAST_FEAST_DATASTORE_DATABASE",
}


def _function_body(relative_path: str, function_name: str) -> str:
    match = re.search(
        rf"^{function_name}\(\) \{{\n(?P<body>.*?)^\}}",
        _read_text(relative_path),
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Could not find function {function_name}"
    return match.group("body")


def _workflow_step(workflow: dict, job_name: str, step_name: str) -> dict:
    for step in workflow["jobs"][job_name]["steps"]:
        if step.get("name") == step_name or step.get("id") == step_name:
            return step
    raise AssertionError(f"Could not find step {step_name}")


def test_terraform_repo_variable_contract_matches_expected_mapping() -> None:
    names_body = _function_body(
        "scripts/terraform-platform-state.sh", "terraform_repo_variable_names"
    )
    names = re.findall(r"^\s+([A-Z0-9_]+)\s*\\?$", names_body, flags=re.MULTILINE)

    pairs_body = _function_body(
        "scripts/terraform-platform-state.sh", "terraform_repo_variable_pairs"
    )
    pair_names = re.findall(r"printf '([A-Z0-9_]+)\\t%s\\n'", pairs_body)

    expected_names = [name for name, _ in REPO_VARIABLE_OUTPUTS]

    assert names == expected_names
    assert set(pair_names) == set(expected_names)


def test_load_gcp_repo_config_matches_repo_variable_contract() -> None:
    action = _read_yaml(".github/actions/load-gcp-repo-config/action.yml")
    outputs = action["outputs"]

    assert set(outputs) == {output for _, output in REPO_VARIABLE_OUTPUTS}

    for output_name, config in outputs.items():
        assert config["value"] == f"${{{{ steps.repo_config.outputs.{output_name} }}}}"

    run_script = action["runs"]["steps"][0]["run"]
    read_pairs = dict(
        re.findall(
            r'echo "([a-z0-9_]+)=\$\(read_repo_var ([A-Z0-9_]+)\)"',
            run_script,
        )
    )

    assert read_pairs == {output: name for name, output in REPO_VARIABLE_OUTPUTS}


def test_remote_terraform_workflow_consumes_repo_backed_contract() -> None:
    workflow = _workflow_yaml(".github/workflows/terraform.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    remote_job = workflow["jobs"]["remote"]

    assert "github.repository_owner" in remote_job["if"]
    assert "environment" not in remote_job
    assert len(inputs) <= 25

    for input_name in REPO_BACKED_WORKFLOW_INPUTS:
        assert input_name in inputs
        assert "default" not in inputs[input_name]

    assert "cloud_run_container_port" not in inputs
    assert "cloud_run_cpu" not in inputs
    assert "cloud_run_memory" not in inputs
    assert "cloud_run_min_instance_count" not in inputs
    assert "cloud_run_max_instance_count" not in inputs

    assert inputs["provision_cloud_run_service"]["type"] == "string"

    resolve_step = _workflow_step(workflow, "remote", "Resolve Terraform inputs")
    env = resolve_step["env"]

    for env_name, output_name in WORKFLOW_REPO_ENV_OUTPUTS:
        assert env[env_name] == f"${{{{ steps.repo_config.outputs.{output_name} }}}}"

    assert "resolve-terraform-inputs.sh" in resolve_step["run"]

    run_script = _read_text("scripts/resolve-terraform-inputs.sh")
    for env_name, _ in WORKFLOW_REPO_ENV_OUTPUTS:
        assert f"${env_name}" in run_script or f"${{{env_name}" in run_script

    assert (
        'provision_cloud_run_service="$(normalize_bool '
        'provision_cloud_run_service "$provision_cloud_run_service")"' in run_script
    )
    assert (
        'cloud_run_container_port="${REPO_GCP_CLOUD_RUN_CONTAINER_PORT:-8080}"'
        in run_script
    )
    assert (
        'cloud_run_container_port="$(normalize_positive_integer cloud_run_container_port "$cloud_run_container_port")"'
        in run_script
    )
    assert (
        'cloud_run_allow_unauthenticated="${INPUT_CLOUD_RUN_ALLOW_UNAUTHENTICATED:-${REPO_GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED:-true}}"'
        in run_script
    )
    assert (
        'cloud_run_allow_unauthenticated="$(normalize_bool cloud_run_allow_unauthenticated "$cloud_run_allow_unauthenticated")"'
        in run_script
    )
    assert (
        'cloud_run_min_instance_count="${REPO_GCP_CLOUD_RUN_MIN_INSTANCE_COUNT:-0}"'
        in run_script
    )
    assert (
        'cloud_run_min_instance_count="$(normalize_non_negative_integer cloud_run_min_instance_count "$cloud_run_min_instance_count")"'
        in run_script
    )
    assert (
        'cloud_run_max_instance_count="${REPO_GCP_CLOUD_RUN_MAX_INSTANCE_COUNT:-2}"'
        in run_script
    )
    assert (
        'cloud_run_max_instance_count="$(normalize_non_negative_integer cloud_run_max_instance_count "$cloud_run_max_instance_count")"'
        in run_script
    )
    assert (
        'echo "cloud_run_max_instance_count must be >= cloud_run_min_instance_count." >&2'
        in run_script
    )
    assert 'cloud_run_cpu="${REPO_GCP_CLOUD_RUN_CPU:-1}"' in run_script
    assert 'cloud_run_memory="${REPO_GCP_CLOUD_RUN_MEMORY:-512Mi}"' in run_script
    assert (
        'feast_online_store_location="${INPUT_FEAST_ONLINE_STORE_LOCATION:-${REPO_GCP_FEAST_ONLINE_STORE_LOCATION:-$region}}"'
        in run_script
    )
    assert (
        'feast_online_store_database_name="${INPUT_FEAST_ONLINE_STORE_DATABASE_NAME:-${REPO_GCP_FEAST_ONLINE_STORE_DATABASE_NAME:-feast-online}}"'
        in run_script
    )
    assert (
        "TF_VAR_feast_online_store_location=${feast_online_store_location}"
        in run_script
    )
    assert (
        "TF_VAR_feast_online_store_database_name=${feast_online_store_database_name}"
        in run_script
    )
    assert "TF_VAR_cloud_run_container_port=${cloud_run_container_port}" in run_script
    assert (
        "TF_VAR_cloud_run_allow_unauthenticated=${cloud_run_allow_unauthenticated}"
        in run_script
    )
    assert (
        "TF_VAR_cloud_run_min_instance_count=${cloud_run_min_instance_count}"
        in run_script
    )
    assert (
        "TF_VAR_cloud_run_max_instance_count=${cloud_run_max_instance_count}"
        in run_script
    )
    assert "TF_VAR_cloud_run_cpu=${cloud_run_cpu}" in run_script
    assert "TF_VAR_cloud_run_memory=${cloud_run_memory}" in run_script


def test_remote_terraform_workflow_is_manual_dispatch_only() -> None:
    workflow = _workflow_yaml(".github/workflows/terraform.yml")

    assert "workflow_dispatch" in workflow["on"]
    assert "push" not in workflow["on"]

    flags_step = _workflow_step(workflow, "remote", "Resolve execution flags")
    flags_script = flags_step["run"]
    assert "command='plan'" in flags_script
    assert 'echo "bootstrap_ready=$bootstrap_ready"' in flags_script


def test_remote_terraform_workflow_treats_repo_variable_sync_as_best_effort() -> None:
    workflow = _workflow_yaml(".github/workflows/terraform.yml")
    remote_job = workflow["jobs"]["remote"]

    assert "env" not in remote_job or "GH_TOKEN" not in remote_job.get("env", {})

    skipped_sync_step = _workflow_step(
        workflow, "remote", "Explain skipped repository variable sync"
    )
    assert "steps.flags.outputs.command == 'apply'" in skipped_sync_step["if"]
    assert (
        "steps.sync_repository_variables.outcome == 'failure'"
        in skipped_sync_step["if"]
    )
    assert (
        "workflow token could not edit GitHub repository variables"
        in skipped_sync_step["run"]
    )
    assert "Existing repository variables remain unchanged." in skipped_sync_step["run"]
    assert "./scripts/configure-github-actions.sh" in skipped_sync_step["run"]

    cleanup_step = _workflow_step(
        workflow, "remote", "Remote cleanup clear repository variables"
    )
    assert cleanup_step["env"]["GH_TOKEN"] == "${{ github.token }}"

    sync_step = _workflow_step(workflow, "remote", "Sync repository variables")
    assert sync_step["id"] == "sync_repository_variables"
    assert sync_step["continue-on-error"] is True
    assert sync_step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "steps.flags.outputs.command == 'apply'" in sync_step["if"]


def test_remote_terraform_workflow_apply_summary_reports_hosted_feast_follow_up() -> (
    None
):
    workflow = _workflow_yaml(".github/workflows/terraform.yml")

    summary_step = _workflow_step(workflow, "remote", "Summarize outputs")
    summary_script = summary_step["run"]

    assert "always()" in summary_step["if"]
    assert "cloud_run_service_url" in summary_script
    assert (
        'feast_bigquery_dataset="$(render_output bigquery_dataset_id "${TF_VAR_bigquery_dataset_id}")"'
        in summary_script
    )
    assert (
        'feast_bigquery_table="$(render_output bigquery_feature_table_id "${TF_VAR_bigquery_feature_table_id}")"'
        in summary_script
    )
    assert (
        'feast_online_store_database_name="$(render_output feast_online_store_database_name "${TF_VAR_feast_online_store_database_name}")"'
        in summary_script
    )
    assert 'echo "- Hosted Feast source: bigquery"' in summary_script
    assert (
        'echo "- Hosted Feast offline source table: ${TF_VAR_project_id}.${feast_bigquery_dataset}.${feast_bigquery_table}"'
        in summary_script
    )
    assert (
        'echo "- Hosted Feast online store database: ${feast_online_store_database_name}"'
        in summary_script
    )


def test_terraform_outputs_expose_primary_hosted_api_contract() -> None:
    outputs = _read_text("terraform/outputs.tf")

    assert 'output "primary_hosted_api_target"' in outputs
    assert 'output "primary_hosted_api_url"' in outputs
    assert '"cloud-run"' in outputs
    assert "google_cloud_run_v2_service.app[0].uri" in outputs


def test_terraform_tfvars_example_promotes_cloud_run_primary_path() -> None:
    tfvars = _read_text("terraform/terraform.tfvars.example")

    assert "provision_cloud_run_service    = true" in tfvars


def test_cloud_run_services_have_health_probes() -> None:
    terraform = _read_text("terraform/main.tf")

    assert "startup_probe" in terraform
    assert "liveness_probe" in terraform
    assert 'path = "/health"' in terraform


def test_cloud_build_triggers_defined_in_terraform() -> None:
    terraform = _read_text("terraform/main.tf")

    assert 'resource "google_cloudbuild_trigger" "publish_app"' in terraform
    assert 'resource "google_cloudbuild_trigger" "publish_airflow"' in terraform
    assert 'resource "google_cloudbuild_trigger" "publish_mlflow"' in terraform
    assert 'resource "google_cloudbuild_trigger" "publish_ui"' in terraform
    assert "cloudbuild/app.yaml" in terraform
    assert "cloudbuild/airflow.yaml" in terraform
    assert "cloudbuild/mlflow.yaml" in terraform
    assert "cloudbuild/ui.yaml" in terraform


def test_trigger_runtime_release_script_uses_airflow_api_contract() -> None:
    script = _read_text("scripts/trigger-runtime-release.sh")
    cli_common = _read_text("scripts/cli-common.sh")
    helper = _read_text("scripts/airflow-api-common.sh")

    assert "require_cli_option_value()" in cli_common
    assert (
        "Usage: $0 --request-file path [--airflow-api-base-url url] [--airflow-api-health-endpoint path]"
        in script
    )
    assert (
        'AIRFLOW_API_BASE_URL="${FOEHNCAST_AIRFLOW_API_BASE_URL:-http://127.0.0.1:8080/api/v2}"'
        in script
    )
    assert (
        'AIRFLOW_API_HEALTH_ENDPOINT="${FOEHNCAST_AIRFLOW_API_HEALTH_ENDPOINT:-/monitor/health}"'
        in script
    )
    assert 'AIRFLOW_API_AUTH_TOKEN="${FOEHNCAST_AIRFLOW_AUTH_TOKEN:-}"' in script
    assert 'if [[ -n "$AIRFLOW_API_AUTH_TOKEN" ]]; then' in script
    assert 'source "${ROOT_DIR}/scripts/cli-common.sh"' in script
    assert 'source "${ROOT_DIR}/scripts/airflow-api-common.sh"' in script
    assert '"$(airflow_api_health_url)"' in script
    assert "python3 -m foehncast.airflow_api" in helper
    assert (
        "${airflow_api_base_url}/dags/${dag_id}/dagRuns?limit=20&order_by=-start_date"
        in helper
    )
    assert "airflow_api_verify_health \\" in script
    assert "airflow_api_wait_for_dag_run_state \\" in script
    assert "trigger_airflow_dag_run()" in script
    assert "--airflow-api-base-url" in script
    assert "--airflow-api-health-endpoint" in script
    assert "python3 -m foehncast.runtime_release" in script
    assert "run_runtime_release_helper" in script
    assert 'PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"' in helper
    assert "normalize-request" in script
    assert (
        'REQUEST_FILE="$(require_cli_option_value "--request-file" "${1:-}" usage)"'
        in script
    )
    assert "--airflow-trigger-mode" not in script
    assert (
        'wait_for_airflow_dag_run_state "$DAG_ID" "$dag_run_id" success 120 2' in script
    )
    assert "verify-report" in script
    assert 'verify-report --expected-run-id "$dag_run_id"' in script
    assert "--report-path" not in script


def test_runtime_image_cloud_build_config_defines_shared_hosted_build_contract() -> (
    None
):
    cloudbuild = _read_text("cloudbuild/runtime-image.yaml")

    assert "gcr.io/cloud-builders/docker" in cloudbuild
    assert (
        'docker build -f "${_DOCKERFILE}" "${tags[@]}" "${_BUILD_CONTEXT}"'
        in cloudbuild
    )
    assert 'docker push "${_IMAGE_REPOSITORY}:sha-${_COMMIT_SHA}"' in cloudbuild
    assert 'if [[ -n "${_FLOATING_TAG}" ]]; then' in cloudbuild
    assert 'docker push "${_FLOATING_TAG}"' in cloudbuild
    assert "images:" in cloudbuild
    assert '"${_IMAGE_REPOSITORY}:sha-${_COMMIT_SHA}"' in cloudbuild
    assert "CLOUD_LOGGING_ONLY" in cloudbuild
    assert (
        "_IMAGE_REPOSITORY: europe-west6-docker.pkg.dev/example-project/foehncast-docker/foehncast-app"
        in cloudbuild
    )
    assert '_FLOATING_TAG: ""' in cloudbuild


def test_cloud_env_pairs_include_feast_runtime_contract() -> None:
    body = _function_body(
        "scripts/terraform-platform-state.sh", "foehncast_cloud_env_pairs"
    )

    assert "printf 'GCP_ARTIFACT_BUCKET_NAME\\t%s\\n'" in body
    assert "GCP_BUCKET_NAME" not in body

    for key in FEAST_CLOUD_ENV_KEYS:
        assert f"printf '{key}\\t%s\\n'" in body


def test_terraform_injects_feast_runtime_contract_into_both_hosted_targets() -> None:
    terraform = _read_text("terraform/main.tf")
    cloud_run_block = re.search(
        r"cloud_run_env_vars = merge\(\n\s*\{\n(?P<body>.*?)\n\s*\},\n\s*var\.cloud_run_env_vars",
        terraform,
        flags=re.DOTALL,
    )

    assert cloud_run_block is not None

    for key in FEAST_CLOUD_ENV_KEYS:
        assert key in cloud_run_block.group("body")

    assert "FOEHNCAST_PIPELINE_REPORT_DIR" in cloud_run_block.group("body")


def test_terraform_grants_hosted_runtime_identities_bigquery_storage_and_bucket_access() -> (
    None
):
    terraform = _read_text("terraform/main.tf")

    assert (
        'resource "google_project_iam_member" "cloud_run_bigquery_read_session_user"'
        in terraform
    )
    assert (
        'resource "google_bigquery_dataset_iam_member" "cloud_run_monitoring_bigquery_editor"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "cloud_run_bucket_metadata_reader"'
        in terraform
    )
    assert 'role    = "roles/bigquery.readSessionUser"' in terraform
    assert 'role       = "roles/bigquery.dataEditor"' in terraform
    assert 'role   = "roles/storage.legacyBucketReader"' in terraform
    assert (
        "google_project_iam_member.cloud_run_bigquery_read_session_user," in terraform
    )
    assert (
        "google_bigquery_dataset_iam_member.cloud_run_monitoring_bigquery_editor,"
        in terraform
    )
    assert (
        "google_storage_bucket_iam_member.cloud_run_bucket_metadata_reader,"
        in terraform
    )


def test_terraform_defines_cloud_build_and_artifact_registry_hosted_image_contract() -> (
    None
):
    terraform = _read_text("terraform/main.tf")
    variables = _read_text("terraform/variables.tf")
    terraform_single_spaced = re.sub(r"[ \t]+", " ", terraform)

    assert (
        'artifact_registry_host = "${var.region}-docker.pkg.dev"'
        in terraform_single_spaced
    )
    assert (
        'artifact_registry_repository_path = "${local.artifact_registry_host}/${var.project_id}/${var.artifact_registry_repository_id}"'
        in terraform_single_spaced
    )
    assert '"cloudbuild.googleapis.com",' in terraform
    assert '"roles/cloudbuild.builds.editor",' in terraform
    assert 'data "google_project" "current"' in terraform
    assert (
        'resource "google_artifact_registry_repository_iam_member" "cloud_build_writer"'
        in terraform
    )
    assert (
        "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
        in terraform
    )
    assert "default Artifact Registry image" not in variables
    assert "default GHCR image" not in variables


def test_terraform_forecast_feature_schema_tracks_direction_encoding_columns() -> None:
    terraform = _read_text("terraform/main.tf")

    assert 'name        = "wind_direction_10m_sin"' in terraform
    assert 'description = "Cyclical sine encoding of 10 m wind direction."' in terraform
    assert 'name        = "wind_direction_10m_cos"' in terraform
    assert (
        'description = "Cyclical cosine encoding of 10 m wind direction."' in terraform
    )


def test_terraform_outputs_split_runtime_identity_contract() -> None:
    outputs = _read_text("terraform/outputs.tf")

    assert 'output "github_deployer_service_account"' in outputs
    assert 'output "cloud_run_runtime_service_account"' in outputs


def test_platform_state_tracks_hosted_runtime_identities_without_repo_var_sync() -> (
    None
):
    names_body = _function_body(
        "scripts/terraform-platform-state.sh", "terraform_repo_variable_names"
    )
    pairs_body = _function_body(
        "scripts/terraform-platform-state.sh", "terraform_repo_variable_pairs"
    )

    assert "GCP_CLOUD_COMPOSER_RUNTIME_SERVICE_ACCOUNT" not in names_body
    assert "GCP_CLOUD_COMPOSER_RUNTIME_SERVICE_ACCOUNT" not in pairs_body


def test_terraform_runtime_iam_includes_bigquery_storage_api_and_bucket_access() -> (
    None
):
    terraform = _read_text("terraform/main.tf")

    assert (
        'resource "google_project_iam_member" "cloud_run_bigquery_read_session_user"'
        in terraform
    )
    assert 'role    = "roles/bigquery.readSessionUser"' in terraform
    assert (
        'resource "google_bigquery_dataset_iam_member" "cloud_run_monitoring_bigquery_editor"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "cloud_run_bucket_metadata_reader"'
        in terraform
    )


def test_terraform_provisions_prediction_event_monitoring_dataset_and_table() -> None:
    terraform = _read_text("terraform/main.tf")
    outputs = _read_text("terraform/outputs.tf")

    assert 'prediction_event_dataset_id       = "foehncast_monitoring"' in terraform
    assert 'prediction_event_table_id         = "prediction_events"' in terraform
    assert "prediction_event_schema = [" in terraform
    assert 'resource "google_bigquery_dataset" "monitoring_store"' in terraform
    assert 'resource "google_bigquery_table" "prediction_events"' in terraform
    assert (
        "dataset_id          = google_bigquery_dataset.monitoring_store.dataset_id"
        in terraform
    )
    assert "table_id            = local.prediction_event_table_id" in terraform
    assert 'field = "prediction_timestamp"' in terraform
    assert 'clustering          = ["model_version", "endpoint", "spot_id"]' in terraform
    assert 'name        = "requested_spot_ids"' in terraform
    assert (
        'description = "JSON-encoded requested spot ids from the inference request."'
        in terraform
    )

    assert 'output "prediction_event_dataset_id"' in outputs
    assert 'output "prediction_event_table_id"' in outputs


def test_terraform_readme_describes_hosted_prediction_event_warehouse_contract() -> (
    None
):
    terraform_readme = _read_text("terraform/README.md")

    assert (
        "a BigQuery dataset and table for retained prediction-event monitoring history"
        in terraform_readme
    )
    assert "foehncast_monitoring.prediction_events" in terraform_readme
    assert (
        "dataset-editor access there so hosted inference can append and read durable prediction-event history"
        in terraform_readme
    )


def test_terraform_grants_github_deployer_firestore_admin() -> None:
    terraform = _read_text("terraform/main.tf")

    assert 'resource "google_project_iam_member" "github_project_admin"' in terraform
    assert '"roles/datastore.owner"' in terraform
    assert "google_project_iam_member.cloud_run_bigquery_read_session_user" in terraform


def test_bootstrap_gcp_reports_hosted_feast_follow_up_step() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "print_feast_runtime_summary()" in bootstrap
    assert "Hosted Feast runtime source: bigquery" in bootstrap
    assert "Hosted Feast offline source table:" in bootstrap
    assert "Hosted Feast online store database:" in bootstrap
    assert (
        "After curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."
        in bootstrap
    )


def test_bootstrap_gcp_uses_explicit_artifact_bucket_env_name() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")
    env_example = _read_text(".env.example")

    assert (
        'artifact_bucket="${GCP_ARTIFACT_BUCKET_NAME:-$(read_tfvars_value_from_file "$TFVARS_FILE" artifact_bucket_name)}"'
        in bootstrap
    )
    assert "GCP_BUCKET_NAME" not in bootstrap
    assert "GCP_ARTIFACT_BUCKET_NAME=foehncast-data" in env_example
    assert "GCP_BUCKET_NAME=" not in env_example


def test_bootstrap_gcp_requires_curl_for_hosted_runtime_verification() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "require_command curl" in bootstrap


def test_bootstrap_gcp_initializes_terraform_with_derived_remote_backend() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "terraform_init_args=(" in bootstrap
    assert '-backend-config="bucket=$(terraform_remote_state_bucket)"' in bootstrap
    assert '-backend-config="prefix=$(terraform_remote_state_prefix)"' in bootstrap
    assert (
        'if [[ "$BOOTSTRAP_ONLY" == "true" && "$PLAN_ONLY" != "true" ]]; then'
        in bootstrap
    )
    assert "  ensure_remote_state_bucket" in bootstrap


def test_bootstrap_gcp_normalizes_custom_env_and_tfvars_paths() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")
    cli_common = _read_text("scripts/cli-common.sh")
    state_helper = _read_text("scripts/terraform-platform-state.sh")

    assert "require_cli_option_value()" in cli_common
    assert "default_terraform_tfvars_file()" in state_helper
    assert (
        'TFVARS_FILE="$(default_terraform_tfvars_file "$TERRAFORM_DIR")"' in bootstrap
    )
    assert "resolve_invocation_path()" in bootstrap
    assert (
        'ENV_FILE="$(require_cli_option_value "--env-file" "${1:-}" usage)"'
        in bootstrap
    )
    assert (
        'TFVARS_FILE="$(require_cli_option_value "--tfvars-file" "${1:-}" usage)"'
        in bootstrap
    )
    assert 'ENV_FILE="$(resolve_invocation_path "$ENV_FILE")"' in bootstrap
    assert 'TFVARS_FILE="$(resolve_invocation_path "$TFVARS_FILE")"' in bootstrap


def test_bootstrap_gcp_uses_isolated_terraform_dir_for_remote_backend() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert (
        'TEMP_TERRAFORM_DIR="$(mktemp -d "${TMPDIR:-/tmp}/foehncast-terraform.XXXXXX")"'
        in bootstrap
    )
    assert 'cp -R "${ROOT_DIR}/terraform/." "$TEMP_TERRAFORM_DIR/"' in bootstrap
    assert 'rm -rf "$TEMP_TERRAFORM_DIR/.terraform"' in bootstrap
    assert (
        'rm -f "$TEMP_TERRAFORM_DIR/terraform.tfstate" "$TEMP_TERRAFORM_DIR/terraform.tfstate.backup"'
        in bootstrap
    )
    assert (
        'echo "Using an isolated Terraform working directory so local state files do not interfere with remote backend initialization."'
        in bootstrap
    )


def test_bootstrap_gcp_reports_cloud_run_url_when_service_is_enabled() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "require_primary_hosted_api_configuration()" in bootstrap
    assert "print_primary_hosted_api_summary()" in bootstrap
    assert (
        'primary_target="$(trimmed_terraform_output_value "$TERRAFORM_DIR" primary_hosted_api_target)"'
        in bootstrap
    )
    assert 'echo "Primary hosted API target: ${primary_target}"' in bootstrap
    assert (
        'print_trimmed_terraform_output_summary "$TERRAFORM_DIR" "Primary hosted API URL" primary_hosted_api_url'
        in bootstrap
    )
    assert "print_cloud_run_summary()" in bootstrap
    assert (
        'print_trimmed_terraform_output_summary "$TERRAFORM_DIR" "Cloud Run service URL" cloud_run_service_url'
        in bootstrap
    )
    assert (
        'echo "Cloud Run allows unauthenticated access: ${FOEHNCAST_TF_CLOUD_RUN_ALLOW_UNAUTHENTICATED}"'
        in bootstrap
    )


def test_bootstrap_gcp_reports_split_runtime_identities() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "print_bootstrap_identity_summary()" in bootstrap
    assert "cloud_run_is_enabled()" in bootstrap
    assert (
        'echo "Cloud Run runtime service account: ${FOEHNCAST_TF_RUNTIME_SERVICE_ACCOUNT}"'
        in bootstrap
    )
    assert "print_bootstrap_identity_summary" in bootstrap
    assert (
        'echo "GitHub deployer service account: ${FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL}"'
        in bootstrap
    )


def test_bootstrap_gcp_verifies_cloud_run_runtime_after_apply() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "verify_cloud_run_runtime()" in bootstrap
    assert "require_curl_payload_patterns()" in bootstrap
    assert (
        'service_url="$(trimmed_terraform_output_value "$TERRAFORM_DIR" cloud_run_service_url)"'
        in bootstrap
    )
    assert 'if ! terraform_platform_value_present "$service_url"; then' in bootstrap
    assert 'health_url="${service_url%/}/health"' in bootstrap
    assert 'spots_url="${service_url%/}/spots"' in bootstrap
    assert 'metrics_url="${service_url%/}/metrics"' in bootstrap
    assert 'echo "Waiting for Cloud Run health at ${health_url}..."' in bootstrap
    assert 'echo "Checking Cloud Run spots endpoint at ${spots_url}..."' in bootstrap
    assert 'echo "Checking Cloud Run metrics at ${metrics_url}..."' in bootstrap
    assert 'endpoint_payload="$(curl "${curl_args[@]}" "$endpoint_url")"' in bootstrap
    assert 'gcloud auth print-identity-token --audiences="$service_url"' in bootstrap
    assert (
        'echo "Cloud Run service requires authenticated invocation; requesting identity token..."'
        in bootstrap
    )
    assert '"model_alias"[[:space:]]*:' in bootstrap
    assert '"model_version"[[:space:]]*:' in bootstrap
    assert '"id"[[:space:]]*:' in bootstrap
    assert 'up{job="foehncast_app"} 1' in bootstrap
    assert (
        'echo "Cloud Run service URL is not available. Fix the Cloud Run configuration instead of skipping hosted runtime verification." >&2'
        in bootstrap
    )
    assert "require_curl_payload_patterns \\" in bootstrap
    assert bootstrap.index("print_feast_runtime_summary") < bootstrap.rindex(
        "verify_cloud_run_runtime"
    )


def test_bootstrap_gcp_prompts_for_primary_cloud_run_and_retained_vm() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")
    state_helper = _read_text("scripts/terraform-platform-state.sh")

    assert "prompt_tfvars_value()" in bootstrap
    assert "tfvars_yes_no_default()" in bootstrap
    assert "foehncast_default_artifact_repository()" in state_helper
    assert "foehncast_default_bigquery_dataset()" in state_helper
    assert "foehncast_default_bigquery_table()" in state_helper
    assert "foehncast_default_feast_online_store_database()" in state_helper
    assert "foehncast_default_cloud_run_service_name()" in state_helper
    assert (
        'cloud_run_default="$(tfvars_yes_no_default provision_cloud_run_service)"'
        in bootstrap
    )
    assert (
        'cloud_run_service="$(prompt_tfvars_value cloud_run_service_name "Cloud Run service name" "$(foehncast_default_cloud_run_service_name)")"'
        in bootstrap
    )
    assert (
        "Provision Cloud Run as the primary hosted API now? This needs a reachable MLflow endpoint."
        in bootstrap
    )


def test_prepare_feast_cloud_requires_bigquery_runtime_contract() -> None:
    script = _read_text("scripts/prepare-feast-cloud.sh")
    cli_common = _read_text("scripts/cli-common.sh")

    assert "require_cli_option_value()" in cli_common
    assert (
        'MATERIALIZE_TS="$(require_cli_option_value "--materialize-to" "${1:-}" usage)"'
        in script
    )
    assert "require_any_env_value()" in script
    assert (
        'export FOEHNCAST_FEAST_SOURCE="${FOEHNCAST_FEAST_SOURCE:-bigquery}"' in script
    )
    assert (
        'export FOEHNCAST_FEAST_GCS_BUCKET="${FOEHNCAST_FEAST_GCS_BUCKET:-${GCP_BUCKET_NAME:-}}"'
        not in script
    )
    assert 'if [[ "$FOEHNCAST_FEAST_SOURCE" != "bigquery" ]]; then' in script
    assert (
        'echo "prepare-feast-cloud.sh requires FOEHNCAST_FEAST_SOURCE=bigquery" >&2'
        in script
    )
    assert (
        'require_env_var FOEHNCAST_FEAST_BIGQUERY_TABLE "Set FOEHNCAST_FEAST_BIGQUERY_TABLE in .env or the environment."'
        in script
    )
    assert (
        'require_any_env_value "Set GCP_PROJECT_ID or FOEHNCAST_FEAST_PROJECT_ID in .env or the environment." \\'
        in script
    )
    assert (
        'require_any_env_value "Set FOEHNCAST_FEAST_GCS_BUCKET or FOEHNCAST_FEAST_REGISTRY in .env or the environment." \\'
        in script
    )
    assert (
        'require_any_env_value "Set FOEHNCAST_FEAST_GCS_BUCKET or FOEHNCAST_FEAST_GCS_STAGING_LOCATION in .env or the environment." \\'
        in script
    )


def test_prepare_feast_local_uses_resolved_env_helpers() -> None:
    script = _read_text("scripts/prepare-feast-local.sh")
    cli_common = _read_text("scripts/cli-common.sh")
    helper = _read_text("scripts/env-file-common.sh")

    assert "require_cli_option_value()" in cli_common
    assert "render_feast_runtime_config_path()" in cli_common
    assert "run_feast_repo_apply_and_maybe_materialize()" in cli_common
    assert "print_feast_materialize_status()" in cli_common
    assert 'source "${ROOT_DIR}/scripts/env-file-common.sh"' in script
    assert 'DATASET="$(require_cli_option_value "--dataset" "${1:-}" usage)"' in script
    assert "env_file_value()" in helper
    assert "resolved_env_value()" in helper
    assert "export_resolved_env_value()" in helper
    assert "ensure_env_default()" in helper
    assert "export_local_feast_datastore_env()" in helper
    assert 'for file_path in "$@"; do' in helper
    assert (
        'export_local_feast_datastore_env "$DEFAULT_ENV_FILE" "$EXAMPLE_ENV_FILE"'
        in script
    )
    assert 'CONFIG_PATH="$(render_feast_runtime_config_path "$ROOT_DIR")"' in script
    assert (
        'run_feast_repo_apply_and_maybe_materialize "$ROOT_DIR/feature_repo" "$MATERIALIZE" "$MATERIALIZE_TS"'
        in script
    )
    assert (
        'print_feast_materialize_status "$ROOT_DIR" "$MATERIALIZE" "$MATERIALIZE_TS"'
        in script
    )


def test_prepare_feast_cloud_renders_runtime_config_and_applies_repo() -> None:
    script = _read_text("scripts/prepare-feast-cloud.sh")
    cli_common = _read_text("scripts/cli-common.sh")

    assert "render_feast_runtime_config_path()" in cli_common
    assert 'CONFIG_PATH="$(render_feast_runtime_config_path "$ROOT_DIR")"' in script
    assert "export_feast_runtime_config_path()" in cli_common
    assert "run_feast_repo_apply_and_maybe_materialize()" in cli_common
    assert 'export_feast_runtime_config_path "$CONFIG_PATH"' in script
    assert "uv run python -m foehncast.feast_runtime" in cli_common
    assert "uv run --group feast feast apply >/dev/null" in cli_common
    assert (
        'run_feast_repo_apply_and_maybe_materialize "$ROOT_DIR/feature_repo" "$MATERIALIZE" "$MATERIALIZE_TS"'
        in script
    )


def test_prepare_feast_cloud_materializes_or_prints_next_step() -> None:
    script = _read_text("scripts/prepare-feast-cloud.sh")
    cli_common = _read_text("scripts/cli-common.sh")

    assert (
        'uv run --group feast feast materialize-incremental "$materialize_ts" >/dev/null'
        in cli_common
    )
    assert "print_feast_materialize_status()" in cli_common
    assert "printf 'Materialized through: %s\\n' \"$materialize_ts\"" in cli_common
    assert (
        'printf \'Next: cd %s/feature_repo && uv run --group feast feast materialize-incremental "%s"\\n\' "$root_dir" "$materialize_ts"'
        in cli_common
    )
    assert (
        'print_feast_materialize_status "$ROOT_DIR" "$MATERIALIZE" "$MATERIALIZE_TS"'
        in script
    )


def test_smoke_bootstrap_only_seeds_hosted_feast_defaults() -> None:
    script = _read_text("scripts/smoke-bootstrap-only.sh")

    assert 'TARGET_REPO="$(require_cli_option_value "--repo" "${1:-}" usage)"' in script
    assert (
        'PROJECT_ID="$(require_cli_option_value "--project-id" "${1:-}" usage)"'
        in script
    )
    assert 'REGION="$(require_cli_option_value "--region" "${1:-}" usage)"' in script
    assert "smoke_feast_bigquery_table()" in script
    assert "print_smoke_feast_summary()" in script
    assert (
        'printf \'%s.%s.%s\\n\' "$PROJECT_ID" "$(foehncast_default_bigquery_dataset)" "$(foehncast_default_bigquery_table)"'
        in script
    )
    assert 'echo "- hosted Feast source: bigquery"' in script
    assert (
        'echo "- hosted Feast offline source table: $(smoke_feast_bigquery_table)"'
        in script
    )
    assert (
        'echo "- hosted Feast online store database: $(foehncast_default_feast_online_store_database)"'
        in script
    )
    assert '"$(foehncast_default_bigquery_dataset)" \\' in script
    assert '"$(foehncast_default_bigquery_table)" \\' in script
    assert '"$(foehncast_default_feast_online_store_database)" \\' in script


def test_smoke_bootstrap_only_reports_feast_follow_up_when_environment_is_kept() -> (
    None
):
    script = _read_text("scripts/smoke-bootstrap-only.sh")

    assert "print_smoke_feast_summary" in script
    assert (
        'echo "When curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."'
        in script
    )


def test_terraform_remote_reports_hosted_feast_follow_up_for_apply() -> None:
    script = _read_text("scripts/terraform-remote.sh")
    state_helper = _read_text("scripts/terraform-platform-state.sh")

    assert "resolved_repo_backed_value()" in script
    assert 'source "${ROOT_DIR}/scripts/terraform-platform-state.sh"' in script
    assert "foehncast_default_bigquery_dataset()" in state_helper
    assert "foehncast_default_bigquery_table()" in state_helper
    assert "foehncast_default_feast_online_store_database()" in state_helper
    assert "remote_feast_bigquery_dataset()" in script
    assert "resolved_repo_backed_value \\" in script
    assert '"${INPUT_BIGQUERY_DATASET_ID:-}" \\' in script
    assert "GCP_BIGQUERY_DATASET \\" in script
    assert (
        '"${GCP_BIGQUERY_DATASET:-${STORAGE_BIGQUERY_DATASET:-${FOEHNCAST_FEAST_BIGQUERY_DATASET:-$(foehncast_default_bigquery_dataset)}}}"'
        in script
    )
    assert "remote_feast_bigquery_table()" in script
    assert (
        'if [[ -z "$INPUT_BIGQUERY_DATASET_ID" && -z "$INPUT_BIGQUERY_FEATURE_TABLE_ID" ]]; then'
        in script
    )
    assert 'runtime_table="${FOEHNCAST_FEAST_BIGQUERY_TABLE:-}"' in script
    assert (
        'table_id="$(resolved_repo_backed_value "${INPUT_BIGQUERY_FEATURE_TABLE_ID:-}" GCP_BIGQUERY_TABLE "${GCP_BIGQUERY_TABLE:-${STORAGE_BIGQUERY_TABLE:-$(foehncast_default_bigquery_table)}}")"'
        in script
    )
    assert 'project_id="${PROJECT_ID:-<project_id>}"' in script
    assert '"${INPUT_FEAST_ONLINE_STORE_DATABASE_NAME:-}" \\' in script
    assert "GCP_FEAST_ONLINE_STORE_DATABASE_NAME \\" in script
    assert (
        '"${GCP_FEAST_ONLINE_STORE_DATABASE_NAME:-${FOEHNCAST_FEAST_DATASTORE_DATABASE:-$(foehncast_default_feast_online_store_database)}}"'
        in script
    )
    assert (
        'PROJECT_ID="$(resolved_repo_backed_value "$PROJECT_ID" GCP_PROJECT_ID "${GCP_PROJECT_ID:-}")"'
        in script
    )
    assert (
        'REGION="$(resolved_repo_backed_value "$REGION" GCP_LOCATION "${GCP_LOCATION:-}")"'
        in script
    )
    assert "bigquery_dataset_id)" in script
    assert 'INPUT_BIGQUERY_DATASET_ID="$value"' in script
    assert "bigquery_feature_table_id)" in script
    assert 'INPUT_BIGQUERY_FEATURE_TABLE_ID="$value"' in script
    assert "feast_online_store_database_name)" in script
    assert 'INPUT_FEAST_ONLINE_STORE_DATABASE_NAME="$value"' in script
    assert "cloud_run_container_port|cloud_run_cpu|cloud_run_memory)" in script
    assert (
        'echo "${key} is not exposed as a workflow_dispatch input. Update the synced repository variable or Terraform configuration instead." >&2'
        in script
    )
    assert 'echo "Hosted Feast runtime source: bigquery"' in script
    assert (
        'echo "Hosted Feast offline source table: $(remote_feast_bigquery_table)"'
        in script
    )
    assert (
        'echo "Hosted Feast online store database: $(remote_feast_online_store_database)"'
        in script
    )
    assert (
        'echo "After curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."'
        in script
    )
    assert (
        'echo "After the remote apply succeeds and curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."'
        in script
    )
    assert 'if [[ "$COMMAND" == "apply" ]]; then' in script
    assert "print_remote_feast_follow_up" in script


def test_terraform_declares_gcs_backend_for_remote_state() -> None:
    providers = _read_text("terraform/providers.tf")

    assert 'backend "gcs" {}' in providers


def test_cloud_scripts_use_shared_terraform_runner() -> None:
    cli_common = _read_text("scripts/cli-common.sh")
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")
    configure = _read_text("scripts/configure-github-actions.sh")
    teardown = _read_text("scripts/teardown-gcp.sh")
    state_helper = _read_text("scripts/terraform-platform-state.sh")

    assert "run_terraform()" in cli_common
    assert "ensure_terraform_command()" in cli_common
    assert "require_command terraform" in cli_common
    assert "require_file()" in cli_common
    assert "require_cli_option_value()" in cli_common
    assert "hashicorp/terraform:" not in cli_common

    assert "require_command terraform" not in bootstrap
    assert 'source "${ROOT_DIR}/scripts/terraform-platform-state.sh"' in bootstrap
    assert "require_file()" not in bootstrap
    assert 'run_terraform -chdir="$TERRAFORM_DIR"' in bootstrap

    assert "ensure_terraform_command" in configure
    assert 'run_terraform -chdir="$terraform_dir" output -json' in state_helper

    assert "require_command terraform" not in teardown
    assert 'source "${ROOT_DIR}/scripts/terraform-platform-state.sh"' in teardown
    assert 'TFVARS_FILE="$(default_terraform_tfvars_file "$TERRAFORM_DIR")"' in teardown
    assert "require_file()" not in teardown
    assert 'run_terraform -chdir="${ROOT_DIR}/terraform" init' in teardown
    assert "print_missing_destroy_tfvars_preview_message()" in teardown
    assert (
        'echo "Terraform variables file not found: $TFVARS_FILE. Nothing to preview in this working copy."'
        in teardown
    )
    assert (
        'echo "Reuse the file created for provisioning to preview local destroy targets, or use ./scripts/terraform-remote.sh destroy when the active environment is managed through the remote backend."'
        in teardown
    )

    assert "trim_terraform_platform_value" in state_helper
    assert "default_terraform_tfvars_file()" in state_helper
    assert "read_tfvars_value_from_file()" in state_helper
    assert "trim_whitespace()" not in bootstrap
    assert "read_tfvars_value()" not in bootstrap
    assert 'value="$(read_tfvars_value_from_file "$TFVARS_FILE" "$key")"' in bootstrap
    assert 'trim_terraform_platform_value "$value"' in state_helper
    assert 'trimmed_terraform_output_value "$TERRAFORM_DIR"' in bootstrap


def test_cloud_scripts_share_github_repo_helpers() -> None:
    github_common = _read_text("scripts/github-common.sh")
    configure = _read_text("scripts/configure-github-actions.sh")
    remote = _read_text("scripts/terraform-remote.sh")

    assert "resolve_repo_from_remote()" in github_common
    assert "require_repo_from_remote()" in github_common
    assert "resolve_target_repo()" in github_common
    assert "require_github_auth()" in github_common
    assert "repo_variable_value()" in github_common

    assert "resolve_repo()" not in configure
    assert "gh auth status" not in configure
    assert "require_github_auth" in configure
    assert (
        'TARGET_REPO="$(require_cli_option_value "--repo" "${1:-}" usage)"' in configure
    )
    assert (
        'TERRAFORM_DIR="$(require_cli_option_value "--terraform-dir" "${1:-}" usage)"'
        in configure
    )
    assert (
        'REPOSITORY_PATH="$(resolve_target_repo "$ROOT_DIR" "$TARGET_REPO")"'
        in configure
    )

    assert "repo_variable_value()" not in remote
    assert "gh auth status" not in remote
    assert "require_github_auth" in remote
    assert 'TARGET_REPO="$(require_cli_option_value "--repo" "${1:-}" usage)"' in remote
    assert (
        'ENV_FILE="$(require_cli_option_value "--env-file" "${1:-}" usage)"' in remote
    )
    assert (
        'record_input "$(require_cli_option_value "--input" "${1:-}" usage)"' in remote
    )
    assert (
        'WATCH_INTERVAL="$(require_cli_option_value "--watch-interval" "${1:-}" usage)"'
        in remote
    )
    assert (
        'REPOSITORY_PATH="$(resolve_target_repo "$ROOT_DIR" "$TARGET_REPO")"' in remote
    )


def test_local_and_runtime_release_scripts_share_airflow_shell_helper() -> None:
    helper = _read_text("scripts/airflow-api-common.sh")
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    trigger = _read_text("scripts/trigger-runtime-release.sh")

    assert "airflow_api_helper_run()" in helper
    assert "airflow_api_verify_health()" in helper
    assert "airflow_api_wait_for_dag_run_state()" in helper
    assert 'PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"' in helper
    assert "python3 -m foehncast.airflow_api" in helper
    assert "Authorization: Bearer ${auth_token}" in helper
    assert "eval " not in helper
    assert "_AIRFLOW_API_AUTH_TOKEN" not in helper
    assert "_AIRFLOW_API_VERSION" not in helper

    assert 'source "${ROOT_DIR}/scripts/airflow-api-common.sh"' in bootstrap
    assert 'source "${ROOT_DIR}/scripts/airflow-api-common.sh"' in trigger
    assert "airflow_api_verify_health \\" in bootstrap
    assert "airflow_api_wait_for_dag_run_state \\" in bootstrap
    assert "airflow_api_verify_health \\" in trigger
    assert "airflow_api_wait_for_dag_run_state \\" in trigger


def test_local_scripts_share_env_file_helper() -> None:
    helper = _read_text("scripts/env-file-common.sh")
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    feast = _read_text("scripts/prepare-feast-local.sh")

    assert "env_file_value()" in helper
    assert "resolved_env_value()" in helper
    assert "export_resolved_env_value()" in helper
    assert "ensure_env_default()" in helper
    assert 'source "${ROOT_DIR}/scripts/env-file-common.sh"' in bootstrap
    assert 'source "${ROOT_DIR}/scripts/env-file-common.sh"' in feast
    assert "env_file_value()" not in bootstrap
    assert "env_file_value()" not in feast


def test_bootstrap_scripts_share_payload_check_helper() -> None:
    helper = _read_text("scripts/payload-check-common.sh")
    local_bootstrap = _read_text("scripts/bootstrap-local.sh")
    cloud_bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "payload_check_require_pattern()" in helper
    assert "payload_check_require_patterns()" in helper
    assert 'source "${ROOT_DIR}/scripts/payload-check-common.sh"' in local_bootstrap
    assert 'source "${ROOT_DIR}/scripts/payload-check-common.sh"' in cloud_bootstrap
    assert (
        'payload_check_require_pattern "Hosted bootstrap verification failed"'
        in cloud_bootstrap
    )
    assert (
        'payload_check_require_patterns "Hosted bootstrap verification failed"'
        in cloud_bootstrap
    )


def test_cloud_operator_scripts_share_gcp_project_access_helper() -> None:
    helper = _read_text("scripts/gcp-common.sh")
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")
    teardown = _read_text("scripts/teardown-gcp.sh")

    assert "verify_gcp_project_access()" in helper
    assert 'echo "Authenticating with Google Cloud via browser if needed..."' in helper
    assert 'echo "Checking access to GCP project ${GCP_PROJECT_ID}..."' in helper
    assert 'gcloud projects describe "$GCP_PROJECT_ID" >/dev/null' in helper
    assert 'source "${ROOT_DIR}/scripts/gcp-common.sh"' in bootstrap
    assert 'source "${ROOT_DIR}/scripts/gcp-common.sh"' in teardown
    assert (
        'verify_gcp_project_access "$ENV_FILE" "${ROOT_DIR}/scripts/gcp-auth.sh"'
        in bootstrap
    )
    assert (
        'verify_gcp_project_access "$ENV_FILE" "${ROOT_DIR}/scripts/gcp-auth.sh"'
        in teardown
    )
    assert (
        'echo "Authenticating with Google Cloud via browser if needed..."'
        not in bootstrap
    )
    assert 'echo "Checking access to GCP project ${GCP_PROJECT_ID}..."' not in bootstrap
    assert (
        'echo "Authenticating with Google Cloud via browser if needed..."'
        not in teardown
    )
    assert 'echo "Checking access to GCP project ${GCP_PROJECT_ID}..."' not in teardown


def test_teardown_gcp_uses_small_summary_helpers() -> None:
    teardown = _read_text("scripts/teardown-gcp.sh")

    assert (
        'ENV_FILE="$(require_cli_option_value "--env-file" "${1:-}" usage)"' in teardown
    )
    assert (
        'TFVARS_FILE="$(require_cli_option_value "--tfvars-file" "${1:-}" usage)"'
        in teardown
    )
    assert (
        'TARGET_REPO="$(require_cli_option_value "--repo" "${1:-}" usage)"' in teardown
    )
    assert "require_destroy_tfvars_file()" in teardown
    assert "print_enabled_message()" in teardown
    assert "print_state_message()" in teardown
    assert "print_remote_backend_destroy_guidance()" in teardown
    assert "print_no_local_terraform_state_message()" in teardown
    assert "print_missing_destroy_tfvars_preview_message()" in teardown
    assert "trim_whitespace()" not in teardown
    assert "require_destroy_tfvars_file" in teardown
    assert (
        'print_no_local_terraform_state_message "Nothing to preview in this working copy."'
        in teardown
    )
    assert (
        'print_no_local_terraform_state_message "Nothing to destroy in this working copy."'
        in teardown
    )
    assert (
        'print_no_local_terraform_state_message "Skipping Terraform destroy path."'
        in teardown
    )
    assert (
        'print_enabled_message "$CLEAR_GITHUB_ACTIONS" "GitHub Actions variables were not changed because --plan-only was set."'
        in teardown
    )
    assert (
        'print_state_message "$TERRAFORM_DESTROYED" "Terraform destroy completed using ${TFVARS_FILE}." "Terraform-managed resources were left unchanged."'
        in teardown
    )
    assert (
        'print_state_message "$DELETE_PROJECT" "The GCP project delete path was executed." "The GCP project was left unchanged."'
        in teardown
    )
