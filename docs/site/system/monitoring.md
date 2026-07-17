# Monitoring

FoehnCast uses Prometheus for metrics collection, Evidently for drift detection, and Streamlit for visualization. This page explains what gets measured and how.

## Signal Flow

<div class="mermaid">
flowchart TD
    subgraph Sources ["What generates signals"]
        AIR["Pipeline summaries (JSON)"]
        PRED["Prediction requests"]
        HIND["Hindcast validation"]
        DRIFT["Drift detection (Evidently)"]
    end

    subgraph Collection ["How they're collected"]
        APP["/metrics endpoint"]
        STATSD["StatsD exporter"]
    end

    subgraph Display ["Where you see them"]
        PROM["Prometheus"]
        ALERT["Alert rules"]
        UI["Streamlit charts"]
    end

    AIR --> APP
    PRED --> APP
    HIND --> APP
    DRIFT --> STATSD
    APP --> PROM
    STATSD --> PROM
    PROM --> UI
    PROM --> ALERT
</div>

## Metrics

The app serves one combined `/metrics` endpoint with everything Prometheus needs:

| Metric prefix | What it tracks |
|--------------|---------------|
| `foehncast_feature_pipeline_*` | Feature pipeline stage status, row counts, durations |
| `foehncast_training_pipeline_*` | Training results, model versions |
| `foehncast_prediction_monitoring_*` | Background task scheduling and execution |
| `foehncast_drift_metric` | Per-column drift scores (via StatsD) |

## Drift Detection

Uses Evidently to compare feature distributions:

| Type | Reference | Current | Method |
|------|-----------|---------|--------|
| Feature drift | Stored reference dataset | Latest curated features | Column-level statistical tests |
| Prediction drift | Historical predictions | Recent prediction window | Distribution comparison |

Results go through StatsD → Prometheus as `foehncast_drift_metric`.

## Hindcast Validation

Compares past predictions against what actually happened:

1. Background task runs hourly
2. Waits 5 days (Open-Meteo archive API latency)
3. Fetches observed weather for each past prediction
4. Recomputes quality using the same labeling function
5. Reports accuracy, MAE, and per-class counts

Results persist in `.state/monitoring/hindcast-validation.json` and show up on `/metrics` and in the Streamlit model card.

## Shadow scoring

On every full inference batch the candidate model scores the same feature frames as the champion, and the pipeline records how far the two disagree. It compares the predicted quality per spot and horizon, then summarises the absolute differences as `foehncast_shadow_mean_abs_divergence`, `foehncast_shadow_max_abs_divergence`, and `foehncast_shadow_compared_rows`, with a `foehncast_shadow_model_info` series carrying the champion and candidate versions. These gauges render from the shadow section of the latest prediction snapshot and appear as a "Shadow" chip in the system tab. Shadow scoring activates only when a distinct candidate alias exists, so right after a first-version bootstrap (champion equals candidate) there is nothing to compare. The path is fully guarded: any failure is skipped and the served champion output is never blocked or changed.

## Alert Rules

Defined in `prometheus_config/alerting_rules.yml`:

| Alert | Fires when |
|-------|-----------|
| `AppDown` | App unreachable for 2 min |
| `HighRequestLatency` | p95 HTTP request latency > 2s for 5 min |
| `PredictionErrorRateHigh` | `/predict` 5xx rate > 0.1/s over 15 min |
| `StatsdExporterDown` | StatsD target gone for 5 min |
| `PredictionMonitoringScheduleFailure` | Background scheduling fails |
| `PredictionMonitoringExecutionFailure` | Background execution fails |
| `FeaturePipelineStageFailure` | Any feature stage fails |
| `TrainingPipelineStageFailure` | Any training stage fails |

## Scrape Config

Three targets in `prometheus_config/prometheus.yml` (15s interval):

| Job | Target |
|-----|--------|
| `foehncast_app` | `app:8000/metrics` |
| `statsd_exporter` | `statsd:9102` |
| `prometheus` | `prometheus:9090` |

## Visualization

The Streamlit UI renders native Altair charts from PromQL queries:

- System health indicators
- Pipeline status and timing
- Drift scores
- Hindcast accuracy gauge

The dashboard charts and the alerting rules use the same Prometheus metrics.

## Evidence Sources

| Source | Type | Location |
|--------|------|----------|
| Pipeline summaries | JSON | `airflow/reports/*-latest.json` |
| Prediction history | JSONL | `.state/monitoring/prediction-events.jsonl` (local) or BigQuery (cloud) |
| Hindcast results | JSON | `.state/monitoring/hindcast-validation.json` |
| Scrape + alert config | YAML | `prometheus_config/` (version-controlled) |

## Local vs Cloud

| Concern | Local | Cloud |
|---------|-------|-------|
| Metrics collection | Prometheus (Docker) | Managed Prometheus (GMP) |
| Scraping | `prometheus_config/prometheus.yml` | Cloud Run auto-scrape of `/metrics` |
| Drift emission | StatsD → exporter → Prometheus | Same `/metrics` endpoint (no StatsD needed) |
| Alerting | Prometheus alerting rules | Cloud Monitoring alerting policies |
| Visualization | Streamlit PromQL queries | Same Streamlit (different `FOEHNCAST_PROMETHEUS_URL`) |
| Prediction log | `.state/monitoring/` JSONL | BigQuery `foehncast_monitoring.prediction_events` |

The same `/metrics` endpoint serves both environments. Cloud Run v2 services expose Prometheus metrics to Managed Prometheus automatically via the Cloud Run metrics integration — no sidecar required.
