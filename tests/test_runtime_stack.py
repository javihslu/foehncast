"""Contract tests for the modernized local runtime stack."""

from __future__ import annotations

from tests.repo_helpers import (
    REPO_ROOT,
    read_repo_text as _read_text,
    read_repo_yaml as _read_yaml,
)


def test_env_example_uses_airflow3_simple_auth_contract() -> None:
    env_example = _read_text(".env.example")

    assert "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=true" in env_example
    assert "AIRFLOW__API_AUTH__JWT_SECRET=foehncast-local-jwt-secret" in env_example
    assert "AIRFLOW_CREATE_ADMIN_USER" not in env_example
    assert "AIRFLOW__WEBSERVER__CONFIG_FILE" not in env_example


def test_airflow_compose_uses_airflow3_runtime_contract() -> None:
    compose = _read_yaml("containers/airflow/docker-compose.yml")
    runtime_env = compose["x-airflow-runtime-env"]
    services = compose["services"]

    assert runtime_env["AIRFLOW__CORE__EXECUTOR"] == "LocalExecutor"
    assert runtime_env["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"].startswith(
        "${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN:-postgresql+psycopg2://"
    )
    assert runtime_env["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN_ASYNC"].startswith(
        "${AIRFLOW__DATABASE__SQL_ALCHEMY_CONN_ASYNC:-postgresql+asyncpg://"
    )
    assert (
        runtime_env["AIRFLOW__CORE__EXECUTION_API_SERVER_URL"]
        == "http://airflow-webserver:8080/execution/"
    )
    assert (
        runtime_env["AIRFLOW__CORE__AUTH_MANAGER"]
        == "${AIRFLOW__CORE__AUTH_MANAGER:-airflow.api_fastapi.auth.managers.simple.simple_auth_manager.SimpleAuthManager}"
    )
    assert (
        runtime_env["AIRFLOW__API_AUTH__JWT_SECRET"]
        == "${AIRFLOW__API_AUTH__JWT_SECRET:-foehncast-local-jwt-secret}"
    )
    assert "airflow-postgres" in services
    assert "airflow-dag-processor" in services
    assert (
        services["airflow-webserver"]["healthcheck"]["test"][3]
        == "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/api/v2/version')"
    )
    assert services["airflow-scheduler"]["healthcheck"]["test"] == [
        "CMD",
        "airflow",
        "jobs",
        "check",
        "--job-type",
        "SchedulerJob",
        "--local",
    ]
    assert services["airflow-triggerer"]["healthcheck"]["test"] == [
        "CMD",
        "airflow",
        "jobs",
        "check",
        "--job-type",
        "TriggererJob",
        "--local",
    ]


def test_local_bootstrap_uses_runtime_service_subset_and_api_health() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    helper = _read_text("scripts/airflow-api-common.sh")
    services = bootstrap.split("BOOTSTRAP_SERVICES=(", 1)[1].split(")", 1)[0]

    assert "http://127.0.0.1:8080/api/v2/monitor/health" in bootstrap
    assert 'source "${ROOT_DIR}/scripts/airflow-api-common.sh"' in bootstrap
    assert "python3 -m foehncast.airflow_api" in helper
    assert "run_airflow_api_helper" in bootstrap
    assert "Waiting for Airflow API server health" in bootstrap
    assert "verify_airflow_api_health" in bootstrap
    assert "airflow_api_verify_health" in bootstrap
    assert "wait_for_service_health airflow-postgres 90 2" in bootstrap
    assert "wait_for_service_health airflow-triggerer 90 2" in bootstrap
    assert 'rm -f "$ROOT_DIR/airflow/airflow.db"' in bootstrap
    assert 'rm -rf "$ROOT_DIR/airflow/logs"' in bootstrap
    assert "wait_for_airflow_dag_run_state" in bootstrap
    assert "airflow_api_wait_for_dag_run_state" in bootstrap
    assert "asset_triggered" in bootstrap
    assert (
        "wait_for_airflow_dag_run_state training_pipeline success asset_triggered 120 2"
        in bootstrap
    )
    assert (
        'compose up --build -d --remove-orphans "${BOOTSTRAP_SERVICES[@]}"' in bootstrap
    )
    assert "airflow-postgres" in services
    assert "airflow-dag-processor" in services
    assert "development_env" not in services


