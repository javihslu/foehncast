"""Contract tests for the modular monitoring stack."""

from __future__ import annotations

import configparser
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def _read_yaml(relative_path: str) -> dict:
    return yaml.safe_load(_read_text(relative_path))


def _read_json(relative_path: str) -> dict:
    return json.loads(_read_text(relative_path))


def test_root_compose_includes_monitoring_module() -> None:
    compose = _read_yaml("docker-compose.yml")

    assert "containers/monitoring/docker-compose.yml" in compose["include"]


def test_monitoring_compose_defines_expected_services() -> None:
    compose = _read_yaml("containers/monitoring/docker-compose.yml")
    services = compose["services"]
    grafana_environment = services["grafana"]["environment"]

    assert {"statsd", "prometheus", "grafana"}.issubset(services)
    assert "development" in services["statsd"]["networks"]
    assert "production" in services["statsd"]["networks"]
    assert "production" in services["prometheus"]["networks"]
    assert "production" in services["grafana"]["networks"]
    assert any(":8125/udp" in port for port in services["statsd"]["ports"])
    assert (
        "../../prometheus_config:/etc/prometheus:ro"
        in services["prometheus"]["volumes"]
    )
    assert (
        "../../grafana_work/dashboards:/opt/grafana/dashboards:ro"
        in services["grafana"]["volumes"]
    )
    assert grafana_environment["FOEHNCAST_GRAFANA_ALERT_EMAIL"] == (
        "${FOEHNCAST_GRAFANA_ALERT_EMAIL:-alerts@example.invalid}"
    )
    assert grafana_environment["GF_SECURITY_ADMIN_USER"] == (
        "${FOEHNCAST_GRAFANA_ADMIN_USER:-admin}"
    )
    assert grafana_environment["GF_SECURITY_ADMIN_PASSWORD"] == (
        "${FOEHNCAST_GRAFANA_ADMIN_PASSWORD:-admin}"
    )
    assert grafana_environment["GF_AUTH_DISABLE_LOGIN_FORM"] == (
        "${FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM:-false}"
    )
    assert grafana_environment["GF_AUTH_ANONYMOUS_ENABLED"] == (
        "${FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED:-false}"
    )
    assert grafana_environment["GF_AUTH_ANONYMOUS_ORG_ROLE"] == (
        "${FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE:-Viewer}"
    )


def test_prometheus_scrapes_app_statsd_and_grafana_targets() -> None:
    config = _read_yaml("prometheus_config/prometheus.yml")
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}

    assert jobs["foehncast_app"]["metrics_path"] == "/metrics"
    assert jobs["foehncast_app"]["static_configs"][0]["targets"] == ["app:8000"]
    assert jobs["statsd_exporter"]["static_configs"][0]["targets"] == ["statsd:9102"]
    assert jobs["grafana"]["static_configs"][0]["targets"] == ["grafana:3000"]


def test_statsd_mapping_preserves_drift_metric_labels() -> None:
    mapping = _read_yaml("prometheus_config/statsd_metrics-mapping.yml")

    assert mapping["mappings"][0]["match"] == "drift_metrics.*.*.*.*"
    assert mapping["mappings"][0]["name"] == "foehncast_drift_metric"


def test_grafana_provisioning_points_to_prometheus_dashboard_dir() -> None:
    datasource = _read_yaml(
        "grafana_work/etc/provisioning/datasources/foehncast-prometheus-datasource.yml"
    )["datasources"][0]
    dashboard_provider = _read_yaml(
        "grafana_work/etc/provisioning/dashboards/default.yml"
    )["providers"][0]
    dashboard = _read_json("grafana_work/dashboards/foehncast-overview.json")

    assert datasource["url"] == "http://prometheus:9090"
    assert datasource["uid"] == "prometheus"
    assert dashboard_provider["options"]["path"] == "/opt/grafana/dashboards"
    assert dashboard["title"] == "FoehnCast Monitoring"
    assert any(
        panel["title"] == "Feature Pipeline Summary Count"
        for panel in dashboard["panels"]
    )


