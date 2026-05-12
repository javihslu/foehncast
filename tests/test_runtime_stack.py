"""Contract tests for the modernized local runtime stack."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def _read_yaml(relative_path: str) -> dict:
    return yaml.safe_load(_read_text(relative_path))


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
    assert "airflow-dag-processor" in services


def test_local_bootstrap_uses_runtime_service_subset_and_api_health() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    services = bootstrap.split("BOOTSTRAP_SERVICES=(", 1)[1].split(")", 1)[0]

    assert "http://127.0.0.1:8080/api/v2/monitor/health" in bootstrap
    assert "Waiting for Airflow API server health" in bootstrap
    assert 'rm -f "$ROOT_DIR/airflow/airflow.db"' in bootstrap
    assert 'rm -rf "$ROOT_DIR/airflow/logs"' in bootstrap
    assert 'TRAINING_DAG_CONF="$(printf ' in bootstrap
    assert '"stage":"Production"' in bootstrap
    assert (
        'airflow dags test training_pipeline "$TRAINING_DATE" -c "$TRAINING_DAG_CONF"'
        in bootstrap
    )
    assert (
        'compose up --build -d --remove-orphans "${BOOTSTRAP_SERVICES[@]}"' in bootstrap
    )
    assert "airflow-dag-processor" in services
    assert "development_env" not in services


def test_local_bootstrap_handles_missing_docker_desktop_helper() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "configure_docker_client_for_bootstrap" in bootstrap
    assert "docker-credential-desktop" in bootstrap
    assert '"credsStore"[[:space:]]*:[[:space:]]*"desktop"' in bootstrap
    assert 'ln -s "$source_docker_config/cli-plugins"' in bootstrap
    assert 'export DOCKER_CONFIG="$TEMP_DOCKER_CONFIG"' in bootstrap


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


def test_runtime_images_use_validated_airflow_and_mlflow_versions() -> None:
    airflow_dockerfile = _read_text("containers/airflow/Dockerfile")
    mlflow_dockerfile = _read_text("containers/mlflow/Dockerfile")

    assert "FROM apache/airflow:3.2.1-python3.12" in airflow_dockerfile
    assert "apache-airflow-providers-standard==1.12.3" in airflow_dockerfile
    assert "FROM ghcr.io/mlflow/mlflow:v3.12.0" in mlflow_dockerfile