def test_local_bootstrap_uses_shared_env_file_helpers() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    helper = _read_text("scripts/env-file-common.sh")

    assert 'source "${ROOT_DIR}/scripts/env-file-common.sh"' in bootstrap
    assert "env_file_value()" in helper
    assert "resolved_env_value()" in helper
    assert "export_resolved_env_value()" in helper
    assert "ensure_env_default()" in helper
    assert "export_local_feast_datastore_env()" in helper
    assert "env_file_value()" not in bootstrap
    assert 'export_local_feast_datastore_env "$ENV_FILE"' in bootstrap
    assert "ensure_env_default FOEHNCAST_GRAFANA_ADMIN_USER admin" in bootstrap
    assert (
        'FEAST_DATASET="${FEAST_DATASET:-$(resolved_env_value AIRFLOW_FEATURE_DATASET "$ENV_FILE")}"'
        in bootstrap
    )


def test_local_bootstrap_routes_mlflow_objectstore_wiring_through_storage_runtime_vars() -> (
    None
):
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert (
        'export STORAGE_S3_ENDPOINT="${STORAGE_S3_ENDPOINT:-http://${OBJECTSTORE_BIND_HOST}:${OBJECTSTORE_PORT}}"'
        in bootstrap
    )
    assert (
        'export MLFLOW_S3_ENDPOINT_URL="${MLFLOW_S3_ENDPOINT_URL:-$STORAGE_S3_ENDPOINT}"'
        in bootstrap
    )
    assert (
        'export MLFLOW_ARTIFACT_DESTINATION="${MLFLOW_ARTIFACT_DESTINATION:-s3://${STORAGE_S3_BUCKET}/mlflow/artifacts}"'
        in bootstrap
    )
    assert "OBJECTSTORE_ENDPOINT=" not in _read_text(".env.example")


def test_local_bootstrap_uses_shared_payload_check_helpers() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    helper = _read_text("scripts/payload-check-common.sh")

    assert 'source "${ROOT_DIR}/scripts/payload-check-common.sh"' in bootstrap
    assert "payload_check_require_pattern()" in helper
    assert "payload_check_require_patterns()" in helper
    assert "require_payload_patterns()" in bootstrap
    assert "require_payload_patterns \\" in bootstrap


def test_local_bootstrap_handles_missing_docker_desktop_helper() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "configure_docker_client_for_bootstrap" in bootstrap
    assert "docker-credential-desktop" in bootstrap
    assert '"credsStore"[[:space:]]*:[[:space:]]*"desktop"' in bootstrap
    assert 'ln -s "$source_docker_config/cli-plugins"' in bootstrap
    assert 'export DOCKER_CONFIG="$TEMP_DOCKER_CONFIG"' in bootstrap


