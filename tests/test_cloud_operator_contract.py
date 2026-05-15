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
    (
        "GCP_PROVISION_CLOUD_COMPOSER_ENVIRONMENT",
        "provision_cloud_composer_environment",
    ),
    ("GCP_CLOUD_COMPOSER_ENVIRONMENT_NAME", "cloud_composer_environment_name"),
    ("GCP_PROVISION_ONLINE_COMPOSE_HOST", "provision_online_compose_host"),
    ("GCP_ONLINE_COMPOSE_HOST_NAME", "online_compose_host_name"),
    ("GCP_ONLINE_COMPOSE_HOST_ZONE", "online_compose_host_zone"),
    ("GCP_ONLINE_COMPOSE_MACHINE_TYPE", "online_compose_machine_type"),
    ("GCP_ONLINE_COMPOSE_DISK_SIZE_GB", "online_compose_disk_size_gb"),
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
    (
        "REPO_GCP_PROVISION_CLOUD_COMPOSER_ENVIRONMENT",
        "provision_cloud_composer_environment",
    ),
    (
        "REPO_GCP_CLOUD_COMPOSER_ENVIRONMENT_NAME",
        "cloud_composer_environment_name",
    ),
    ("REPO_GCP_PROVISION_ONLINE_COMPOSE_HOST", "provision_online_compose_host"),
    ("REPO_GCP_ONLINE_COMPOSE_HOST_NAME", "online_compose_host_name"),
    ("REPO_GCP_ONLINE_COMPOSE_HOST_ZONE", "online_compose_host_zone"),
    ("REPO_GCP_ONLINE_COMPOSE_MACHINE_TYPE", "online_compose_machine_type"),
    ("REPO_GCP_ONLINE_COMPOSE_DISK_SIZE_GB", "online_compose_disk_size_gb"),
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
    "provision_cloud_composer_environment",
    "cloud_composer_environment_name",
    "provision_online_compose_host",
    "online_compose_host_name",
    "online_compose_host_zone",
    "online_compose_machine_type",
    "online_compose_disk_size_gb",
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

    assert "github.event_name == 'workflow_dispatch' ||" in remote_job["if"]
    assert "github.event_name == 'push'" in remote_job["if"]
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
    assert inputs["provision_cloud_composer_environment"]["type"] == "string"
    assert inputs["provision_online_compose_host"]["type"] == "string"

    resolve_step = _workflow_step(workflow, "remote", "Resolve Terraform inputs")
    env = resolve_step["env"]

    for env_name, output_name in WORKFLOW_REPO_ENV_OUTPUTS:
        assert env[env_name] == f"${{{{ steps.repo_config.outputs.{output_name} }}}}"

    run_script = resolve_step["run"]
    for env_name, _ in WORKFLOW_REPO_ENV_OUTPUTS:
        assert f"${env_name}" in run_script

    assert (
        'provision_cloud_run_service="$(normalize_bool '
        'provision_cloud_run_service "$provision_cloud_run_service")"' in run_script
    )
    assert (
        'provision_online_compose_host="$(normalize_bool '
        'provision_online_compose_host "$provision_online_compose_host")"' in run_script
    )
    assert 'cloud_run_container_port="$REPO_GCP_CLOUD_RUN_CONTAINER_PORT"' in run_script
    assert "cloud_run_container_port='8080'" in run_script
    assert (
        'cloud_run_container_port="$(normalize_positive_integer cloud_run_container_port "$cloud_run_container_port")"'
        in run_script
    )
    assert (
        'cloud_run_allow_unauthenticated="${{ inputs.cloud_run_allow_unauthenticated }}"'
        in run_script
    )
    assert (
        'cloud_run_allow_unauthenticated="$REPO_GCP_CLOUD_RUN_ALLOW_UNAUTHENTICATED"'
        in run_script
    )
    assert "cloud_run_allow_unauthenticated='true'" in run_script
    assert (
        'cloud_run_allow_unauthenticated="$(normalize_bool cloud_run_allow_unauthenticated "$cloud_run_allow_unauthenticated")"'
        in run_script
    )
    assert (
        'cloud_run_min_instance_count="$REPO_GCP_CLOUD_RUN_MIN_INSTANCE_COUNT"'
        in run_script
    )
    assert "cloud_run_min_instance_count='0'" in run_script
    assert (
        'cloud_run_min_instance_count="$(normalize_non_negative_integer cloud_run_min_instance_count "$cloud_run_min_instance_count")"'
        in run_script
    )
    assert (
        'cloud_run_max_instance_count="$REPO_GCP_CLOUD_RUN_MAX_INSTANCE_COUNT"'
        in run_script
    )
    assert "cloud_run_max_instance_count='2'" in run_script
    assert (
        'cloud_run_max_instance_count="$(normalize_non_negative_integer cloud_run_max_instance_count "$cloud_run_max_instance_count")"'
        in run_script
    )
    assert (
        'echo "cloud_run_max_instance_count must be greater than or equal to cloud_run_min_instance_count." >&2'
        in run_script
    )
    assert 'cloud_run_cpu="$REPO_GCP_CLOUD_RUN_CPU"' in run_script
    assert "cloud_run_cpu='1'" in run_script
    assert 'cloud_run_memory="$REPO_GCP_CLOUD_RUN_MEMORY"' in run_script
    assert "cloud_run_memory='512Mi'" in run_script
    assert (
        'provision_cloud_composer_environment="${{ inputs.provision_cloud_composer_environment }}"'
        in run_script
    )
    assert (
        'provision_cloud_composer_environment="$REPO_GCP_PROVISION_CLOUD_COMPOSER_ENVIRONMENT"'
        in run_script
    )
    assert "provision_cloud_composer_environment='false'" in run_script
    assert (
        'provision_cloud_composer_environment="$(normalize_bool provision_cloud_composer_environment "$provision_cloud_composer_environment")"'
        in run_script
    )
    assert (
        'cloud_composer_environment_name="${{ inputs.cloud_composer_environment_name }}"'
        in run_script
    )
    assert (
        'cloud_composer_environment_name="$REPO_GCP_CLOUD_COMPOSER_ENVIRONMENT_NAME"'
        in run_script
    )
    assert "cloud_composer_environment_name='foehncast-composer'" in run_script
    assert (
        'feast_online_store_location="${{ inputs.feast_online_store_location }}"'
        in run_script
    )
    assert (
        'feast_online_store_location="$REPO_GCP_FEAST_ONLINE_STORE_LOCATION"'
        in run_script
    )
    assert 'feast_online_store_location="$region"' in run_script
    assert (
        'feast_online_store_database_name="${{ inputs.feast_online_store_database_name }}"'
        in run_script
    )
    assert (
        'feast_online_store_database_name="$REPO_GCP_FEAST_ONLINE_STORE_DATABASE_NAME"'
        in run_script
    )
    assert "feast_online_store_database_name='feast-online'" in run_script
    assert (
        'echo "TF_VAR_feast_online_store_location=${feast_online_store_location}"'
        in run_script
    )
    assert (
        'echo "TF_VAR_feast_online_store_database_name=${feast_online_store_database_name}"'
        in run_script
    )
    assert (
        'echo "TF_VAR_cloud_run_container_port=${cloud_run_container_port}"'
        in run_script
    )
    assert (
        'echo "TF_VAR_cloud_run_allow_unauthenticated=${cloud_run_allow_unauthenticated}"'
        in run_script
    )
    assert (
        'echo "TF_VAR_cloud_run_min_instance_count=${cloud_run_min_instance_count}"'
        in run_script
    )
    assert (
        'echo "TF_VAR_cloud_run_max_instance_count=${cloud_run_max_instance_count}"'
        in run_script
    )
    assert 'echo "TF_VAR_cloud_run_cpu=${cloud_run_cpu}"' in run_script
    assert 'echo "TF_VAR_cloud_run_memory=${cloud_run_memory}"' in run_script
    assert (
        'echo "TF_VAR_provision_cloud_composer_environment=${provision_cloud_composer_environment}"'
        in run_script
    )
    assert (
        'echo "TF_VAR_cloud_composer_environment_name=${cloud_composer_environment_name}"'
        in run_script
    )