def test_grafana_alerting_provisions_background_monitoring_rules() -> None:
    alerting = _read_yaml(
        "grafana_work/etc/provisioning/alerting/foehncast-alert-rules.yml"
    )
    group = alerting["groups"][0]
    rules = {rule["title"]: rule for rule in group["rules"]}

    assert alerting["apiVersion"] == 1
    assert group["folder"] == "FoehnCast Monitoring"
    assert group["interval"] == "1m"
    assert (
        rules["FoehnCast Prediction Monitoring Schedule Failures"]["data"][0]["model"][
            "expr"
        ]
        == 'sum by (endpoint) (increase(foehncast_prediction_monitoring_schedule_total{result="failed"}[15m]))'
    )
    assert rules["FoehnCast Prediction Monitoring Schedule Failures"]["panelId"] == 12
    assert (
        rules["FoehnCast Prediction Monitoring Execution Failures"]["data"][0]["model"][
            "expr"
        ]
        == 'sum by (endpoint) (increase(foehncast_prediction_monitoring_execution_total{result="failed"}[15m]))'
    )
    assert rules["FoehnCast Prediction Monitoring Execution Failures"]["panelId"] == 13
    assert (
        rules["FoehnCast Prediction Monitoring Stale Success"]["data"][0]["model"][
            "expr"
        ]
        == '((time() - max by (endpoint) (foehncast_prediction_monitoring_last_execution_timestamp_seconds{result="succeeded"})) * on (endpoint) (sum by (endpoint) (increase(foehncast_prediction_monitoring_schedule_total{result="scheduled"}[15m])) > bool 0))'
    )
    assert rules["FoehnCast Prediction Monitoring Stale Success"]["panelId"] == 14
    assert (
        rules["FoehnCast Feature Stage Failures"]["data"][0]["model"]["expr"]
        == "max by (dataset, storage_backend, stage) (foehncast_feature_pipeline_stage_failure_count)"
    )
    assert rules["FoehnCast Feature Stage Failures"]["panelId"] == 18
    assert rules["FoehnCast Feature Stage Failures"]["labels"]["component"] == (
        "feature-pipeline"
    )
    assert (
        rules["FoehnCast Hosted Sync Stale"]["data"][0]["model"]["expr"]
        == "time() - max by (git_ref, compose_deploy_mode) (foehncast_online_compose_sync_last_success_timestamp_seconds)"
    )
    assert rules["FoehnCast Hosted Sync Stale"]["panelId"] == 19
    assert rules["FoehnCast Hosted Sync Stale"]["labels"]["component"] == (
        "hosted-operator"
    )
    assert all(
        rule["dashboardUid"] == "foehncast-monitoring" for rule in rules.values()
    )


def test_grafana_alerting_provisions_contact_point_and_policy_tree() -> None:
    contact_points = _read_yaml(
        "grafana_work/etc/provisioning/alerting/foehncast-contact-points.yml"
    )
    policies = _read_yaml(
        "grafana_work/etc/provisioning/alerting/foehncast-notification-policies.yml"
    )

    contact_point = contact_points["contactPoints"][0]
    receiver = contact_point["receivers"][0]
    policy = policies["policies"][0]
    routes = policy["routes"]
    inference_route = next(
        route
        for route in routes
        if route["object_matchers"] == [["component", "=", "inference-monitoring"]]
    )
    feature_route = next(
        route
        for route in routes
        if route["object_matchers"] == [["component", "=", "feature-pipeline"]]
    )
    hosted_route = next(
        route
        for route in routes
        if route["object_matchers"] == [["component", "=", "hosted-operator"]]
    )

    assert contact_points["apiVersion"] == 1
    assert contact_point["name"] == "foehncast-email"
    assert receiver["uid"] == "foehncast_email"
    assert receiver["type"] == "email"
    assert receiver["settings"]["addresses"] == "$FOEHNCAST_GRAFANA_ALERT_EMAIL"

    assert policies["apiVersion"] == 1
    assert policy["receiver"] == "foehncast-email"
    assert policy["group_by"] == ["alertname", "severity"]
    assert inference_route["receiver"] == "foehncast-email"
    assert inference_route["object_matchers"] == [
        ["component", "=", "inference-monitoring"]
    ]
    assert inference_route["group_by"] == ["alertname", "endpoint", "severity"]
    assert feature_route["receiver"] == "foehncast-email"
    assert feature_route["object_matchers"] == [["component", "=", "feature-pipeline"]]
    assert feature_route["group_by"] == [
        "alertname",
        "dataset",
        "storage_backend",
        "stage",
        "severity",
    ]
    assert hosted_route["receiver"] == "foehncast-email"
    assert hosted_route["group_by"] == [
        "alertname",
        "git_ref",
        "compose_deploy_mode",
        "severity",
    ]


