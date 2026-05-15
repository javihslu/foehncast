# Interfaces and Surfaces

FoehnCast exposes five surface classes: rider, service, operator, delivery, and public-safe docs. This page defines who each surface is for and what should stay private.

!!! note "Scope"

    This page defines exposure boundaries.
    Use runtime pages for deployed targets.
    Use workflow pages for maintainer procedures.

## Surface Map

<div class="mermaid">
flowchart LR
    classDef public fill:#f5f5f5,stroke:#333
    classDef service fill:#e1f5fe,stroke:#01579b
    classDef operator fill:#fff8e1,stroke:#f57f17
    classDef evidence fill:#ececff,stroke:#9370db

    RIDER["Rider demos<br/>Streamlit and /features/online/demo"]:::public
    SERVICE["Service routes<br/>/health, /spots, /predict, /rank, /features/online"]:::service
    OPERATOR["Private operator surfaces<br/>/metrics, Airflow, MLflow, Prometheus, Grafana"]:::operator
    DELIVERY["fab:fa-github Delivery<br/>GitHub Actions, Terraform, bootstrap"]:::public
    EVIDENCE["Public-safe evidence<br/>Docs, summaries, screenshots"]:::evidence

    RIDER --> SERVICE
    DELIVERY --> SERVICE
    SERVICE --> OPERATOR
    OPERATOR -. "Rendered outputs only" .-> EVIDENCE
</div>

The important split is simple: not every HTTP route is rider-facing, and not every visible screen is safe to treat as public documentation.

## Surface Classes

| Surface class | Examples | Main audience | Default exposure |
|------|----------|---------------|------------------|
| Rider-facing demo surfaces | Streamlit rider console and `/features/online/demo` | rider, reviewer, contributor | public-safe when shown as screenshots, rendered examples, or a deliberate local demo |
| Service endpoints | `/health`, `/spots`, `/predict`, `/rank`, and `/features/online` | clients, smoke tests, and app-side integrations | service-only |
| Operator surfaces | `/metrics`, Airflow, MLflow, Prometheus, and Grafana | maintainer or deployment operator | private by default |
| Delivery surfaces | GitHub Actions, Terraform, and bootstrap helpers | maintainer | review-controlled and not runtime-facing |
| Public-safe docs and evidence | docs pages, rendered summaries, and screenshots | reviewer, fork reader, course audience | public-safe |

## Exposure Rules

- `/metrics` is an operator surface even though it is an app route.
- Streamlit and `/features/online/demo` are evaluation surfaces, not deployment control planes.
- GitHub Actions and Terraform advance reviewed delivery, but they do not own runtime scheduling, retries, or backfills.
- Public docs should use rendered evidence or screenshots instead of live Airflow, MLflow, Prometheus, or Grafana views.

## Exposure By Runtime Mode

| Runtime mode | Product or service surface | Operator-only surface |
|------|-----------------------------|-----------------------|
| Local evaluator | local app routes, local Streamlit demo, and the optional online-features demo | local Airflow, MLflow, Prometheus, and Grafana |
| Shared API lane | hosted inference API only | no hosted Airflow or MLflow container in that target |
| Operator lane | no public app route by default | Airflow, MLflow, Prometheus, and Grafana stay private unless deliberately exposed |
| Public docs site | rendered docs and evidence only | no live control planes |

The same split applies in local and cloud runtimes: app routes form the product and service surface, while operator tools stay private unless an operator intentionally publishes them.

## Why This Boundary Works

- it lets the rider-facing demo reuse the real serving path without turning the product into an admin console
- it keeps service endpoints narrow enough for smoke tests and client integrations
- it keeps orchestration, tracking, monitoring, and alerting on the operator side
- it gives the public docs stable evidence sources that do not depend on exposing private hosted dashboards

See [Architecture](architecture.md), [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Inference Pipeline](inference-pipeline.md), [Monitoring](monitoring.md), [Local Evaluator](local-evaluator.md), and [Hosted Full-Stack](hosted-full-stack.md) for the surrounding runtime contracts.