def test_remote_terraform_workflow_auto_applies_on_push_when_bootstrapped() -> None:
    workflow = _workflow_yaml(".github/workflows/terraform.yml")

    flags_step = _workflow_step(workflow, "remote", "Resolve execution flags")
    flags_script = flags_step["run"]
    assert "if [[ \"$EVENT_NAME\" == 'push' ]]; then" in flags_script
    assert "command='apply'" in flags_script
    assert 'echo "bootstrap_ready=$bootstrap_ready"' in flags_script

    apply_step = _workflow_step(workflow, "remote", "Terraform apply chosen plan")
    assert "steps.flags.outputs.command == 'apply'" in apply_step["if"]

    skipped_step = _workflow_step(
        workflow, "remote", "Explain skipped automatic apply before bootstrap"
    )
    assert "github.event_name == 'push'" in skipped_step["if"]


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
    assert (
        'echo "- Primary hosted API target: $(render_output primary_hosted_api_target not-provisioned)"'
        in summary_script
    )
    assert (
        'echo "- Primary hosted API URL: $(render_output primary_hosted_api_url not-provisioned)"'
        in summary_script
    )
    assert (
        'echo "- Primary hosted API verification: ${{ steps.verify_hosted_runtimes.outputs.primary_hosted_api_verification_status }}"'
        in summary_script
    )
    assert (
        'echo "- Cloud Run verification: ${{ steps.verify_hosted_runtimes.outputs.cloud_run_verification_status }}"'
        in summary_script
    )
    assert (
        'echo "- Cloud Run invocation: ${{ steps.verify_hosted_runtimes.outputs.cloud_run_invocation_mode }}"'
        in summary_script
    )
    assert (
        'echo "- Hosted VM public app surface: ${{ steps.verify_hosted_runtimes.outputs.online_compose_verification_status }}"'
        in summary_script
    )

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
    assert (
        'echo "- Feast follow-up: after curated BigQuery rows are available, run ./scripts/prepare-feast-cloud.sh to apply the Feast repo and materialize the hosted online store."'
        in summary_script
    )


def test_terraform_outputs_expose_primary_hosted_api_contract() -> None:
    outputs = _read_text("terraform/outputs.tf")

    assert 'output "primary_hosted_api_target"' in outputs
    assert 'output "primary_hosted_api_url"' in outputs
    assert '"cloud-run"' in outputs
    assert "google_cloud_run_v2_service.app[0].uri" in outputs


def test_terraform_online_compose_public_ports_default_to_private_control_plane() -> (
    None
):
    variables = _read_text("terraform/variables.tf")

    assert 'variable "online_compose_public_ports"' in variables
    assert "default     = []" in variables


def test_terraform_tfvars_example_promotes_cloud_run_primary_path() -> None:
    tfvars = _read_text("terraform/terraform.tfvars.example")

    assert "provision_cloud_run_service    = true" in tfvars
    assert re.search(
        r"^provision_cloud_composer_environment\s+=\s+false$",
        tfvars,
        flags=re.MULTILINE,
    )
    assert re.search(
        r'^cloud_composer_environment_name\s+=\s+"foehncast-composer"$',
        tfvars,
        flags=re.MULTILINE,
    )
    assert "provision_online_compose_host  = true" in tfvars
    assert "online_compose_public_ports    = []" in tfvars


def test_remote_terraform_workflow_verifies_hosted_runtimes_after_apply() -> None:
    workflow = _workflow_yaml(".github/workflows/terraform.yml")

    verify_step = _workflow_step(workflow, "remote", "Verify hosted runtimes")
    verify_script = verify_step["run"]

    assert verify_step["id"] == "verify_hosted_runtimes"
    assert (
        "if [[ \"${TF_VAR_provision_cloud_run_service}\" != 'true' ]]; then"
        in verify_script
    )
    assert (
        'online_compose_app_url="$(terraform -chdir=terraform output -raw online_compose_app_url 2>/dev/null || true)"'
        in verify_script
    )
    assert (
        'echo "Hosted online compose app URL is not publicly exposed, which matches the Cloud Run primary-path contract."'
        in verify_script
    )
    assert (
        'echo "Hosted runtime verification failed: online compose app URL is public (${online_compose_app_url}). Remove port 8000 from online_compose_public_ports so Cloud Run remains the only public API path." >&2'
        in verify_script
    )
    assert (
        'cloud_run_service_url="$(terraform -chdir=terraform output -raw cloud_run_service_url 2>/dev/null || true)"'
        in verify_script
    )
    assert (
        "cloud_run_allow_unauthenticated=\"$(printf '%s' \"${TF_VAR_cloud_run_allow_unauthenticated}\" | tr '[:upper:]' '[:lower:]')\""
        in verify_script
    )
    assert (
        'gcloud auth print-identity-token --audiences="$cloud_run_service_url"'
        in verify_script
    )
    assert 'echo "Waiting for Cloud Run health at ${health_url}..."' in verify_script
    assert (
        'echo "Checking Cloud Run spots endpoint at ${spots_url}..."' in verify_script
    )
    assert 'metrics_url="${cloud_run_service_url%/}/metrics"' in verify_script
    assert 'echo "Checking Cloud Run metrics at ${metrics_url}..."' in verify_script
    assert '"status"[[:space:]]*:[[:space:]]*"healthy"' in verify_script
    assert '"model_alias"[[:space:]]*:' in verify_script
    assert '"model_version"[[:space:]]*:' in verify_script
    assert '"id"[[:space:]]*:' in verify_script
    assert "foehncast_online_compose_sync_status_file_present" in verify_script
    assert (
        'echo "Cloud Run runtime verification failed: Cloud Run service URL is not available. Fix the Cloud Run configuration instead of skipping hosted runtime verification." >&2'
        in verify_script
    )
    assert (
        'echo "cloud_run_invocation_mode=${cloud_run_invocation_mode}"' in verify_script
    )
    assert (
        'echo "primary_hosted_api_target=${primary_hosted_api_target}"' in verify_script
    )
    assert (
        'echo "primary_hosted_api_verification_status=${primary_hosted_api_verification_status}"'
        in verify_script
    )
    assert '} >> "$GITHUB_OUTPUT"' in verify_script


