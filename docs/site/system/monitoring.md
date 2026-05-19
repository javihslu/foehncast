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

## Alert Rules

9 rules in `prometheus_config/alerting_rules.yml`:

| Alert | Fires when |
|-------|-----------|
| `AppDown` | App unreachable for 2 min |
| `HighRequestLatency` | p95 > 2s for 5 min |
| `PredictionErrorRateHigh` | Error rate > 0.1/s for 5 min |
| `StatsdExporterDown` | StatsD target gone for 5 min |
| `PredictionMonitoringScheduleFailure` | Background scheduling fails |
| `PredictionMonitoringExecutionFailure` | Background execution fails |
| `FeaturePipelineStageFailure` | Any feature stage fails |
| `TrainingPipelineStageFailure` | Any training stage fails |
| `HostedSyncStale` | No sync success for 15 min |

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

All charts read from the same metrics that alerts fire on — so what you see matches what triggers.

## Evidence Sources

| Source | Type | Location |
|--------|------|----------|
| Pipeline summaries | JSON | `airflow/reports/*-latest.json` |
| Prediction history | JSONL | `.state/monitoring/prediction-events.jsonl` (local) or BigQuery (cloud) |
| Hindcast results | JSON | `.state/monitoring/hindcast-validation.json` |
| Scrape + alert config | YAML | `prometheus_config/` (version-controlled) |

## Related Pages

- [Architecture](architecture.md) — where monitoring fits
- [Inference Pipeline](inference-pipeline.md) — generates prediction events
- [Grading Checklist](grading-checklist.md) — monitoring evidence for grading
