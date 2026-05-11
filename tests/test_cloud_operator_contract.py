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
    "cloud_run_min_instance_count",
    "cloud_run_max_instance_count",
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
    assert len(inputs) <= 25

    for input_name in REPO_BACKED_WORKFLOW_INPUTS:
        assert input_name in inputs
        assert "default" not in inputs[input_name]

    assert "cloud_run_container_port" not in inputs
    assert "cloud_run_cpu" not in inputs
    assert "cloud_run_memory" not in inputs

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
        'cloud_run_min_instance_count="${{ inputs.cloud_run_min_instance_count }}"'
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
        'cloud_run_max_instance_count="${{ inputs.cloud_run_max_instance_count }}"'
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


def test_remote_terraform_workflow_apply_summary_reports_hosted_feast_follow_up() -> (
    None
):
    workflow = _workflow_yaml(".github/workflows/terraform.yml")

    summary_step = _workflow_step(workflow, "remote", "Summarize outputs")
    summary_script = summary_step["run"]

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
    assert 'role    = "roles/bigquery.readSessionUser"' in terraform
    assert 'role   = "roles/storage.objectAdmin"' in terraform
    assert (
        "google_project_iam_member.cloud_run_bigquery_read_session_user," in terraform
    )
    assert (
        "google_project_iam_member.online_compose_bigquery_read_session_user,"
        in terraform
    )
    assert "google_storage_bucket_iam_member.online_compose_bucket_admin," in terraform


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
        "install -d -m 0755 /opt/foehncast/.state /opt/foehncast/.state/feast"
        in template
    )
    assert "install -d -m 0755 /opt/foehncast/grafana_work/data" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/airflow" in template
    assert "chown -R $${app_uid}:$${app_uid} /opt/foehncast/.state" in template
    assert (
        "chown -R $${grafana_uid}:$${grafana_uid} /opt/foehncast/grafana_work/data"
        in template
    )
    assert "chown $${airflow_uid}:0 /opt/foehncast/airflow/.admin-password" in template


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
        "install -d -m 0755 /opt/foehncast/.state /opt/foehncast/.state/feast"
        in template
    )
    assert "install -d -m 0755 /opt/foehncast/grafana_work/data" in template
    assert "chown -R $${airflow_uid}:0 /opt/foehncast/airflow" in template
    assert "chown -R $${app_uid}:$${app_uid} /opt/foehncast/.state" in template
    assert (
        "chown -R $${grafana_uid}:$${grafana_uid} /opt/foehncast/grafana_work/data"
        in template
    )
    assert "chown $${airflow_uid}:0 /opt/foehncast/airflow/.admin-password" in template
    assert "chmod 600 /opt/foehncast/airflow/.admin-password" in template


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
    assert 'role   = "roles/storage.objectAdmin"' in terraform
    assert "google_project_iam_member.cloud_run_bigquery_read_session_user" in terraform
    assert (
        "google_project_iam_member.online_compose_bigquery_read_session_user"
        in terraform
    )
    assert "google_storage_bucket_iam_member.online_compose_bucket_admin" in terraform


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


def test_prepare_feast_cloud_requires_bigquery_runtime_contract() -> None:
    script = _read_text("scripts/prepare-feast-cloud.sh")

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
        'echo "Set GCP_PROJECT_ID or FOEHNCAST_FEAST_PROJECT_ID in .env or the environment." >&2'
        in script
    )
    assert (
        'echo "Set GCP_BUCKET_NAME, FOEHNCAST_FEAST_GCS_BUCKET, or FOEHNCAST_FEAST_REGISTRY in .env or the environment." >&2'
        in script
    )


def test_prepare_feast_cloud_renders_runtime_config_and_applies_repo() -> None:
    script = _read_text("scripts/prepare-feast-cloud.sh")

    assert (
        'CONFIG_PATH="$(cd "$ROOT_DIR" && uv run python -m foehncast.feast_runtime)"'
        in script
    )
    assert 'export FOEHNCAST_FEAST_CONFIG_PATH="$CONFIG_PATH"' in script
    assert 'export FEAST_FS_YAML_FILE_PATH="$CONFIG_PATH"' in script
    assert 'cd "$ROOT_DIR/feature_repo"' in script
    assert "uv run --group feast feast apply >/dev/null" in script