def test_publish_app_image_stops_at_image_publish_boundary() -> None:
    workflow = _workflow_yaml(".github/workflows/publish-app-image.yml")
    config_job = workflow["jobs"]["config"]

    assert workflow["on"]["workflow_dispatch"] == {}
    assert (
        config_job["outputs"]["project_id"]
        == "${{ steps.repo_config.outputs.project_id }}"
    )
    assert (
        config_job["outputs"]["workload_identity_provider"]
        == "${{ steps.repo_config.outputs.workload_identity_provider }}"
    )
    assert (
        config_job["outputs"]["service_account_email"]
        == "${{ steps.repo_config.outputs.service_account_email }}"
    )
    assert (
        config_job["outputs"]["registry_host"]
        == "${{ steps.derived.outputs.registry_host }}"
    )
    assert (
        config_job["outputs"]["image_repository"]
        == "${{ steps.derived.outputs.image_repository }}"
    )
    assert (
        config_job["outputs"]["publish_ready"]
        == "${{ steps.derived.outputs.publish_ready }}"
    )
    assert "cloud_run_service" not in config_job["outputs"]
    assert "cloud_run_allow_unauthenticated" not in config_job["outputs"]
    assert "deploy_mode" not in config_job["outputs"]
    assert "cloud_run_revision_tag" not in config_job["outputs"]
    assert "serving_alias" not in config_job["outputs"]
    assert "deploy_ready" not in config_job["outputs"]

    derived_step = _workflow_step(workflow, "config", "derived")
    assert "CLOUD_RUN_SERVICE" not in derived_step["env"]
    assert "DEPLOY_MODE_INPUT" not in derived_step["env"]
    assert "CANDIDATE_REVISION_TAG_INPUT" not in derived_step["env"]
    assert "SERVING_ALIAS_INPUT" not in derived_step["env"]
    assert "deploy_ready" not in derived_step["run"]
    assert "deploy_mode" not in derived_step["run"]
    assert "cloud_run_revision_tag" not in derived_step["run"]
    assert "serving_alias" not in derived_step["run"]

    publish_job = workflow["jobs"]["publish"]
    assert (
        publish_job["outputs"]["image_uri"]
        == "${{ steps.image.outputs.immutable_tag }}"
    )

    summary_step = _workflow_step(workflow, "publish", "Summarize published image")
    assert (
        'echo "- Runtime handoff: not executed from GitHub in this workflow"'
        in summary_step["run"]
    )
    assert (
        'echo "- Next step: run Trigger Runtime Release with action deploy_candidate and this immutable image URI"'
        in summary_step["run"]
    )

    assert "deploy" not in workflow["jobs"]
    assert "deploy_skipped" not in workflow["jobs"]

    skipped_step = _workflow_step(workflow, "skipped", "Explain skipped publish")
    assert (
        "This workflow stops at image publication and does not deploy or promote runtime state."
        in skipped_step["run"]
    )
    assert "GCP_CLOUD_RUN_SERVICE" not in skipped_step["run"]


def test_publish_app_image_uses_cloud_build_artifact_registry_contract() -> None:
    workflow = _workflow_yaml(".github/workflows/publish-app-image.yml")
    workflow_text = _read_text(".github/workflows/publish-app-image.yml")
    push_paths = workflow["on"]["push"]["paths"]

    assert workflow["permissions"] == {"contents": "read", "id-token": "write"}
    assert ".github/actions/load-gcp-repo-config/action.yml" in push_paths
    assert "cloudbuild/**" in push_paths

    repo_config_step = _workflow_step(workflow, "config", "repo_config")
    assert repo_config_step["uses"] == "./.github/actions/load-gcp-repo-config"

    auth_step = _workflow_step(workflow, "publish", "Authenticate to Google Cloud")
    assert auth_step["uses"] == "google-github-actions/auth@v2"

    setup_step = _workflow_step(workflow, "publish", "Set up gcloud")
    assert setup_step["uses"] == "google-github-actions/setup-gcloud@v2"
    assert setup_step["with"]["project_id"] == "${{ needs.config.outputs.project_id }}"

    submit_step = _workflow_step(workflow, "publish", "Submit Cloud Build")
    assert "gcloud builds submit ." in submit_step["run"]
    assert "--config cloudbuild/runtime-image.yaml" in submit_step["run"]
    assert '"_BUILD_CONTEXT=${BUILD_CONTEXT}"' in submit_step["run"]
    assert '"_DOCKERFILE=${DOCKERFILE}"' in submit_step["run"]
    assert '"_IMAGE_REPOSITORY=${IMAGE_REPOSITORY}"' in submit_step["run"]
    assert '"_FLOATING_TAG=${LATEST_TAG}"' in submit_step["run"]
    assert "BUILD_CONTEXT: ." in workflow_text
    assert "DOCKERFILE: containers/app/Dockerfile" in workflow_text
    assert "docker/setup-buildx-action" not in workflow_text
    assert "docker/build-push-action" not in workflow_text
    assert "docker/metadata-action" not in workflow_text