def test_local_bootstrap_supports_ci_smoke_mode_and_teardown() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "Usage: $0 [--ci-smoke] [env-file]" in bootstrap
    assert "--ci-smoke)" in bootstrap
    assert "CI_SMOKE=true" in bootstrap
    assert (
        'CI_SMOKE_INGEST_FIXTURE_DIR="${CI_SMOKE_INGEST_FIXTURE_DIR:-/workspace/data/unit_contract_eval}"'
        in bootstrap
    )
    assert "AIRFLOW_AUTO_RETRAIN_MODE=off" not in bootstrap
    assert 'FOEHNCAST_INGEST_FIXTURE_DIR="$CI_SMOKE_INGEST_FIXTURE_DIR"' in bootstrap
    assert (
        "Stopping background Airflow orchestration services for isolated feature DAG smoke..."
        in bootstrap
    )
    assert (
        "compose stop airflow-dag-processor airflow-scheduler airflow-triggerer >/dev/null"
        in bootstrap
    )
    assert (
        "Restarting background Airflow orchestration services for asset-triggered training..."
        in bootstrap
    )
    assert (
        "compose up -d airflow-dag-processor airflow-scheduler airflow-triggerer >/dev/null"
        in bootstrap
    )
    assert "Waiting for asset-triggered training pipeline..." in bootstrap
    assert (
        "wait_for_airflow_dag_run_state training_pipeline success asset_triggered 120 2"
        in bootstrap
    )
    assert (
        "Skipping asset-triggered training pipeline wait in CI smoke mode."
        not in bootstrap
    )
    assert "Stopping CI smoke stack..." in bootstrap
    assert "compose down -v --remove-orphans >/dev/null 2>&1 || true" in bootstrap
    assert "Local evaluator smoke passed." in bootstrap
    assert (
        bootstrap.index('airflow dags test feature_pipeline "$FEATURE_DATE"')
        < bootstrap.rindex("restart_ci_smoke_airflow_orchestration_services")
        < bootstrap.index(
            "wait_for_airflow_dag_run_state training_pipeline success asset_triggered 120 2"
        )
    )


def test_local_bootstrap_prepares_bind_mounted_runtime_paths_for_container_writes() -> (
    None
):
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "prepare_bind_mounted_runtime_paths" in bootstrap
    assert 'prepare_bind_mounted_runtime_paths "$FEAST_DATASET"' in bootstrap
    assert 'chmod 0777 "$path"' in bootstrap
    assert 'rm -rf "$ROOT_DIR/grafana_work/data"' in bootstrap
    assert '"$ROOT_DIR/airflow"' in bootstrap
    assert '"$ROOT_DIR/.state/airflow"' in bootstrap
    assert '"$ROOT_DIR/.state/monitoring"' in bootstrap
    assert '"$ROOT_DIR/.state/online-compose-sync"' in bootstrap
    assert '"$ROOT_DIR/data/$dataset"' in bootstrap
    assert '"$ROOT_DIR/.state/feast"' in bootstrap
    assert '"$ROOT_DIR/data/feast"' in bootstrap
    assert '"$ROOT_DIR/grafana_work/data"' in bootstrap
    assert bootstrap.index(
        'prepare_bind_mounted_runtime_paths "$FEAST_DATASET"'
    ) < bootstrap.index(
        'compose up --build -d --remove-orphans "${BOOTSTRAP_SERVICES[@]}"'
    )


def test_local_evaluator_smoke_wrapper_delegates_to_ci_smoke_bootstrap() -> None:
    smoke = _read_text("scripts/smoke-local-evaluator.sh")

    assert 'exec "${ROOT_DIR}/scripts/bootstrap-local.sh" --ci-smoke "$@"' in smoke


def test_local_evaluator_smoke_uses_committed_ingest_fixtures() -> None:
    fixture_dir = REPO_ROOT / "data" / "unit_contract_eval"
    fixtures = {path.name for path in fixture_dir.glob("*.parquet")}

    assert fixtures == {
        "bodensee.parquet",
        "neuchatel.parquet",
        "silvaplana.parquet",
        "thunersee.parquet",
        "urnersee.parquet",
        "walensee.parquet",
    }


def test_airflow_init_uses_simple_auth_password_file() -> None:
    init_script = _read_text("containers/airflow/init-airflow.sh")

    assert "simple_auth_manager_passwords_file" in init_script
    assert 'printf \'{"%s":"%s"}\\n\'' in init_script
    assert "airflow db migrate" in init_script
    assert "airflow users create" not in init_script


def test_dag_processor_command_script_runs_airflow_dag_processor() -> None:
    dag_processor = _read_text("containers/airflow/start-airflow-dag-processor.sh")

    assert "exec airflow dag-processor" in dag_processor


