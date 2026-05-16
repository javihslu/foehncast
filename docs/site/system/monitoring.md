# Monitoring

FoehnCast keeps monitoring as an operator surface, not a rider-facing one. The monitoring stack turns pipeline summaries, prediction events, drift signals, and serving health into scrapeable metrics and checked-in alert rules.

This page describes what is measured, where the evidence comes from, and how operators verify it.

!!! note "Scope"

    This page describes the validated monitoring contract.
    It focuses on monitoring evidence and boundaries.
    It does not redefine orchestration or the hosted build.

## Signal Path

<div class="mermaid">
flowchart LR
    subgraph Sources ["Evidence sources"]
        direction TB
        AIR["Airflow pipeline summaries"]
        PRED["Prediction requests"]
        SYNC["Hosted sync status"]
    end

    subgraph Processing ["Metric composition"]
        direction TB
        APP["App /metrics endpoint"]
        LOG["Prediction log + event history"]
        DRIFT["Evidently drift detection"]
        STATSD["StatsD exporter"]
    end

    subgraph Operator ["Operator tooling"]
        direction TB
        PROM["Prometheus"]
        GRAFANA["Grafana dashboards"]
        ALERT["Alert rules"]
    end

    AIR --> APP
    PRED --> LOG
    SYNC --> APP
    LOG --> APP
    LOG --> DRIFT
    DRIFT --> STATSD
    APP --> PROM
    STATSD --> PROM
    PROM --> GRAFANA
    PROM --> ALERT
</div>

Monitoring consumes persisted or runtime state after the pipeline and serving paths run. It does not own feature engineering, model scoring, or orchestration.

## Runtime Role

| Runtime mode | Monitoring contract |
|------|---------------------|
| Local evaluator | app `/metrics`, StatsD drift export, persisted pipeline summaries, and local Grafana dashboards validate the full monitoring path on one machine |
| Shared hosted environment | Cloud Run exposes `/metrics`; the operator lane keeps Prometheus, Grafana, and hosted sync evidence online |
| Public docs | rendered metrics snippets, checked-in configs, and summary artifacts explain the contract without live control planes |

The public-versus-private surface rule is documented in [Interfaces and Surfaces](interfaces-and-surfaces.md).

## Evidence Sources

| Source | Kind | What it shows |
|------|------|---------------|
| `airflow/reports/*.json` | durable | latest feature and training pipeline summaries plus history |
| `.state/monitoring/prediction-events.jsonl` | durable | prediction-event history by model version (local S3-backed runtimes) |
| `foehncast_monitoring.prediction_events` BigQuery table | durable | prediction-event history (Cloud Run and cloud-native readers) |
| `.state/monitoring/prediction-log.jsonl` | bounded working set | recent prediction rows for local drift evaluation; not a history source |
| `.state/hosted-sync/last-success.json` | durable | latest hosted sync success marker |
| app `/metrics` | composed scrape | app-owned monitoring state and summary-derived metrics |
| StatsD exporter `:9102` | scrape | Evidently-backed drift metrics |

Durable files survive restarts and support audits. Runtime counters on `/metrics` describe process health and reset with the process.

## Metrics

The serving application publishes one composed Prometheus payload on `/metrics`:

<div class="mermaid">
flowchart LR
    subgraph App ["/metrics payload"]
        direction TB
        FPS["Feature pipeline summary gauges"]
        TPS["Training pipeline summary gauges"]
        PHS["Prediction history gauges"]
        PMC["Prediction monitoring counters"]
        HSS["Hosted sync status"]
        REG["Registered model version"]
    end

    subgraph StatsD ["StatsD path"]
        direction TB
        EVD["Evidently drift report"]
        SDE["StatsD exporter"]
    end

    FPS --> PROM["Prometheus"]
    TPS --> PROM
    PHS --> PROM
    PMC --> PROM
    HSS --> PROM
    REG --> PROM
    EVD --> SDE --> PROM
</div>

Key metric families:

| Metric prefix | Source | Labels |
|------|--------|--------|
| `foehncast_feature_pipeline_*` | persisted `airflow/reports/` summaries | `dataset`, `storage_backend` |
| `foehncast_training_pipeline_*` | persisted training summaries | `dataset` |
| `foehncast_prediction_monitoring_*` | in-process counters (ephemeral) | `endpoint`, `result` |
| `foehncast_drift_metric` | Evidently via StatsD | column-level drift scores |

