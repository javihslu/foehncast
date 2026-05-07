"""Regression tests for the cloud operator contract surfaces."""

from __future__ import annotations

from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

REPO_VARIABLE_OUTPUTS: list[tuple[str, str]] = [
    ("GCP_PROJECT_ID", "project_id"),
    ("GCP_LOCATION", "location"),
    ("GCP_ARTIFACT_REPOSITORY", "artifact_repository"),
    ("GCP_ARTIFACT_BUCKET_NAME", "artifact_bucket_name"),
    ("GCP_BIGQUERY_DATASET", "bigquery_dataset"),
    ("GCP_BIGQUERY_LOCATION", "bigquery_location"),
    ("GCP_BIGQUERY_TABLE", "bigquery_table"),
    ("GCP_WORKLOAD_IDENTITY_PROVIDER", "workload_identity_provider"),
    ("GCP_SERVICE_ACCOUNT_EMAIL", "service_account_email"),
    ("GCP_TERRAFORM_STATE_BUCKET", "state_bucket"),
    ("GCP_TERRAFORM_STATE_PREFIX", "state_prefix"),
    ("GCP_PROVISION_CLOUD_RUN_SERVICE", "provision_cloud_run_service"),
    ("GCP_CLOUD_RUN_SERVICE_NAME", "cloud_run_service_name"),
    ("GCP_MLFLOW_TRACKING_URI", "mlflow_tracking_uri"),
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
    ("REPO_GCP_PROVISION_CLOUD_RUN_SERVICE", "provision_cloud_run_service"),
    ("REPO_GCP_CLOUD_RUN_SERVICE_NAME", "cloud_run_service_name"),
    ("REPO_GCP_MLFLOW_TRACKING_URI", "mlflow_tracking_uri"),
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
    "provision_cloud_run_service",
    "mlflow_tracking_uri",
    "cloud_run_service_name",
    "provision_online_compose_host",
    "online_compose_host_name",
    "online_compose_host_zone",
    "online_compose_machine_type",
    "online_compose_disk_size_gb",
}


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def _read_yaml(relative_path: str) -> dict:
    return yaml.safe_load(_read_text(relative_path))


def _workflow_yaml(relative_path: str) -> dict:
    workflow = _read_yaml(relative_path)
    if True in workflow and "on" not in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


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

    for input_name in REPO_BACKED_WORKFLOW_INPUTS:
        assert input_name in inputs
        assert "default" not in inputs[input_name]

    assert inputs["provision_cloud_run_service"]["type"] == "string"
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


def test_publish_app_image_uses_provisioned_cloud_run_service_for_deploys() -> None:
    workflow = _workflow_yaml(".github/workflows/publish-app-image.yml")
    config_job = workflow["jobs"]["config"]

    assert (
        config_job["outputs"]["cloud_run_service"]
        == "${{ steps.repo_config.outputs.cloud_run_service }}"
    )

    derived_step = _workflow_step(workflow, "config", "derived")
    assert (
        derived_step["env"]["CLOUD_RUN_SERVICE"]
        == "${{ steps.repo_config.outputs.cloud_run_service }}"
    )
    assert '-n "$CLOUD_RUN_SERVICE"' in derived_step["run"]

    deploy_job = workflow["jobs"]["deploy"]
    assert (
        deploy_job["env"]["CLOUD_RUN_SERVICE"]
        == "${{ needs.config.outputs.cloud_run_service }}"
    )


def test_publish_runtime_images_excludes_local_only_development_env() -> None:
    workflow = _workflow_yaml(".github/workflows/publish-runtime-images.yml")
    push_paths = workflow["on"]["push"]["paths"]
    image_targets = workflow["jobs"]["publish"]["strategy"]["matrix"]["include"]

    assert "containers/development_env/**" not in push_paths
    assert {target["image_name"] for target in image_targets} == {
        "foehncast-app",
        "foehncast-airflow",
        "foehncast-mlflow",
    }


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
    assert "hashicorp/terraform:" not in cli_common

    assert "require_command terraform" not in bootstrap
    assert 'run_terraform -chdir="$TERRAFORM_DIR"' in bootstrap

    assert "ensure_terraform_command" in configure
    assert 'run_terraform -chdir="$terraform_dir" output -json' in state_helper

    assert "require_command terraform" not in teardown
    assert 'run_terraform -chdir="${ROOT_DIR}/terraform" init' in teardown