def test_trigger_runtime_release_workflow_uses_current_retained_host_handoff_contract() -> (
    None
):
    workflow = _workflow_yaml(".github/workflows/trigger-runtime-release.yml")
    config_job = workflow["jobs"]["config"]
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]

    assert workflow["permissions"] == {"contents": "read", "id-token": "write"}
    assert dispatch_inputs["action"]["default"] == "deploy_candidate"
    assert dispatch_inputs["action"]["type"] == "choice"
    assert dispatch_inputs["action"]["options"] == [
        "deploy_candidate",
        "promote_candidate",
        "rollback_live",
    ]
    assert dispatch_inputs["candidate_revision_tag"]["default"] == "candidate"
    assert dispatch_inputs["candidate_alias"]["default"] == "candidate"
    assert dispatch_inputs["target_alias"]["default"] == "champion"
    assert dispatch_inputs["rollback_revision_tag"]["default"] == "rollback"

    assert set(config_job["outputs"]) == {
        "owner_allowed",
        "project_id",
        "workload_identity_provider",
        "service_account_email",
        "online_compose_host_name",
        "online_compose_host_zone",
        "action",
        "image_uri",
        "candidate_revision_tag",
        "candidate_alias",
        "target_alias",
        "rollback_revision",
        "rollback_model_version",
        "rollback_revision_tag",
        "trigger_ready",
    }

    repo_config_step = _workflow_step(workflow, "config", "repo_config")
    assert repo_config_step["uses"] == "./.github/actions/load-gcp-repo-config"

    derived_step = _workflow_step(workflow, "config", "derived")
    assert derived_step["env"]["ACTION_INPUT"] == "${{ github.event.inputs.action }}"
    assert (
        derived_step["env"]["PROVISION_ONLINE_COMPOSE_HOST"]
        == "${{ steps.repo_config.outputs.provision_online_compose_host }}"
    )
    assert "deploy_candidate|promote_candidate|rollback_live" in derived_step["run"]
    assert "trigger_ready=false" in derived_step["run"]
    assert 'echo "trigger_ready=$trigger_ready"' in derived_step["run"]

    trigger_job = workflow["jobs"]["trigger"]
    assert (
        trigger_job["if"]
        == "${{ needs.config.outputs.owner_allowed == 'true' && needs.config.outputs.trigger_ready == 'true' }}"
    )
    assert (
        trigger_job["env"]["HOST_NAME"]
        == "${{ needs.config.outputs.online_compose_host_name }}"
    )
    assert (
        trigger_job["env"]["HOST_ZONE"]
        == "${{ needs.config.outputs.online_compose_host_zone }}"
    )

    payload_step = _workflow_step(workflow, "trigger", "Build runtime release request")
    assert "runtime-release-request.json" in payload_step["run"]
    assert "github_run_url" in payload_step["run"]

    refresh_step = _workflow_step(workflow, "trigger", "Refresh operator host checkout")
    assert "gcloud compute ssh" in refresh_step["run"]
    assert "foehncast-online-compose-sync.service" in refresh_step["run"]
    assert "--wait" in refresh_step["run"]

    copy_step = _workflow_step(workflow, "trigger", "Copy runtime release request")
    assert "gcloud compute scp" in copy_step["run"]
    assert "/tmp/runtime-release-request.json" in copy_step["run"]

    handoff_step = _workflow_step(
        workflow, "trigger", "Trigger runtime release handoff"
    )
    assert (
        "./scripts/trigger-runtime-release.sh --request-file /tmp/runtime-release-request.json"
        in handoff_step["run"]
    )
    assert 'echo "- Airflow DAG: runtime_release"' in handoff_step["run"]
    assert (
        'echo "- Current receiver: retained-host Airflow adapter"'
        in handoff_step["run"]
    )
    assert (
        'echo "- Target receiver: Cloud Composer without VM SSH"' in handoff_step["run"]
    )
    assert 'echo "## Runtime release handoff"' in handoff_step["run"]

    skipped_step = _workflow_step(
        workflow, "skipped", "Explain skipped runtime release handoff"
    )
    assert "This is the current retained-host entry contract." in skipped_step["run"]
    assert "Cloud Composer without VM SSH" in skipped_step["run"]


def test_orchestration_docs_describe_current_host_path_and_target_composer_readiness() -> (
    None
):
    workflow_doc = _read_text("docs/site/system/delivery-and-operator-workflow.md")
    cloud_mapping = _read_text("docs/site/system/cloud-mapping.md")
    terraform_readme = _read_text("terraform/README.md")

    assert (
        "The current hosted orchestration path and the target managed direction are different on purpose."
        in workflow_doc
    )
    assert (
        "| Hosted Airflow surface | retained operator host | Cloud Composer |"
        in workflow_doc
    )
    assert "reviewed request should reach Composer without VM SSH" in workflow_doc
    assert (
        "a reviewed DAG delivery path that does not depend on a VM checkout"
        in workflow_doc
    )
    assert (
        "a managed secret and runtime-config path for hosted orchestration"
        in workflow_doc
    )
    assert (
        "The target managed direction is the same reviewed request reaching Composer without a retained-host refresh step."
        in workflow_doc
    )
    assert (
        "Terraform can provision the managed surface ahead of that cutover"
        in workflow_doc
    )

    assert (
        "Cloud Composer is the target managed orchestration direction, and Terraform can now provision a Cloud Composer environment for readiness work."
        in cloud_mapping
    )
    assert (
        "a reviewed runtime release entry that reaches the managed Airflow surface directly"
        in cloud_mapping
    )
    assert (
        "The retained host remains the active orchestration authority until those boundaries move."
        in cloud_mapping
    )

    assert (
        "Terraform can provision an optional Cloud Composer environment today."
        in terraform_readme
    )
    assert "reviewed runtime release entry without VM SSH" in terraform_readme
    assert "GCP_PROVISION_CLOUD_COMPOSER_ENVIRONMENT" in terraform_readme


def test_promote_candidate_workflow_redirects_to_runtime_trigger_contract() -> None:
    workflow = _workflow_yaml(".github/workflows/promote-candidate.yml")
    config_job = workflow["jobs"]["config"]
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    config_steps = {
        step.get("id") or step.get("name")
        for step in workflow["jobs"]["config"]["steps"]
    }

    assert workflow["permissions"] == {"contents": "read"}
    assert dispatch_inputs["candidate_revision_tag"]["default"] == "candidate"
    assert dispatch_inputs["candidate_alias"]["default"] == "candidate"
    assert dispatch_inputs["target_alias"]["default"] == "champion"

    assert set(config_job["outputs"]) == {
        "owner_allowed",
        "candidate_revision_tag",
        "candidate_alias",
        "target_alias",
    }
    assert "repo_config" not in config_steps

    derived_step = _workflow_step(workflow, "config", "derived")
    assert (
        derived_step["env"]["CANDIDATE_REVISION_TAG_INPUT"]
        == "${{ github.event.inputs.candidate_revision_tag }}"
    )
    assert (
        derived_step["env"]["CANDIDATE_ALIAS_INPUT"]
        == "${{ github.event.inputs.candidate_alias }}"
    )
    assert (
        derived_step["env"]["TARGET_ALIAS_INPUT"]
        == "${{ github.event.inputs.target_alias }}"
    )
    assert "candidate_revision_tag='candidate'" in derived_step["run"]
    assert "candidate_alias='candidate'" in derived_step["run"]
    assert "target_alias='champion'" in derived_step["run"]
    assert "promote_ready" not in derived_step["run"]

    assert "promote" not in workflow["jobs"]

    blocked_job = workflow["jobs"]["blocked"]
    assert "environment" not in blocked_job
    assert (
        blocked_job["env"]["CANDIDATE_REVISION_TAG"]
        == "${{ needs.config.outputs.candidate_revision_tag }}"
    )
    assert (
        blocked_job["env"]["CANDIDATE_ALIAS"]
        == "${{ needs.config.outputs.candidate_alias }}"
    )
    assert (
        blocked_job["env"]["TARGET_ALIAS"] == "${{ needs.config.outputs.target_alias }}"
    )

    blocked_step = _workflow_step(
        workflow, "blocked", "Explain blocked promotion workflow"
    )
    assert (
        "Candidate promotion moved behind Trigger Runtime Release"
        in blocked_step["run"]
    )
    assert (
        "Candidate promotion is no longer executed directly from GitHub Actions."
        in blocked_step["run"]
    )
    assert (
        "Use Trigger Runtime Release with action promote_candidate"
        in blocked_step["run"]
    )


