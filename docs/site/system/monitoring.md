# Monitoring

FoehnCast keeps monitoring as an operator surface, not a rider-facing one. The monitoring stack turns pipeline summaries, retained prediction events, drift signals, and hosted sync state into scrapeable metrics and checked-in alert rules without changing the runtime contracts those signals describe.

This page records the current monitoring design that is validated in the local stack and in regression tests. It focuses on what is measured today, where the evidence comes from, and how the operator path stays separate from the public docs surface.

!!! note "Scope"

    This page describes the current validated monitoring contract.
    It is not a roadmap.
    Future changes should be documented after they are chosen and implemented.

## Signal Path

<div class="mermaid">
flowchart LR
    AIR[Airflow pipeline summaries] --> APP[/App /metrics/]
    PRED[Prediction requests] --> LOG[Prediction log and event history]
    LOG --> DRIFT[Evidently drift checks]
    DRIFT --> STATSD[StatsD exporter]
    SYNC[Hosted sync status file] --> APP
    LOG --> APP
    APP --> PROM[Prometheus]
    STATSD --> PROM
    GRAFANA[Grafana] --> PROM
    PROM --> DASH[Dashboards and alert rules]
</div>

The important split is that monitoring consumes persisted or runtime monitoring state after the pipeline and serving paths run. It does not own feature engineering, model scoring, or orchestration itself.

## Monitoring By Runtime Mode

| Runtime mode | What is monitored | What stays private |
|------|-------------------|--------------------|
| Local evaluator | app `/metrics`, StatsD drift export, local pipeline summaries, and local Grafana dashboards | local Airflow, MLflow, Prometheus, and Grafana remain operator tools |
| Active shared environment | app `/metrics`, hosted sync state, and the hosted monitoring stack on the compose host | Airflow, MLflow, Prometheus, and Grafana stay private by default |
| Public docs | rendered metrics snippets, screenshots, checked-in configs, and summary artifacts | no live control planes |

This keeps the public explanation clear: operators use the monitoring stack directly, while the docs site uses rendered evidence.

## Surface Roles

| Surface | What it exposes | Why it matters |
|------|------------------|----------------|
| `airflow/reports/*.json` | latest feature and training pipeline summaries plus timestamped history | gives the app and operator tooling a stable pipeline-run contract |
| `.state/monitoring/prediction-events.jsonl` | retained prediction-event history by model version | preserves inference evidence across restarts |
| `.state/monitoring/prediction-log.jsonl` | bounded working set used for prediction-side drift evaluation | keeps drift windows small enough for local evaluation |
| `.state/online-compose-sync/last-success.json` | latest hosted sync success marker | lets operators detect stale hosted updates |
| app `/metrics` | pipeline summaries, retained prediction history, hosted sync state, and in-process monitoring counters | gives Prometheus one stable scrape surface for app-owned monitoring state |
| StatsD exporter | drift metrics pushed from Evidently-backed checks | keeps drift signals scrapeable without inventing a second app-owned registry |
| Prometheus and Grafana | time-series storage, dashboard panels, and alert evaluation | provides the operator view and alerting layer |

## Durable And Ephemeral Signals

The monitoring stack uses both durable and ephemeral signals on purpose.

Durable signals survive restarts and provide historical evidence:

- feature and training pipeline summaries under `airflow/reports/`
- timestamped summary history alongside the latest pipeline summaries
- retained prediction-event history in `.state/monitoring/prediction-events.jsonl`
- hosted compose sync status in `.state/online-compose-sync/last-success.json`

Ephemeral signals are runtime-only counters that reset on restart:

- prediction-monitoring schedule counts
- prediction-monitoring execution counts
- last successful background monitoring execution timestamps

The app combines both kinds of signals on `/metrics`, but the distinction still matters operationally. Durable files support audits and restarts; ephemeral counters describe the current process health.

## Metrics Surface

The serving application publishes one composed Prometheus payload on `/metrics`.

