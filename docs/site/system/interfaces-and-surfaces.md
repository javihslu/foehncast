# Interfaces and Surfaces

FoehnCast exposes several different kinds of surfaces, but they do not all serve the same audience or carry the same exposure expectations. This page records the current boundary between rider-facing demos, service endpoints, operator tools, and public-safe docs evidence so readers do not have to reconstruct that split from the landing page, architecture page, inference page, and monitoring page.

!!! note "Scope"

    This page describes the current validated surface boundary.
    It is not a proposal for a new product UI or admin model.
    New routes or tools should be placed into one of these surface classes explicitly.

## Surface Map

<div class="mermaid">
flowchart LR
    subgraph Rider["Rider-facing demo surfaces"]
        DASH[Streamlit rider console]
        DEMO[/features/online/demo]
    end

    subgraph Service["Service endpoints"]
        HEALTH[/health]
        SPOTS[/spots]
        PRED[/predict]
        RANK[/rank]
        FEAT[/features/online]
    end

    subgraph Operator["Operator surfaces"]
        MET[/metrics]
        AIR[Airflow]
        MLF[MLflow]
        PROM[Prometheus]
        GRAF[Grafana]
    end

    subgraph PublicSafe["Public-safe docs and evidence"]
        DOCS[Docs pages]
        EVID[Rendered summaries and screenshots]
    end

    DASH --> PRED
    DASH --> RANK
    DEMO --> FEAT
    PRED --> MET
    RANK --> MET
    MET --> PROM
    PROM --> GRAF
</div>

The important split is that not every HTTP route is rider-facing, and not every visible screen is safe to treat as public documentation.

## Current Surface Classes

| Surface class | Current examples | Primary audience | Default exposure |
|------|------------------|------------------|------------------|
| Rider-facing demo surfaces | Streamlit live demo and `/features/online/demo` | rider, reviewer, contributor | public-safe when shown as screenshots, rendered examples, or a deliberate local demo |
| Service endpoints | `/health`, `/spots`, `/predict`, `/rank`, and `/features/online` | clients, smoke tests, support services, and app-side integrations | service-only |
| Operator dashboards and control planes | `/metrics`, Airflow, MLflow, Prometheus, and Grafana | maintainer or deployment operator | private by default, except for the hosted app route itself |
| Public-safe docs and evidence | docs pages, rendered markdown, summary JSON-derived charts, and screenshots | reviewer, fork reader, course audience | public-safe |

This means a surface can be technically reachable without being part of the rider-facing product boundary. The clearest example is `/metrics`: it is an application endpoint, but it belongs to the operator monitoring contract rather than to the public product surface.

## Rider-Facing Demo Surfaces

The current rider-facing layer is intentionally small.

| Surface | What it does today | Must not become |
|------|---------------------|-----------------|
| Streamlit rider console | loads live predictions and rankings, shows configured rider profile, and presents rider-facing cards and tables | an operator dashboard or deployment control plane |
| `/features/online/demo` | gives a lightweight manual page that calls `/features/online` against the running app | the main product UI |

The Streamlit app is a real evaluation surface, not a separate hidden model path. It reuses the same prediction and ranking helpers as the API. The online-features demo is narrower: it exists to make the optional Feast-backed lookup path easy to test manually without turning that lookup into the product itself.

## Service API Surfaces

The current service API stays request-focused.

| Endpoint | Current responsibility |
|------|-------------------------|
| `/health` | report readiness plus the served model alias and model version |
| `/spots` | return the configured spot set |
| `/predict` | return per-spot forecast rows with continuous `quality_index` values |
| `/rank` | score the prediction payload for the configured rider profile |
| `/features/online` | return Feast-backed online feature rows for app-side integrations |

These endpoints are service surfaces, not hidden training or promotion paths. `/predict` and `/rank` schedule background monitoring work after they build the response payload, but they do not take on the rest of the operator monitoring stack.

## Operator Surfaces

The operator layer is where orchestration, tracking, monitoring, and review live.

| Surface | Current role |
|------|--------------|
| `/metrics` | expose the composed Prometheus payload for app-owned monitoring signals |
| Airflow | run and inspect feature and training orchestration |
| MLflow | track runs, model versions, and registry aliases |
| Prometheus | scrape time-series targets |
| Grafana | visualize dashboards and evaluate alert rules |

This operator layer stays separate from the rider-facing and public-docs layers on purpose. The checked-in monitoring config disables anonymous Grafana access, public dashboards, and embedding by default. The local bootstrap applies local-only overrides only so a local run can verify provisioning without changing the hosted policy.

## Public-Safe Docs And Evidence

The public docs site is a separate surface class, not a mirror of the live control plane.

Preferred public-safe evidence sources are:

- docs pages that summarize the current contracts
- rendered markdown excerpts and summary-derived charts
- screenshots of rider-facing or operator surfaces when explanation needs a picture
- persisted summary artifacts under `airflow/reports/` or retained event history under `.state/monitoring/` when you are showing structure rather than sensitive live state

Avoid treating these as public documentation surfaces:

- live Grafana embeds
- live Airflow or MLflow admin views
- private hosted operator URLs pasted directly into public docs

That rule keeps the docs understandable in review without leaking a live control plane into the public site.

## Exposure By Runtime Mode

| Runtime mode | Product or service surface | Operator-only surface |
|------|-----------------------------|-----------------------|
| Local evaluator | local app routes, local Streamlit demo, optional online-features demo | local Airflow, MLflow, Prometheus, and Grafana |
| Hosted full-stack target | no public app route by default | Airflow, MLflow, Prometheus, and Grafana stay private unless deliberately exposed |
| Hosted inference target | hosted inference API only | no hosted Airflow or MLflow container in that target |
| Public docs site | rendered docs and evidence only | no live control planes |

The shared hosted environment keeps the same rule as the docs: the app is the product and service surface, while operator tools stay private unless an operator intentionally publishes them.

## Why This Boundary Works

- it lets the rider-facing demo reuse the real serving path without turning the product into an admin console
- it keeps service endpoints narrow enough for smoke tests and client integrations
- it leaves orchestration, tracking, monitoring, and alerting on the operator side
- it gives the public docs stable evidence sources that do not depend on exposing private hosted dashboards

See [Architecture](architecture.md), [Delivery and Operator Workflow](delivery-and-operator-workflow.md), [Inference Pipeline](inference-pipeline.md), [Monitoring](monitoring.md), [Local Evaluator](local-evaluator.md), and [Hosted Full-Stack](hosted-full-stack.md) for the surrounding runtime contracts.