def test_rollback_live_release_workflow_redirects_to_runtime_trigger_contract() -> None:
    workflow = _workflow_yaml(".github/workflows/rollback-live-release.yml")
    config_job = workflow["jobs"]["config"]
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    config_steps = {
        step.get("id") or step.get("name")
        for step in workflow["jobs"]["config"]["steps"]
    }

    assert workflow["permissions"] == {"contents": "read"}
    assert dispatch_inputs["rollback_revision"]["required"] is True
    assert dispatch_inputs["rollback_model_version"]["required"] is True
    assert dispatch_inputs["rollback_revision_tag"]["default"] == "rollback"
    assert dispatch_inputs["target_alias"]["default"] == "champion"

    assert set(config_job["outputs"]) == {
        "owner_allowed",
        "rollback_revision",
        "rollback_model_version",
        "rollback_revision_tag",
        "target_alias",
    }
    assert "repo_config" not in config_steps

    derived_step = _workflow_step(workflow, "config", "derived")
    assert (
        derived_step["env"]["ROLLBACK_REVISION_INPUT"]
        == "${{ github.event.inputs.rollback_revision }}"
    )
    assert (
        derived_step["env"]["ROLLBACK_MODEL_VERSION_INPUT"]
        == "${{ github.event.inputs.rollback_model_version }}"
    )
    assert (
        derived_step["env"]["ROLLBACK_REVISION_TAG_INPUT"]
        == "${{ github.event.inputs.rollback_revision_tag }}"
    )
    assert (
        derived_step["env"]["TARGET_ALIAS_INPUT"]
        == "${{ github.event.inputs.target_alias }}"
    )
    assert 'echo "rollback_revision=$rollback_revision"' in derived_step["run"]
    assert (
        'echo "rollback_model_version=$rollback_model_version"' in derived_step["run"]
    )
    assert "rollback_revision_tag='rollback'" in derived_step["run"]
    assert "target_alias='champion'" in derived_step["run"]
    assert "rollback_ready" not in derived_step["run"]

    assert "rollback" not in workflow["jobs"]

    blocked_job = workflow["jobs"]["blocked"]
    assert "environment" not in blocked_job
    assert (
        blocked_job["env"]["ROLLBACK_REVISION"]
        == "${{ needs.config.outputs.rollback_revision }}"
    )
    assert (
        blocked_job["env"]["ROLLBACK_MODEL_VERSION"]
        == "${{ needs.config.outputs.rollback_model_version }}"
    )
    assert (
        blocked_job["env"]["ROLLBACK_REVISION_TAG"]
        == "${{ needs.config.outputs.rollback_revision_tag }}"
    )
    assert (
        blocked_job["env"]["TARGET_ALIAS"] == "${{ needs.config.outputs.target_alias }}"
    )

    blocked_step = _workflow_step(
        workflow, "blocked", "Explain blocked rollback workflow"
    )
    assert "Live rollback moved behind Trigger Runtime Release" in blocked_step["run"]
    assert (
        "Live rollback is no longer executed directly from GitHub Actions."
        in blocked_step["run"]
    )
    assert (
        "Use Trigger Runtime Release with action rollback_live" in blocked_step["run"]
    )


def test_trigger_runtime_release_script_uses_local_airflow_contract() -> None:
    script = _read_text("scripts/trigger-runtime-release.sh")
    cli_common = _read_text("scripts/cli-common.sh")
    helper = _read_text("scripts/airflow-api-common.sh")

    assert "require_cli_option_value()" in cli_common
    assert "Usage: $0 --request-file path" in script
    assert 'AIRFLOW_API_BASE_URL="http://127.0.0.1:8080/api/v2"' in script
    assert 'source "${ROOT_DIR}/scripts/cli-common.sh"' in script
    assert 'source "${ROOT_DIR}/scripts/airflow-api-common.sh"' in script
    assert "${AIRFLOW_API_BASE_URL}/monitor/health" in script
    assert "python3 -m foehncast.airflow_api" in helper
    assert (
        "${airflow_api_base_url}/dags/${dag_id}/dagRuns?limit=20&order_by=-start_date"
        in helper
    )
    assert "run_airflow_api_helper" in script
    assert "airflow_api_verify_health \\" in script
    assert "airflow_api_wait_for_dag_run_state \\" in script
    assert "python3 -m foehncast.runtime_release" in script
    assert "run_runtime_release_helper" in script
    assert 'PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"' in helper
    assert "normalize-request" in script
    assert (
        'REQUEST_FILE="$(require_cli_option_value "--request-file" "${1:-}" usage)"'
        in script
    )
    assert 'airflow dags trigger "$DAG_ID"' in script
    assert (
        'wait_for_airflow_dag_run_state "$DAG_ID" "$dag_run_id" success 120 2' in script
    )
    assert "runtime-release-latest.json" in script
    assert "verify-report" in script


def test_publish_runtime_images_excludes_local_only_development_env() -> None:
    workflow = _workflow_yaml(".github/workflows/publish-runtime-images.yml")
    push_paths = workflow["on"]["push"]["paths"]
    image_targets = workflow["jobs"]["publish"]["strategy"]["matrix"]["include"]

    assert "containers/development_env/**" not in push_paths
    assert "containers/app/**" not in push_paths
    assert ".github/actions/load-gcp-repo-config/action.yml" in push_paths
    assert "cloudbuild/**" in push_paths
    assert {target["image_name"] for target in image_targets} == {
        "foehncast-airflow",
        "foehncast-mlflow",
    }


def test_publish_runtime_images_uses_cloud_build_artifact_registry_contract() -> None:
    workflow = _workflow_yaml(".github/workflows/publish-runtime-images.yml")
    workflow_text = _read_text(".github/workflows/publish-runtime-images.yml")
    config_job = workflow["jobs"]["config"]

    assert workflow["permissions"] == {"contents": "read", "id-token": "write"}
    assert (
        config_job["outputs"]["project_id"]
        == "${{ steps.repo_config.outputs.project_id }}"
    )
    assert (
        config_job["outputs"]["image_repository_base"]
        == "${{ steps.derived.outputs.image_repository_base }}"
    )

    repo_config_step = _workflow_step(workflow, "config", "repo_config")
    assert repo_config_step["uses"] == "./.github/actions/load-gcp-repo-config"

    auth_step = _workflow_step(workflow, "publish", "Authenticate to Google Cloud")
    assert auth_step["uses"] == "google-github-actions/auth@v2"

    setup_step = _workflow_step(workflow, "publish", "Set up gcloud")
    assert setup_step["uses"] == "google-github-actions/setup-gcloud@v2"
    assert setup_step["with"]["project_id"] == "${{ needs.config.outputs.project_id }}"

    submit_step = _workflow_step(workflow, "publish", "Submit Cloud Build")
    assert "gcloud builds submit ." in submit_step["run"]
    assert "--config cloudbuild/runtime-image.yaml" in submit_step["run"]
    assert '"_BUILD_CONTEXT=${BUILD_CONTEXT}"' in submit_step["run"]
    assert '"_DOCKERFILE=${DOCKERFILE}"' in submit_step["run"]
    assert '"_IMAGE_REPOSITORY=${IMAGE_REPOSITORY}"' in submit_step["run"]
    assert '"_FLOATING_TAG=${LATEST_TAG}"' in submit_step["run"]
    assert "ghcr.io" not in workflow_text
    assert "docker/login-action" not in workflow_text
    assert "docker/build-push-action" not in workflow_text
    assert "docker/metadata-action" not in workflow_text


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

    for key in FEAST_CLOUD_ENV_KEYS:
        assert f"printf '{key}\\t%s\\n'" in body


