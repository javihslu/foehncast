# Monitoring

FoehnCast keeps monitoring as an operator surface, not a rider-facing one. The monitoring stack turns pipeline summaries, retained prediction events, drift signals, and hosted sync state into scrapeable metrics and checked-in alert rules.

This page describes what is measured, where the evidence comes from, and how operators verify it.

!!! note "Scope"

    This page describes the validated monitoring contract.
    It focuses on the monitoring evidence and boundaries.
    It does not treat the retained host as the desired long-term hosted control plane.

## Signal Path

<div class="mermaid">
flowchart LR
    AIR["Airflow pipeline summaries"] --> APP["App /metrics"]
    PRED["Prediction requests"] --> LOG["Prediction log and event history"]
    LOG --> DRIFT["Evidently drift checks"]
    DRIFT --> STATSD["StatsD exporter"]
    SYNC["Hosted sync status file"] --> APP
    LOG --> APP
    APP --> PROM["Prometheus"]
    STATSD --> PROM
    PROM --> GRAFANA["Grafana"]
    GRAFANA --> DASH["Dashboards and alert rules"]
</div>

The important split is that monitoring consumes persisted or runtime monitoring state after the pipeline and serving paths run. It does not own feature engineering, model scoring, or orchestration itself.

## Monitoring By Runtime Mode

| Runtime mode | Monitoring contract | Exposure boundary |
|------|---------------------|-------------------|
| Local evaluator | app `/metrics`, StatsD drift export, persisted pipeline summaries, and local Grafana dashboards validate the full monitoring path on one machine | local-only |
| Shared hosted environment | Cloud Run exposes the app-owned `/metrics` contract, while the active operator lane keeps Prometheus, Grafana, hosted sync evidence, and operator review online until the managed hosted control plane absorbs more of that work | operator stack stays private by default |
| Public docs | rendered metrics snippets, screenshots, checked-in configs, and summary artifacts explain the monitoring contract | no live control planes |

The public-versus-private surface rule itself is documented in [Interfaces and Surfaces](interfaces-and-surfaces.md). This page stays focused on what monitoring measures and how operators verify it.

## Evidence Sources

| Source | Kind | What it shows |
|------|------|---------------|
| `airflow/reports/*.json` | durable evidence | latest feature and training pipeline summaries plus history |
| `.state/monitoring/prediction-events.jsonl` | durable evidence | retained prediction-event history by model version |
| `.state/monitoring/prediction-log.jsonl` | durable working set | recent prediction history for prediction-side drift evaluation |
| `.state/online-compose-sync/last-success.json` | durable evidence | latest hosted sync success marker |
| app `/metrics` | composed scrape surface | app-owned monitoring state and summary-derived metrics |
| StatsD exporter | scrape surface | Evidently-backed drift metrics |
| Prometheus and Grafana | operator tooling | time-series storage, dashboards, and alert evaluation |

Durable files survive restarts and support audits. Runtime counters on `/metrics` describe process health and reset with the process.

## Metrics And Drift

The serving application publishes one composed Prometheus payload on `/metrics`. It includes feature and training summary metrics, retained prediction-history metrics, hosted sync status metrics, and in-process scheduling or execution counters.

Drift detection is backed by Evidently and exported through StatsD. Feature drift compares reference and current feature datasets on shared columns. Prediction drift compares retained prediction history across reference and recent windows. Emitted StatsD metrics are mapped into Prometheus as `foehncast_drift_metric`.

This keeps the operator scrape path simple: Prometheus reads the app surface for app-owned monitoring state and the StatsD exporter for drift metrics.

## Dashboards And Alerts

Prometheus scrapes the app on `/metrics`, the StatsD exporter, and Grafana itself. Grafana is provisioned from repository-owned dashboards and alert rules.

The checked-in dashboard covers pipeline summary counts, stage durations and failures, feature and inference drift share, retained prediction-log size and model coverage, prediction-monitoring schedule failures, and seconds since the last hosted sync.

## Alert Rules

The checked-in alert rules cover the main operator failure modes.

| Rule family | What it guards |
|------|-----------------|
| Prediction Monitoring Schedule Failures | background monitoring jobs that fail to schedule for one endpoint |
| Prediction Monitoring Execution Failures | background monitoring jobs that start but fail during execution |
| Prediction Monitoring Stale Success | endpoints that keep scheduling work without recording a recent successful execution |
| Feature Stage Failures | persisted feature-pipeline stage failure counts |
| Training Stage Failures | persisted training-pipeline stage failure counts |
| Hosted Sync Stale | hosted compose sync status that has not reported a recent success |

The contact point and policy tree stay checked in too, so the alert routing contract is reviewable without depending on a live Grafana instance.

## Recovery Evidence

Recovery work should leave durable evidence that operators can compare before and after the intervention.

| Recovery task | Evidence | Check |
|------|----------|-------|
| feature retry or backfill | latest feature summary JSON plus history | summary timestamp advances and the feature-stage alert clears |
| training follow-up after a replay | latest training summary JSON plus history | stage and model version are recorded and the training-stage alert clears |
| deploy, promote, or rollback handoff retry | latest runtime-release summary JSON plus history | GitHub summary and runtime acknowledgement match |
| retained operator host refresh verification | latest sync status file | hosted-sync stale signal clears and `/metrics` republishes the new sync state |

Capture the initiating run reference with the summary artifacts: the GitHub workflow URL for reviewed delivery, or the logical date and DAG run id for hosted Airflow recovery.

These checks stay intentionally small. They give operators one repeatable evidence pack without turning the monitoring stack into the system that performs the recovery itself. See [Delivery and Operator Workflow](delivery-and-operator-workflow.md) for the retry and backfill procedures.

## Public-Safe Evidence

Explain monitoring with rendered evidence, not live control-plane embeds.

- rendered `/metrics` snippets or screenshots
- checked-in Prometheus scrape config
- checked-in Grafana dashboards and alert rules
- pipeline summary JSON artifacts under `airflow/reports/`
- retained prediction-event files under `.state/monitoring/` when showing structure rather than sensitive runtime data

This keeps the public docs understandable in review while leaving live Grafana, Prometheus, and Airflow as operator tools.

## Why This Structure Works

- it keeps operator monitoring separate from the rider-facing app and docs pages
- it preserves durable monitoring evidence across restarts without turning runtime state into product data
- it keeps alerting reviewable because dashboards, rules, and scrape config live in git
- it keeps the monitoring boundary stable even while the hosted operator surface changes underneath it
- it lets one `/metrics` surface describe the app-owned monitoring contract while StatsD handles Evidently drift export

See [Architecture](architecture.md), [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Feature Pipeline](feature-pipeline.md), and [Getting Started](../getting-started.md) for the surrounding system and local operator path.