Feature and training summary metrics include per-stage state gauges (`succeeded`, `failed`, `not_run`), spot counts, row counts, duration gauges, and failure counts. Prediction monitoring counters track background task scheduling and execution attempts.

## Drift Detection

Drift detection uses Evidently to compare reference and current datasets, then exports results through StatsD.

| Drift kind | Reference | Current | Method |
|------|-----------|---------|--------|
| Feature drift | stored reference feature dataset | latest curated features | column-level statistical tests via Evidently |
| Prediction drift | historical prediction events | recent prediction window | comparison across `prediction-events.jsonl` or the BigQuery warehouse contract |

Emitted StatsD metrics are mapped into Prometheus as `foehncast_drift_metric`. The StatsD host defaults to `127.0.0.1:8125` and can be overridden through `monitoring.statsd_host` in `config.yaml`.

## Scrape Configuration

Prometheus scrapes four targets, all checked in at `prometheus_config/prometheus.yml`:

| Job | Target | What it collects |
|------|--------|------------------|
| `foehncast_app` | `app:8000/metrics` | app-owned pipeline, prediction, and sync metrics |
| `statsd_exporter` | `statsd:9102` | Evidently drift metrics |
| `grafana` | `grafana:3000/metrics` | Grafana self-monitoring |
| `prometheus` | `prometheus:9090` | Prometheus self-monitoring |

Scrape interval is 15 seconds. Alert rules are evaluated at the same interval.

## Alert Rules

The checked-in rules at `prometheus_config/alerting_rules.yml` cover four failure modes:

| Alert | Severity | Trigger | What it guards |
|------|----------|---------|----------------|
| `AppDown` | critical | app target unreachable for 2 min | serving availability |
| `HighRequestLatency` | warning | p95 latency above 2 s for 5 min | request performance |
| `PredictionErrorRateHigh` | warning | error rate above 0.1/s for 5 min | prediction reliability |
| `StatsdExporterDown` | warning | StatsD target unreachable for 5 min | drift pipeline availability |

All rules, the contact point, and the alert routing policy are checked into the repository so the alerting contract is reviewable without a live Grafana instance.

## Dashboards

Grafana is provisioned from the repository-owned dashboard at `grafana_work/dashboards/foehncast-overview.json`. The dashboard covers:

- feature pipeline summary count and latest run success by dataset and backend
- failed spot counts
- monitoring target health

Dashboard JSON and provisioning config are version-controlled so the operator view is reproducible from a fresh `docker compose up`.

## Recovery Evidence

Recovery work should leave durable evidence that operators can compare before and after the intervention.

| Recovery task | Evidence | Check |
|------|----------|-------|
| Feature retry or backfill | latest feature summary JSON | summary timestamp advances |
| Training follow-up | latest training summary JSON | stage and model version are recorded |
| Deploy, promote, or rollback | latest runtime-release summary | GitHub summary and runtime acknowledgement match |
| Hosted sync refresh | latest sync status file | sync state updates on `/metrics` |

Capture the run reference with the summary artifacts: the GitHub workflow URL for reviewed delivery, or the logical date and DAG run id for hosted Airflow recovery. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for retry and backfill procedures.

## Public-Safe Evidence

Explain monitoring with rendered evidence, not live control-plane embeds:

- rendered `/metrics` snippets or screenshots
- checked-in Prometheus scrape and alert configs
- checked-in Grafana dashboards
- pipeline summary JSON artifacts under `airflow/reports/`
- prediction-event file structure under `.state/monitoring/`

This keeps public docs understandable in review while leaving live Grafana, Prometheus, and Airflow as operator tools.

## Why This Structure Works

- operator monitoring stays separate from the rider-facing app
- durable evidence survives restarts without turning runtime state into product data
- alerting is reviewable because dashboards, rules, and scrape config live in git
- the monitoring boundary stays stable even while hosted operator surfaces change
- one `/metrics` surface describes the app-owned contract while StatsD handles drift export

See [Architecture](architecture.md), [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Feature Pipeline](feature-pipeline.md), and [Getting Started](../getting-started.md) for the surrounding system and local operator path.