That payload includes:

- feature pipeline summary metrics rendered from the latest persisted summary
- training pipeline summary metrics rendered from the latest persisted summary
- retained prediction-log metrics grouped by model version
- hosted online-compose sync status metrics
- in-process prediction-monitoring counters for scheduling and execution outcomes

This keeps the operator scrape path simple: Prometheus reads the app surface for app-owned monitoring state and the StatsD exporter for drift metrics.

## Drift Monitoring

Drift detection is backed by Evidently and exported through StatsD.

The current contract is:

- feature drift compares reference and current feature datasets on shared columns
- prediction drift compares retained prediction history across reference and recent windows
- drift thresholds and evaluation windows come from the monitoring config, with validated fallbacks in code
- emitted StatsD metrics are mapped into Prometheus as `foehncast_drift_metric`

This means the Grafana dashboard can show both dataset-level drift share and column-level drift signals without making the app own another custom metric family.

## Prometheus And Grafana

The checked-in Prometheus config scrapes three operator targets:

- the app on `/metrics`
- the StatsD exporter
- Grafana itself

Grafana is provisioned from repository-owned dashboards and alert rules. The validated monitoring dashboard includes panels for:

- feature and training pipeline summary counts
- stage durations and stage failure counts
- feature and inference drift share
- retained prediction-log size and model coverage
- prediction-monitoring schedule failures
- seconds since the last hosted sync

That makes the dashboard a view over checked-in metrics contracts rather than a manually assembled local-only artifact.

The same dashboard contract works in the local evaluator and in the active shared environment. What changes is the runtime around it, not the meaning of the monitored signals.

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

## Recovery Evidence And Runbook Checks

Retry and backfill work should leave durable evidence that operators can compare before and after the intervention.

| Recovery task | Durable evidence to capture | Operator check |
|------|-----------------------------|----------------|
| feature retry or backfill | `airflow/reports/feature-pipeline-<dataset>-latest.json` plus the matching history file | the latest summary timestamp advances and the feature-stage failure alert clears |
| training follow-up after a replay | `airflow/reports/training-pipeline-<dataset>-latest.json` plus the matching history file | the summary records the requested stage, registered model version, and no training-stage failure alert remains |
| reviewed deploy, promote, or rollback handoff retry | `airflow/reports/runtime-release-latest.json` plus the matching history file | the GitHub workflow summary and the runtime-side acknowledgement describe the same action and coordinates |
| retained operator host refresh verification | `.state/online-compose-sync/last-success.json` | the hosted-sync stale signal clears and the app republishes the updated sync state on `/metrics` |

When the recovery started from reviewed delivery, capture the GitHub workflow URL too. When the recovery started from hosted Airflow, capture the logical date and DAG run id with the summary artifacts.

These checks are intentionally small. They give operators one repeatable evidence pack without turning the monitoring stack into the system that performs the retry itself.

## Reading Evidence Safely

The docs site should explain monitoring with rendered evidence, not live control-plane embeds.

Preferred public-safe evidence sources are:

- rendered `/metrics` snippets or screenshots
- the checked-in Prometheus scrape config
- the checked-in Grafana dashboard and alert-rule definitions
- pipeline summary JSON artifacts under `airflow/reports/`
- retained prediction-event files under `.state/monitoring/` when showing structure rather than sensitive runtime data

This keeps the public docs understandable in review while leaving live Grafana, Prometheus, and Airflow as operator tools.

## Why This Structure Works

- it keeps operator monitoring separate from the rider-facing app and docs pages
- it preserves durable monitoring evidence across restarts without turning runtime state into product data
- it keeps alerting reviewable because dashboards, rules, and scrape config live in git
- it lets one `/metrics` surface describe the app-owned monitoring contract while StatsD handles Evidently drift export

See [Architecture](architecture.md), [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Feature Pipeline](feature-pipeline.md), and [Getting Started](../getting-started.md) for the surrounding system and local operator path.