def test_terraform_injects_feast_runtime_contract_into_both_hosted_targets() -> None:
    terraform = _read_text("terraform/main.tf")
    cloud_run_block = re.search(
        r"cloud_run_env_vars = merge\(\n\s*\{\n(?P<body>.*?)\n\s*\},\n\s*var\.cloud_run_env_vars",
        terraform,
        flags=re.DOTALL,
    )
    online_compose_block = re.search(
        r"online_compose_env_vars = merge\(\n\s*\{\n(?P<body>.*?)\n\s*\},\n\s*var\.online_compose_env_vars",
        terraform,
        flags=re.DOTALL,
    )

    assert cloud_run_block is not None
    assert online_compose_block is not None

    for key in FEAST_CLOUD_ENV_KEYS:
        assert key in cloud_run_block.group("body")
        assert key in online_compose_block.group("body")


def test_terraform_grants_hosted_runtime_identities_bigquery_storage_and_bucket_access() -> (
    None
):
    terraform = _read_text("terraform/main.tf")

    assert (
        'resource "google_project_iam_member" "cloud_run_bigquery_read_session_user"'
        in terraform
    )
    assert (
        'resource "google_project_iam_member" "online_compose_bigquery_read_session_user"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "online_compose_bucket_admin"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "cloud_run_bucket_metadata_reader"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "online_compose_bucket_metadata_reader"'
        in terraform
    )
    assert 'role    = "roles/bigquery.readSessionUser"' in terraform
    assert 'role   = "roles/storage.objectAdmin"' in terraform
    assert 'role   = "roles/storage.legacyBucketReader"' in terraform
    assert (
        "google_project_iam_member.cloud_run_bigquery_read_session_user," in terraform
    )
    assert (
        "google_project_iam_member.online_compose_bigquery_read_session_user,"
        in terraform
    )
    assert "google_storage_bucket_iam_member.online_compose_bucket_admin," in terraform
    assert (
        "google_storage_bucket_iam_member.cloud_run_bucket_metadata_reader,"
        in terraform
    )
    assert (
        "google_storage_bucket_iam_member.online_compose_bucket_metadata_reader,"
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
    assert (
        'online_compose_app_image = var.online_compose_app_image != "" ? var.online_compose_app_image : "${local.artifact_registry_repository_path}/foehncast-app:latest"'
        in terraform_single_spaced
    )
    assert (
        'online_compose_airflow_image = var.online_compose_airflow_image != "" ? var.online_compose_airflow_image : "${local.artifact_registry_repository_path}/foehncast-airflow:latest"'
        in terraform_single_spaced
    )
    assert (
        'online_compose_mlflow_image = var.online_compose_mlflow_image != "" ? var.online_compose_mlflow_image : "${local.artifact_registry_repository_path}/foehncast-mlflow:latest"'
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
    assert (
        'resource "google_artifact_registry_repository_iam_member" "online_compose_reader"'
        in terraform
    )
    assert (
        "google_artifact_registry_repository_iam_member.online_compose_reader,"
        in terraform
    )
    assert "default Artifact Registry image" in variables
    assert "default GHCR image" not in variables


def test_terraform_defines_cloud_composer_hosted_orchestration_contract() -> None:
    terraform = _read_text("terraform/main.tf")
    variables = _read_text("terraform/variables.tf")
    outputs = _read_text("terraform/outputs.tf")

    assert '"composer.googleapis.com",' in terraform
    assert '"container.googleapis.com",' in terraform
    assert '"sqladmin.googleapis.com",' in terraform
    assert '"roles/composer.admin",' in terraform
    assert 'variable "provision_cloud_composer_environment"' in variables
    assert 'variable "cloud_composer_environment_name"' in variables
    assert 'variable "cloud_composer_image_version"' in variables
    assert 'resource "google_service_account" "cloud_composer_runtime"' in terraform
    assert 'resource "google_project_iam_member" "cloud_composer_worker"' in terraform
    assert 'role    = "roles/composer.worker"' in terraform
    assert (
        'resource "google_service_account_iam_member" "cloud_composer_service_agent_extension"'
        in terraform
    )
    assert 'role               = "roles/composer.ServiceAgentV2Ext"' in terraform
    assert 'resource "google_compute_network" "cloud_composer"' in terraform
    assert 'resource "google_compute_subnetwork" "cloud_composer"' in terraform
    assert 'resource "google_composer_environment" "cloud_composer"' in terraform
    assert "env_variables = local.cloud_composer_env_vars" in terraform
    assert (
        "service_account = google_service_account.cloud_composer_runtime[0].name"
        in terraform
    )
    assert 'output "provision_cloud_composer_environment"' in outputs
    assert 'output "cloud_composer_environment_name"' in outputs
    assert 'output "cloud_composer_airflow_uri"' in outputs
    assert 'output "cloud_composer_dag_gcs_prefix"' in outputs


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
    assert 'output "online_compose_runtime_service_account"' in outputs
    assert 'output "cloud_composer_runtime_service_account"' in outputs
    assert (
        'value       = var.provision_online_compose_host ? try(google_service_account.online_compose_runtime[0].email, "foehncast-online-compose@${var.project_id}.iam.gserviceaccount.com") : null'
        in outputs
    )
    assert (
        'value       = var.provision_cloud_composer_environment ? try(google_service_account.cloud_composer_runtime[0].email, "foehncast-composer@${var.project_id}.iam.gserviceaccount.com") : null'
        in outputs
    )


def test_platform_state_tracks_hosted_runtime_identities_without_repo_var_sync() -> (
    None
):
    load_body = _function_body(
        "scripts/terraform-platform-state.sh", "load_terraform_platform_state"
    )
    names_body = _function_body(
        "scripts/terraform-platform-state.sh", "terraform_repo_variable_names"
    )
    pairs_body = _function_body(
        "scripts/terraform-platform-state.sh", "terraform_repo_variable_pairs"
    )

    assert (
        'FOEHNCAST_TF_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT="$(optional_terraform_output_value "$terraform_dir" online_compose_runtime_service_account)"'
        in load_body
    )
    assert (
        'FOEHNCAST_TF_CLOUD_COMPOSER_RUNTIME_SERVICE_ACCOUNT="$(optional_terraform_output_value "$terraform_dir" cloud_composer_runtime_service_account)"'
        in load_body
    )
    assert "GCP_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT" not in names_body
    assert "GCP_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT" not in pairs_body
    assert "GCP_CLOUD_COMPOSER_RUNTIME_SERVICE_ACCOUNT" not in names_body
    assert "GCP_CLOUD_COMPOSER_RUNTIME_SERVICE_ACCOUNT" not in pairs_body


def test_online_compose_startup_template_prepares_writable_runtime_dirs() -> None:
    template = _read_text("terraform/templates/online-compose-host.sh.tftpl")

    assert "airflow_uid=50000" in template
    assert "app_uid=1000" in template
    assert "grafana_uid=472" in template
    assert (
        "install -d -m 0775 /opt/foehncast/airflow /opt/foehncast/airflow/logs /opt/foehncast/airflow/reports"
        in template
    )
    assert (
        "install -d -m 0755 /opt/foehncast/.state /opt/foehncast/.state/airflow /opt/foehncast/.state/feast /opt/foehncast/.state/online-compose-sync"
        in template
    )
    assert "install -d -m 0775 /opt/foehncast/data/feast" in template
    assert "install -d -m 0755 /opt/foehncast/grafana_work/data" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/airflow" in template
    assert "chown -R $${app_uid}:$${app_uid} /opt/foehncast/.state" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/.state/airflow" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/.state/feast" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/data/feast" in template
    assert (
        "chown -R $${grafana_uid}:$${grafana_uid} /opt/foehncast/grafana_work/data"
        in template
    )
    assert "chown $${airflow_uid}:0 /opt/foehncast/airflow/.admin-password" in template
    assert "cat > /usr/local/bin/foehncast-online-compose-sync <<'EOF'" in template
    assert "chmod 0755 /usr/local/bin/foehncast-online-compose-sync" in template
    assert "systemctl enable --now foehncast-online-compose-sync.timer" in template
    assert "systemctl start foehncast-online-compose-sync.service" in template


def test_online_compose_startup_template_prepares_writable_runtime_directories() -> (
    None
):
    template = _read_text("terraform/templates/online-compose-host.sh.tftpl")

    assert "airflow_uid=50000" in template
    assert "app_uid=1000" in template
    assert "grafana_uid=472" in template
    assert (
        "install -d -m 0775 /opt/foehncast/airflow /opt/foehncast/airflow/logs /opt/foehncast/airflow/reports"
        in template
    )
    assert (
        "install -d -m 0755 /opt/foehncast/.state /opt/foehncast/.state/airflow /opt/foehncast/.state/feast /opt/foehncast/.state/online-compose-sync"
        in template
    )
    assert "install -d -m 0775 /opt/foehncast/data/feast" in template
    assert "install -d -m 0755 /opt/foehncast/grafana_work/data" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/airflow" in template
    assert "chown -R $${app_uid}:$${app_uid} /opt/foehncast/.state" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/.state/airflow" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/.state/feast" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/data/feast" in template
    assert (
        "chown -R $${grafana_uid}:$${grafana_uid} /opt/foehncast/grafana_work/data"
        in template
    )
    assert "chown $${airflow_uid}:0 /opt/foehncast/airflow/.admin-password" in template
    assert "chmod 600 /opt/foehncast/airflow/.admin-password" in template


def test_online_compose_startup_template_installs_periodic_repo_sync_timer() -> None:
    template = _read_text("terraform/templates/online-compose-host.sh.tftpl")

    assert 'git -C /opt/foehncast fetch --depth 1 origin "${git_ref}"' in template
    assert "git -C /opt/foehncast checkout --force FETCH_HEAD" in template
    assert (
        "cat > /etc/systemd/system/foehncast-online-compose-sync.service <<'EOF'"
        in template
    )
    assert "ExecStart=/usr/local/bin/foehncast-online-compose-sync" in template
    assert (
        "cat > /etc/systemd/system/foehncast-online-compose-sync.timer <<'EOF'"
        in template
    )
    assert "OnBootSec=2m" in template
    assert "OnUnitActiveSec=5m" in template
    assert "Persistent=true" in template
    assert "compose_args=(" in template
    assert "-f /opt/foehncast/docker-compose.yml" in template
    assert "-f /opt/foehncast/docker-compose.cloud.yml" in template
    assert "--env-file /opt/foehncast/.env" in template
    assert (
        'docker compose "$${compose_args[@]}" pull model-registry app airflow-init airflow-webserver airflow-dag-processor airflow-scheduler airflow-triggerer'
        in template
    )
    assert (
        "docker compose -f /opt/foehncast/docker-compose.yml -f /opt/foehncast/docker-compose.cloud.yml --env-file /opt/foehncast/.env up -d --no-build"
        in template
    )
    assert "--build" not in template


def test_online_compose_startup_template_configures_artifact_registry_auth() -> None:
    template = _read_text("terraform/templates/online-compose-host.sh.tftpl")

    assert "packages.cloud.google.com/apt/doc/apt-key.gpg" in template
    assert "google-cloud-cli" in template
    assert (
        'gcloud auth configure-docker "${artifact_registry_host}" --quiet >/dev/null 2>&1'
        in template
    )


def test_online_compose_startup_template_configures_docker_log_rotation() -> None:
    template = _read_text("terraform/templates/online-compose-host.sh.tftpl")

    assert template.index("journalctl --vacuum-size=100M") < template.index(
        "apt-get update"
    )
    assert "install -d -m 0755 /etc/docker" in template
    assert "cat > /etc/docker/daemon.json <<'EOF'" in template
    assert '"log-driver": "json-file"' in template
    assert '"max-size": "10m"' in template
    assert '"max-file": "3"' in template
    assert "journalctl --vacuum-size=100M" in template
    assert (
        r"find /var/lib/docker/containers -name '*-json.log' -type f -size +50M -exec truncate -s 0 {} \;"
        in template
    )
    assert "systemctl restart docker" in template


def test_online_compose_sync_template_repairs_serving_surface_when_cold() -> None:
    template = _read_text("terraform/templates/online-compose-host.sh.tftpl")

    assert (
        'feature_logical_date="$${FEATURE_LOGICAL_DATE:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}"'
        in template
    )
    assert (
        'feature_run_id="$${FEATURE_RUN_ID:-hosted_sync__$(date -u +"%Y-%m-%dT%H-%M-%SZ")}"'
        in template
    )
    assert (
        'airflow_health_url="http://127.0.0.1:8080/api/v2/monitor/health"' in template
    )
    assert 'app_health_url="http://127.0.0.1:8000/health"' in template
    assert 'online_features_url="http://127.0.0.1:8000/features/online"' in template
    assert "verify_airflow_api_health() {" in template
    assert "wait_for_airflow_dag_run_state() {" in template
    assert "serving_surface_ready() {" in template
    assert "bootstrap_serving_surface() {" in template
    assert "verify_serving_surface() {" in template
    assert (
        "airflow dags trigger feature_pipeline \\\n"
        '    --logical-date "$${feature_logical_date}" \\\n'
        '    --run-id "$${feature_run_id}" >/dev/null' in template
    )
    assert (
        'curl --retry 1 --retry-all-errors --retry-delay 0 -fsS -X POST -H "Content-Type: application/json" -d \'{}\' "$${online_features_url}" >/dev/null 2>&1'
        in template
    )
    assert (
        'curl --retry 30 --retry-all-errors --retry-delay 2 -fsS -X POST -H "Content-Type: application/json" -d \'{}\' "$${online_features_url}" >/dev/null'
        in template
    )
    assert (
        "wait_for_airflow_dag_run_state feature_pipeline success manual 120 2"
        in template
    )
    assert (
        "wait_for_airflow_dag_run_state training_pipeline success asset_triggered 120 2"
        in template
    )
    assert (
        'echo "Hosted runtime not ready; triggering feature and training convergence."'
        in template
    )
    assert 'echo "Waiting for hosted feature pipeline..."' in template
    assert "if ! serving_surface_ready; then" in template
    assert 'echo "Checking hosted online features..."' in template


def test_online_compose_sync_template_records_last_success_status_file() -> None:
    template = _read_text("terraform/templates/online-compose-host.sh.tftpl")

    assert (
        "cat > /opt/foehncast/.state/online-compose-sync/last-success.json <<'EOF'"
        in template
    )
    assert '"state": "pending"' in template
    assert (
        'sync_status_file="/opt/foehncast/.state/online-compose-sync/last-success.json"'
        in template
    )
    assert 'sync_timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"' in template
    assert 'sync_commit="$(git -C /opt/foehncast rev-parse HEAD)"' in template
    assert 'cat > "$${sync_status_file}.tmp" <<STATUS' in template
    assert 'mv "$${sync_status_file}.tmp" "$${sync_status_file}"' in template
    assert 'chmod 0644 "$${sync_status_file}"' in template
    assert '"last_successful_sync_at": "$${sync_timestamp}"' in template
    assert '"last_successful_commit": "$${sync_commit}"' in template
    assert '"compose_deploy_mode": "$${compose_deploy_mode}"' in template
    assert 'compose_deploy_mode="pull"' in template


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
        'resource "google_project_iam_member" "online_compose_bigquery_read_session_user"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "online_compose_bucket_admin"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "cloud_run_bucket_metadata_reader"'
        in terraform
    )
    assert (
        'resource "google_storage_bucket_iam_member" "online_compose_bucket_metadata_reader"'
        in terraform
    )


def test_terraform_grants_github_deployer_firestore_admin() -> None:
    terraform = _read_text("terraform/main.tf")

    assert 'resource "google_project_iam_member" "github_project_admin"' in terraform
    assert '"roles/datastore.owner"' in terraform
    assert 'role   = "roles/storage.objectAdmin"' in terraform
    assert "google_project_iam_member.cloud_run_bigquery_read_session_user" in terraform
    assert (
        "google_project_iam_member.online_compose_bigquery_read_session_user"
        in terraform
    )
    assert "google_storage_bucket_iam_member.online_compose_bucket_admin" in terraform
    assert (
        "google_storage_bucket_iam_member.online_compose_bucket_metadata_reader"
        in terraform
    )


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


def test_bootstrap_gcp_reports_online_compose_urls_when_hosted_vm_is_enabled() -> None:
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")
    state_helper = _read_text("scripts/terraform-platform-state.sh")

    assert "print_online_compose_summary()" in bootstrap
    assert "trimmed_terraform_output_value()" in state_helper
    assert "terraform_platform_value_present()" in state_helper
    assert "print_terraform_summary_line_if_present()" in state_helper
    assert "print_trimmed_terraform_output_summary()" in state_helper
    assert (
        'print_trimmed_terraform_output_summary "$TERRAFORM_DIR" "Online compose host IP" online_compose_host_ip'
        in bootstrap
    )
    assert (
        'print_trimmed_terraform_output_summary "$TERRAFORM_DIR" "Online compose app URL" online_compose_app_url'
        in bootstrap
    )
    assert (
        'print_trimmed_terraform_output_summary "$TERRAFORM_DIR" "Online compose Airflow URL" online_compose_airflow_url'
        in bootstrap
    )
    assert (
        'print_trimmed_terraform_output_summary "$TERRAFORM_DIR" "Online compose MLflow URL" online_compose_mlflow_url'
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
    assert "online_compose_is_enabled()" in bootstrap
    assert (
        'echo "Cloud Run runtime service account: ${FOEHNCAST_TF_RUNTIME_SERVICE_ACCOUNT}"'
        in bootstrap
    )
    assert "print_bootstrap_identity_summary" in bootstrap
    assert (
        'print_terraform_summary_line_if_present "Online compose runtime service account" "$FOEHNCAST_TF_ONLINE_COMPOSE_RUNTIME_SERVICE_ACCOUNT"'
        in bootstrap
    )
    assert "if online_compose_is_enabled; then" in bootstrap
    assert (
        'echo "GitHub deployer service account: ${FOEHNCAST_TF_SERVICE_ACCOUNT_EMAIL}"'
        in bootstrap
    )


def test_bootstrap_gcp_verifies_hosted_app_health_and_sync_metrics_after_apply() -> (
    None
):
    bootstrap = _read_text("scripts/bootstrap-gcp.sh")

    assert "verify_online_compose_runtime()" in bootstrap
    assert (
        'echo "Hosted online compose app URL is not publicly exposed, which matches the Cloud Run primary-path contract."'
        in bootstrap
    )
    assert (
        'echo "Hosted online compose app URL is public (${app_url}), but this configuration requires Cloud Run to remain the only public API path." >&2'
        in bootstrap
    )
    assert bootstrap.index("print_feast_runtime_summary") < bootstrap.rindex(
        "verify_online_compose_runtime"
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
    assert "foehncast_online_compose_sync_status_file_present" in bootstrap
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
    assert "foehncast_default_online_compose_host_name()" in state_helper
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
    assert (
        "Provision the full online compose host now? This keeps the hosted Airflow, MLflow, and retained operator stack on one VM."
        in bootstrap
    )
    assert (
        'provision_online_compose_host_default="$(tfvars_yes_no_default provision_online_compose_host)"'
        in bootstrap
    )
    assert 'replace_or_append_line "$TFVARS_FILE"' in bootstrap
    assert "online_compose_public_ports = []" in bootstrap


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
        'require_any_env_value "Set GCP_BUCKET_NAME, FOEHNCAST_FEAST_GCS_BUCKET, or FOEHNCAST_FEAST_REGISTRY in .env or the environment." \\'
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
        'payload_check_require_pattern "Grafana provisioning check failed"'
        in local_bootstrap
    )
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
