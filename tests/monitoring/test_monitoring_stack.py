"""Contract tests for the modular monitoring stack."""

from __future__ import annotations

from tests.repo_helpers import (
    read_repo_text as _read_text,
    read_repo_yaml as _read_yaml,
)


def test_root_compose_includes_monitoring_module() -> None:
    compose = _read_yaml("docker-compose.yml")

    assert "containers/monitoring/docker-compose.yml" in compose["include"]


def test_monitoring_compose_defines_expected_services() -> None:
    compose = _read_yaml("containers/monitoring/docker-compose.yml")
    services = compose["services"]

    assert {"statsd", "prometheus"}.issubset(services)
    assert "development" in services["statsd"]["networks"]
    assert "production" in services["statsd"]["networks"]
    assert "production" in services["prometheus"]["networks"]
    assert any(":8125/udp" in port for port in services["statsd"]["ports"])
    assert (
        "../../prometheus_config:/etc/prometheus:ro"
        in services["prometheus"]["volumes"]
    )


def test_prometheus_scrapes_app_and_statsd_targets() -> None:
    config = _read_yaml("prometheus_config/prometheus.yml")
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}

    assert jobs["foehncast_app"]["metrics_path"] == "/metrics"
    assert jobs["foehncast_app"]["static_configs"][0]["targets"] == ["app:8000"]
    assert jobs["statsd_exporter"]["static_configs"][0]["targets"] == ["statsd:9102"]


def test_statsd_mapping_preserves_drift_metric_labels() -> None:
    mapping = _read_yaml("prometheus_config/statsd_metrics-mapping.yml")

    assert mapping["mappings"][0]["match"] == "drift_metrics.*.*.*.*"
    assert mapping["mappings"][0]["name"] == "foehncast_drift_metric"


def test_prometheus_alerting_rules_cover_service_and_domain_health() -> None:
    rules = _read_yaml("prometheus_config/alerting_rules.yml")
    groups = {g["name"]: g for g in rules["groups"]}

    service = {r["alert"]: r for r in groups["foehncast-service-health"]["rules"]}
    assert groups["foehncast-service-health"]["interval"] == "30s"
    assert "AppDown" in service
    assert "HighRequestLatency" in service
    assert "PredictionErrorRateHigh" in service
    assert "StatsdExporterDown" in service
    assert service["AppDown"]["labels"]["severity"] == "critical"

    domain = {r["alert"]: r for r in groups["foehncast-domain-health"]["rules"]}
    assert groups["foehncast-domain-health"]["interval"] == "1m"
    assert "PredictionMonitoringScheduleFailure" in domain
    assert "PredictionMonitoringExecutionFailure" in domain
    assert "FeaturePipelineStageFailure" in domain
    assert "TrainingPipelineStageFailure" in domain
    assert all(r["labels"]["severity"] == "warning" for r in domain.values())


def test_app_compose_routes_monitoring_metrics_to_statsd_service() -> None:
    compose = _read_yaml("containers/app/docker-compose.yml")
    app_service = compose["services"]["app"]
    environment = compose["services"]["app"]["environment"]
    volumes = app_service["volumes"]

    assert environment["FOEHNCAST_STATSD_HOST"] == "statsd"
    assert environment["FOEHNCAST_STATSD_PORT"] == 8125
    assert (
        environment["FOEHNCAST_STATSD_PREFIX"]
        == "${FOEHNCAST_STATSD_PREFIX:-drift_metrics}"
    )
    assert "../../airflow/reports:/workspace/airflow/reports" in volumes


def test_local_bootstrap_waits_for_app_health_after_training_pipeline() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert bootstrap.index(
        'echo "Waiting for asset-triggered training pipeline..."'
    ) < bootstrap.index('echo "Waiting for app health..."')


def test_local_bootstrap_starts_monitoring_services_without_development_env() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    services = bootstrap.split("BOOTSTRAP_SERVICES=(", 1)[1].split(")", 1)[0]

    assert "statsd" in services
    assert "prometheus" in services
    assert "development_env" not in services