def test_grafana_dashboard_includes_feature_and_inference_drift_panels() -> None:
    dashboard = _read_json("grafana_work/dashboards/foehncast-overview.json")
    panels = {panel["title"]: panel for panel in dashboard["panels"]}

    assert (
        panels["Feature Drift Share"]["targets"][0]["expr"]
        == 'max by (dataset_name, dataset_version) (foehncast_drift_metric{column_name="dataset", metric_name="share_of_drifted_columns", dataset_name!="inference_predictions"})'
    )
    assert (
        panels["Feature Drift Share"]["fieldConfig"]["defaults"]["thresholds"]["steps"][
            1
        ]["value"]
        == 0.15
    )
    assert (
        panels["Inference Drift Share"]["targets"][0]["expr"]
        == 'max by (dataset_version) (foehncast_drift_metric{dataset_name="inference_predictions", column_name="dataset", metric_name="share_of_drifted_columns"})'
    )
    assert (
        panels["Inference Drift Share"]["fieldConfig"]["defaults"]["thresholds"][
            "steps"
        ][2]["value"]
        == 0.3
    )
    assert (
        panels["Inference Quality Drift Score"]["targets"][0]["expr"]
        == 'max by (dataset_version) (foehncast_drift_metric{dataset_name="inference_predictions", column_name="quality_index", metric_name="drift_score"})'
    )
    assert (
        panels["Prediction Log Total Rows"]["targets"][0]["expr"]
        == "foehncast_prediction_log_total_row_count"
    )
    assert (
        panels["Prediction Log Models"]["targets"][0]["expr"]
        == "foehncast_prediction_log_model_count"
    )
    assert (
        panels["Prediction Log Rows By Model"]["targets"][0]["expr"]
        == "foehncast_prediction_log_row_count"
    )
    assert (
        panels["Prediction Monitoring Schedule Failures (15m)"]["targets"][0]["expr"]
        == 'sum by (endpoint) (increase(foehncast_prediction_monitoring_schedule_total{result="failed"}[15m]))'
    )
    assert (
        panels["Engineered Spots"]["targets"][0]["expr"]
        == "sum by (dataset, storage_backend) (foehncast_feature_pipeline_engineered_spot_count)"
    )
    assert (
        panels["Validated Spots"]["targets"][0]["expr"]
        == "sum by (dataset, storage_backend) (foehncast_feature_pipeline_validated_spot_count)"
    )
    assert (
        panels["Feature Stage Duration"]["targets"][0]["expr"]
        == "max by (dataset, storage_backend, stage) (foehncast_feature_pipeline_stage_duration_seconds)"
    )
    assert (
        panels["Feature Stage Failures"]["targets"][0]["expr"]
        == "max by (dataset, storage_backend, stage) (foehncast_feature_pipeline_stage_failure_count)"
    )
    assert (
        panels["Seconds Since Last Hosted Sync"]["targets"][0]["expr"]
        == "time() - max by (git_ref, compose_deploy_mode) (foehncast_online_compose_sync_last_success_timestamp_seconds)"
    )
    assert (
        panels["Prediction Monitoring Schedule Failures (15m)"]["fieldConfig"][
            "defaults"
        ]["thresholds"]["steps"][1]["value"]
        == 0.5
    )
    assert (
        panels["Seconds Since Last Hosted Sync"]["fieldConfig"]["defaults"][
            "thresholds"
        ]["steps"][1]["value"]
        == 900
    )
    assert (
        panels["Prediction Monitoring Execution Failures (15m)"]["targets"][0]["expr"]
        == 'sum by (endpoint) (increase(foehncast_prediction_monitoring_execution_total{result="failed"}[15m]))'
    )
    assert (
        panels["Prediction Monitoring Execution Failures (15m)"]["fieldConfig"][
            "defaults"
        ]["thresholds"]["steps"][1]["value"]
        == 0.5
    )
    assert (
        panels["Seconds Since Last Successful Monitoring"]["targets"][0]["expr"]
        == 'time() - max by (endpoint) (foehncast_prediction_monitoring_last_execution_timestamp_seconds{result="succeeded"})'
    )