def test_prepare_feast_cloud_materializes_or_prints_next_step() -> None:
    script = _read_text("scripts/prepare-feast-cloud.sh")

    assert (
        'uv run --group feast feast materialize-incremental "$MATERIALIZE_TS" >/dev/null'
        in script
    )
    assert "printf 'Materialized through: %s\\n' \"$MATERIALIZE_TS\"" in script
    assert (
        'printf \'Next: cd %s/feature_repo && uv run --group feast feast materialize-incremental "%s"\\n\' "$ROOT_DIR" "$MATERIALIZE_TS"'
        in script
    )


def test_smoke_bootstrap_only_seeds_hosted_feast_defaults() -> None:
    script = _read_text("scripts/smoke-bootstrap-only.sh")

    assert "smoke_feast_bigquery_table()" in script
    assert "print_smoke_feast_summary()" in script
    assert (
        'printf \'%s.%s.%s\\n\' "$PROJECT_ID" "foehncast" "forecast_features"' in script
    )
    assert 'echo "- hosted Feast source: bigquery"' in script
    assert (
        'echo "- hosted Feast offline source table: $(smoke_feast_bigquery_table)"'
        in script
    )
    assert 'echo "- hosted Feast online store database: feast-online"' in script
    assert '"foehncast" \\' in script
    assert '"forecast_features" \\' in script
    assert '"feast-online" \\' in script


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

    assert "remote_feast_bigquery_dataset()" in script
    assert 'value="${INPUT_BIGQUERY_DATASET_ID:-}"' in script
    assert (
        'value="$(repo_variable_value "$REPOSITORY_PATH" GCP_BIGQUERY_DATASET)"'
        in script
    )
    assert (
        'value="${GCP_BIGQUERY_DATASET:-${STORAGE_BIGQUERY_DATASET:-${FOEHNCAST_FEAST_BIGQUERY_DATASET:-foehncast}}}"'
        in script
    )
    assert "remote_feast_bigquery_table()" in script
    assert (
        'if [[ -z "$INPUT_BIGQUERY_DATASET_ID" && -z "$INPUT_BIGQUERY_FEATURE_TABLE_ID" ]]; then'
        in script
    )
    assert 'runtime_table="${FOEHNCAST_FEAST_BIGQUERY_TABLE:-}"' in script
    assert 'table_id="${INPUT_BIGQUERY_FEATURE_TABLE_ID:-}"' in script
    assert (
        'table_id="$(repo_variable_value "$REPOSITORY_PATH" GCP_BIGQUERY_TABLE)"'
        in script
    )
    assert (
        'table_id="${GCP_BIGQUERY_TABLE:-${STORAGE_BIGQUERY_TABLE:-forecast_features}}"'
        in script
    )
    assert 'project_id="${PROJECT_ID:-<project_id>}"' in script
    assert 'value="${INPUT_FEAST_ONLINE_STORE_DATABASE_NAME:-}"' in script
    assert (
        'value="$(repo_variable_value "$REPOSITORY_PATH" GCP_FEAST_ONLINE_STORE_DATABASE_NAME)"'
        in script
    )
    assert (
        'value="${GCP_FEAST_ONLINE_STORE_DATABASE_NAME:-${FOEHNCAST_FEAST_DATASTORE_DATABASE:-feast-online}}"'
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
    assert "hashicorp/terraform:" not in cli_common

    assert "require_command terraform" not in bootstrap
    assert 'run_terraform -chdir="$TERRAFORM_DIR"' in bootstrap

    assert "ensure_terraform_command" in configure
    assert 'run_terraform -chdir="$terraform_dir" output -json' in state_helper

    assert "require_command terraform" not in teardown
    assert 'run_terraform -chdir="${ROOT_DIR}/terraform" init' in teardown
    assert (
        'echo "Terraform variables file not found: $TFVARS_FILE. Nothing to preview in this working copy."'
        in teardown
    )
    assert (
        'echo "Reuse the file created for provisioning to preview local destroy targets, or use ./scripts/terraform-remote.sh destroy for remote-backend environments."'
        in teardown
    )
