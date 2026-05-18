"""Contract tests for the modular monitoring stack."""

from __future__ import annotations

import configparser

from tests.repo_helpers import (
    read_repo_json as _read_json,
    read_repo_text as _read_text,
    read_repo_yaml as _read_yaml,
)


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
    assert grafana_environment["GRAFANA_PROMETHEUS_URL"] == ("http://prometheus:9090")
    assert grafana_environment["GF_SECURITY_ADMIN_USER"] == (
        "${FOEHNCAST_GRAFANA_ADMIN_USER:-admin}"
    )
    assert grafana_environment["GF_SECURITY_ADMIN_PASSWORD"] == (
        "${FOEHNCAST_GRAFANA_ADMIN_PASSWORD:-admin}"
    )
    assert grafana_environment["GF_SECURITY_ALLOW_EMBEDDING"] == (
        "${FOEHNCAST_GRAFANA_ALLOW_EMBEDDING:-false}"
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
    assert "HostedSyncStale" in domain
    assert all(r["labels"]["severity"] == "warning" for r in domain.values())


def test_grafana_provisioning_points_to_prometheus_dashboard_dir() -> None:
    datasource = _read_yaml(
        "grafana_work/etc/provisioning/datasources/foehncast-prometheus-datasource.yml"
    )["datasources"][0]
    dashboard_provider = _read_yaml(
        "grafana_work/etc/provisioning/dashboards/default.yml"
    )["providers"][0]
    ops = _read_json("grafana_work/dashboards/foehncast-operations.json")
    rider = _read_json("grafana_work/dashboards/foehncast-rider.json")
    ml = _read_json("grafana_work/dashboards/foehncast-ml-diagnostics.json")

    assert datasource["url"] == "${GRAFANA_PROMETHEUS_URL}"
    assert datasource["uid"] == "prometheus"
    assert dashboard_provider["options"]["path"] == "/opt/grafana/dashboards"

    # Operations dashboard
    assert ops["title"] == "FoehnCast Operations"
    assert ops["uid"] == "foehncast-operations"
    ops_panels = {p["title"]: p for p in ops["panels"]}
    assert "Feature Stage Durations" in ops_panels
    assert "Training Stage Durations" in ops_panels
    assert "Spot Pipeline Funnel" in ops_panels
    # Inference SLI panels (Request Rate, Error Rate, Latency p95, Request
    # Latency Distribution, Requests by Endpoint) were removed because the
    # in-process Prometheus surface served by `serve.py` does not retain a
    # time-series history and so rate()/histogram_quantile() panels render
    # as empty. They are tracked for restoration once a real Prometheus
    # scrape backend is in place.
    assert "Request Latency Distribution" not in ops_panels
    assert "Request Rate" not in ops_panels
    assert "Error Rate" not in ops_panels
    assert not any(
        p["type"] == "row" and p["title"] == "Inference SLIs" for p in ops["panels"]
    )

    # Rider dashboard
    assert rider["title"] == "FoehnCast Rider"
    assert rider["uid"] == "foehncast-rider"

    # ML Diagnostics dashboard
    assert ml["title"] == "FoehnCast ML Diagnostics"
    assert ml["uid"] == "foehncast-ml-diagnostics"
    ml_panels = {p["title"]: p for p in ml["panels"]}
    assert "Feature Stage States" in ml_panels
    assert "Model Registry" in [p["title"] for p in ml["panels"] if p["type"] == "row"]


def test_operations_dashboard_covers_pipeline_and_inference_metrics() -> None:
    ops = _read_json("grafana_work/dashboards/foehncast-operations.json")
    panels = {p["title"]: p for p in ops["panels"] if p["type"] != "row"}

    # Pipeline timing
    assert (
        panels["Feature Stage Durations"]["targets"][0]["expr"]
        == 'foehncast_feature_pipeline_stage_duration_seconds{dataset="train"}'
    )
    assert (
        panels["Training Stage Durations"]["targets"][0]["expr"]
        == 'foehncast_training_pipeline_stage_duration_seconds{dataset="train"}'
    )
    # Panels for metrics that the in-process /api/v1/query engine cannot
    # serve (predmon counters, online compose sync, up{} synthetic probes)
    # were dropped from the operations dashboard to keep the public view
    # free of empty panels on Cloud Run. They are reintroduced once a real
    # Prometheus scrape backend is available.
    for stripped in (
        "Hosted Sync Age",
        "Schedule Count",
        "Execution Count",
        "Seconds Since Last Success",
        "Sync Status File",
        "App",
        "Prometheus",
        "Grafana",
        "StatsD",
    ):
        assert stripped not in panels
    assert panels["Spot Pipeline Funnel"]["targets"][0]["expr"] == (
        'foehncast_feature_pipeline_expected_spot_count{dataset="train"}'
    )
    assert len(panels["Spot Pipeline Funnel"]["targets"]) == 5


def test_ml_diagnostics_dashboard_covers_drift_and_training_metrics() -> None:
    ml = _read_json("grafana_work/dashboards/foehncast-ml-diagnostics.json")
    panels = {p["title"]: p for p in ml["panels"] if p["type"] != "row"}

    # Drift overview
    assert (
        panels["Feature Drift Score"]["targets"][0]["expr"]
        == 'foehncast_drift_metric{dataset_name=~".+",metric_name="drift_score"}'
    )
    assert (
        panels["Inference Drift Score"]["targets"][0]["expr"]
        == 'foehncast_drift_metric{dataset_name="inference_predictions",metric_name="drift_score"}'
    )
    # Training metrics
    assert (
        panels["Accuracy"]["targets"][0]["expr"]
        == 'foehncast_training_pipeline_run_metric{dataset="train",metric_name="accuracy"}'
    )
    assert (
        panels["RMSE"]["targets"][0]["expr"]
        == 'foehncast_training_pipeline_run_metric{dataset="train",metric_name="rmse"}'
    )
    # Model registry
    assert (
        panels["Model Version"]["targets"][0]["expr"]
        == 'foehncast_training_pipeline_registered_model_version{dataset="train"}'
    )
    # Feature pipeline detail
    assert (
        panels["Range Violations per Spot"]["targets"][0]["expr"]
        == 'foehncast_feature_pipeline_spot_range_violation_count{dataset="train"}'
    )
    assert (
        panels["Training Handoff Ready"]["targets"][0]["expr"]
        == 'foehncast_feature_pipeline_training_handoff_ready{dataset="train"}'
    )
    assert (
        panels["Prediction Freshness"]["targets"][0]["expr"]
        == "time() - max(foehncast_prediction_log_latest_prediction_timestamp_seconds)"
    )
    # Collapsed rows contain spot-level and column-drift detail
    collapsed = {
        p["title"]: p for p in ml["panels"] if p["type"] == "row" and p.get("collapsed")
    }
    assert "Per-Column Drift Detail" in collapsed
    assert "Spot-Level Detail" in collapsed
    assert len(collapsed["Per-Column Drift Detail"]["panels"]) == 2
    assert len(collapsed["Spot-Level Detail"]["panels"]) == 7


def test_rider_dashboard_covers_drift_and_prediction_metrics() -> None:
    rider = _read_json("grafana_work/dashboards/foehncast-rider.json")
    panels = {p["title"]: p for p in rider["panels"] if p["type"] != "row"}

    # Drift status
    assert (
        panels["Feature Drift Score"]["targets"][0]["expr"]
        == 'foehncast_drift_metric{dataset_name=~".+",metric_name="drift_score"}'
    )
    # Model confidence gauge (sourced from the inference Prometheus surface,
    # which records the mean forecast quality index per spot after every
    # `/predict` or `/rank` call).
    assert (
        panels["Model Confidence"]["targets"][0]["expr"]
        == "avg(foehncast_inference_model_confidence)"
    )
    # System pulse
    assert (
        panels["Prediction Freshness"]["targets"][0]["expr"]
        == "time() - max(foehncast_prediction_log_latest_prediction_timestamp_seconds)"
    )
    # Spot validation panels (all 6 Swiss spots)
    spot_ids = {
        "silvaplana",
        "urnersee",
        "neuchatel",
        "bodensee",
        "walensee",
        "thunersee",
    }
    spot_panels = [
        p
        for p in rider["panels"]
        if p["type"] != "row"
        and "spot_validation_passed" in p.get("targets", [{}])[0].get("expr", "")
    ]
    assert len(spot_panels) == 6
    found_spots = set()
    for p in spot_panels:
        for sid in spot_ids:
            if sid in p["targets"][0]["expr"]:
                found_spots.add(sid)
    assert found_spots == spot_ids


def test_all_dashboards_have_unique_panel_ids_and_cross_links() -> None:
    for filename, uid in [
        ("foehncast-operations.json", "foehncast-operations"),
        ("foehncast-rider.json", "foehncast-rider"),
        ("foehncast-ml-diagnostics.json", "foehncast-ml-diagnostics"),
    ]:
        d = _read_json(f"grafana_work/dashboards/{filename}")
        assert d["uid"] == uid

        ids: set[int] = set()
        for p in d["panels"]:
            assert p["id"] not in ids, f"Duplicate id {p['id']} in {filename}"
            ids.add(p["id"])
            for inner in p.get("panels", []):
                assert inner["id"] not in ids, (
                    f"Duplicate id {inner['id']} in {filename}"
                )
                ids.add(inner["id"])

        assert len(d.get("links", [])) == 3


def test_grafana_ini_configures_anonymous_viewer_access_and_disables_public_dashboards() -> (
    None
):
    config = configparser.ConfigParser()
    config.read_string(_read_text("grafana_work/etc/grafana.ini"))

    assert not config.getboolean("auth", "disable_login_form")
    assert config.getboolean("auth.anonymous", "enabled")
    assert config["auth.anonymous"]["org_role"] == "Viewer"
    assert config.getboolean("security", "allow_embedding")
    assert not config.getboolean("public_dashboards", "enabled")
    assert config.getboolean("metrics", "enabled")
    assert (
        config["dashboards"]["default_home_dashboard_path"]
        == "/opt/grafana/dashboards/foehncast-operations.json"
    )


def test_local_bootstrap_applies_local_only_grafana_access_overrides() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "FOEHNCAST_GRAFANA_ALLOW_EMBEDDING" in bootstrap
    assert "FOEHNCAST_GRAFANA_DISABLE_LOGIN_FORM" in bootstrap
    assert "FOEHNCAST_GRAFANA_ANONYMOUS_ENABLED" in bootstrap
    assert "FOEHNCAST_GRAFANA_ANONYMOUS_ORG_ROLE" in bootstrap
    assert "GRAFANA_API_USER" in bootstrap
    assert "GRAFANA_API_PASSWORD" in bootstrap
    assert '--user "${GRAFANA_API_USER}:${GRAFANA_API_PASSWORD}"' in bootstrap


def test_local_bootstrap_verifies_grafana_provisioning() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")

    assert "verify_grafana_provisioning" in bootstrap
    assert "/api/search?dashboardUIDs=foehncast-operations" in bootstrap
    assert "/api/v1/provisioning/alert-rules" in bootstrap
    assert "foehncast_predmon_schedule_fail" in bootstrap
    assert "foehncast_predmon_execution_fail" in bootstrap
    assert "foehncast_predmon_stale_success" in bootstrap
    assert "foehncast_feature_stage_failures" in bootstrap
    assert "foehncast_training_stage_failures" in bootstrap
    assert "foehncast_hosted_sync_stale" in bootstrap
    assert "/api/v1/provisioning/contact-points?name=foehncast-email" in bootstrap
    assert "/api/v1/provisioning/policies" in bootstrap
    assert '"feature-pipeline"' in bootstrap
    assert '"training-pipeline"' in bootstrap
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
        'echo "Waiting for asset-triggered training pipeline..."'
    ) < bootstrap.index('echo "Waiting for app health..."')


def test_local_bootstrap_starts_monitoring_services_without_development_env() -> None:
    bootstrap = _read_text("scripts/bootstrap-local.sh")
    services = bootstrap.split("BOOTSTRAP_SERVICES=(", 1)[1].split(")", 1)[0]

    assert "statsd" in services
    assert "prometheus" in services
    assert "grafana" in services
    assert "development_env" not in services