def test_grafana_ini_disables_anonymous_access_and_public_dashboards_by_default() -> (
    None
):
    config = configparser.ConfigParser()
    config.read_string(_read_text("grafana_work/etc/grafana.ini"))

    assert not config.getboolean("auth", "disable_login_form")
    assert not config.getboolean("auth.anonymous", "enabled")
    assert config["auth.anonymous"]["org_role"] == "Viewer"
    assert not config.getboolean("security", "allow_embedding")
    assert not config.getboolean("public_dashboards", "enabled")
    assert config.getboolean("metrics", "enabled")
    assert (
        config["dashboards"]["default_home_dashboard_path"]
        == "/opt/grafana/dashboards/foehncast-overview.json"
    )


def test_local_bootstrap_applies_local_only_grafana_access_overrides() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM" in bootstrap
    assert "FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED" in bootstrap
    assert "FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE" in bootstrap
    assert "GRAFANA_API_USER" in bootstrap
    assert "GRAFANA_API_PASSWORD" in bootstrap
    assert '--user "${GRAFANA_API_USER}:${GRAFANA_API_PASSWORD}"' in bootstrap


def test_local_bootstrap_verifies_grafana_provisioning() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "verify_grafana_provisioning" in bootstrap
    assert "/api/search?dashboardUIDs=foehncast-monitoring" in bootstrap
    assert "/api/v1/provisioning/alert-rules" in bootstrap
    assert "foehncast_predmon_schedule_fail" in bootstrap
    assert "foehncast_predmon_execution_fail" in bootstrap
    assert "foehncast_predmon_stale_success" in bootstrap
    assert "foehncast_feature_stage_failures" in bootstrap
    assert "foehncast_hosted_sync_stale" in bootstrap
    assert "/api/v1/provisioning/contact-points?name=foehncast-email" in bootstrap
    assert "/api/v1/provisioning/policies" in bootstrap
    assert '"feature-pipeline"' in bootstrap
    assert '"hosted-operator"' in bootstrap


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


def test_local_bootstrap_verifies_grafana_before_pipeline_runs() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert bootstrap.index("verify_grafana_provisioning") < bootstrap.index(
        'echo "Running feature pipeline for ${FEATURE_DATE}..."'
    )


def test_local_bootstrap_waits_for_app_health_after_training_pipeline() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert bootstrap.index(
        "wait_for_airflow_dag_run_state training_pipeline success asset_triggered 120 2"
    ) < bootstrap.index('echo "Waiting for app health..."')


def test_local_bootstrap_seeds_hosted_sync_status_before_stack_start() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "seed_local_online_compose_sync_status" in bootstrap
    assert 'sync_status_file="$sync_dir/last-success.json"' in bootstrap
    assert bootstrap.rindex("seed_local_online_compose_sync_status") < bootstrap.index(
        'echo "Starting local stack..."'
    )


def test_local_bootstrap_verifies_hosted_sync_metrics_after_app_health() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert (
        'APP_METRICS_URL="${APP_METRICS_URL:-http://127.0.0.1:8000/metrics}"'
        in bootstrap
    )
    assert "verify_hosted_sync_metrics" in bootstrap
    assert "foehncast_online_compose_sync_status_file_present" in bootstrap
    assert "foehncast_online_compose_sync_last_success_timestamp_seconds" in bootstrap
    assert bootstrap.index('echo "Waiting for app health..."') < bootstrap.rindex(
        "verify_hosted_sync_metrics"
    )


def test_local_bootstrap_starts_monitoring_services_without_development_env() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    services = bootstrap.split("BOOTSTRAP_SERVICES=(", 1)[1].split(")", 1)[0]

    assert "statsd" in services
    assert "prometheus" in services
    assert "grafana" in services
    assert "development_env" not in services