def test_development_env_is_opt_in_via_local_only_profile() -> None:
    compose = _read_yaml("containers/development_env/docker-compose.yml")

    assert compose["services"]["development_env"]["profiles"] == ["local-only"]


def test_gcp_compose_overlay_injects_bigquery_storage_and_feast_env() -> None:
    gcp = _read_yaml("docker-compose.gcp.yml")

    runtime = gcp["x-gcp-runtime-env"]
    assert runtime["STORAGE_BACKEND"] == "bigquery"
    assert "GCP_PROJECT_ID" in str(runtime["STORAGE_BIGQUERY_PROJECT_ID"])
    assert "STORAGE_BIGQUERY_DATASET" in str(
        runtime.get("STORAGE_BIGQUERY_DATASET", "")
    )

    feast = gcp["x-feast-gcp-env"]
    assert feast["FOEHNCAST_FEAST_SOURCE"] == "bigquery"
    assert "gs://" in str(feast["FOEHNCAST_FEAST_REGISTRY"])
    assert "gs://" in str(feast["FOEHNCAST_FEAST_GCS_STAGING_LOCATION"])
    assert "FOEHNCAST_FEAST_DATASTORE_DATABASE" in feast

    services = gcp["services"]
    assert "gs://" in str(
        services["model-registry"]["environment"]["MLFLOW_ARTIFACT_DESTINATION"]
    )

    for svc in ("app", "airflow-scheduler", "airflow-triggerer"):
        svc_env = services[svc]["environment"]
        assert svc_env is not None, f"{svc} missing environment in GCP overlay"

    assert "gs://" in str(
        services["app"]["environment"].get("FOEHNCAST_PIPELINE_REPORT_DIR", "")
    )


def test_gcp_compose_overlay_does_not_set_s3_endpoint_on_mlflow() -> None:
    gcp = _read_yaml("docker-compose.gcp.yml")
    mlflow_env = gcp["services"]["model-registry"]["environment"]

    assert "MLFLOW_S3_ENDPOINT_URL" not in mlflow_env
    assert "AWS_ACCESS_KEY_ID" not in mlflow_env
    assert "AWS_SECRET_ACCESS_KEY" not in mlflow_env


def test_mlflow_base_compose_does_not_hardcode_s3_credentials() -> None:
    mlflow = _read_yaml("containers/mlflow/docker-compose.yml")
    env_list = mlflow["services"]["model-registry"]["environment"]

    env_keys = {e.split("=")[0] for e in env_list}
    assert "AWS_ACCESS_KEY_ID" not in env_keys
    assert "AWS_SECRET_ACCESS_KEY" not in env_keys
    assert "MLFLOW_S3_ENDPOINT_URL" not in env_keys


def test_objectstore_overlay_still_injects_s3_credentials_into_mlflow() -> None:
    obj = _read_yaml("docker-compose.objectstore.yml")
    mlflow_env = obj["services"]["model-registry"]["environment"]

    assert "AWS_ACCESS_KEY_ID" in mlflow_env
    assert "AWS_SECRET_ACCESS_KEY" in mlflow_env
    assert mlflow_env["MLFLOW_S3_ENDPOINT_URL"] == "http://objectstore:9000"


def test_runtime_images_use_validated_airflow_and_mlflow_versions() -> None:
    airflow_dockerfile = _read_text("containers/airflow/Dockerfile")
    mlflow_dockerfile = _read_text("containers/mlflow/Dockerfile")

    assert "FROM apache/airflow:3.2.1-python3.12" in airflow_dockerfile
    assert "apache-airflow-providers-standard==1.12.3" in airflow_dockerfile
    assert '"feast[gcp]>=0.63.0"' in airflow_dockerfile
    assert "python -m venv /home/airflow/.local/feast-venv" in airflow_dockerfile
    assert (
        "FOEHNCAST_FEAST_PYTHON=/home/airflow/.local/feast-venv/bin/python"
        in airflow_dockerfile
    )
    assert "FROM ghcr.io/mlflow/mlflow:v3.12.0" in mlflow_dockerfile
