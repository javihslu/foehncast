# Interfaces

FoehnCast exposes different things to different audiences. This page clarifies what's public, what's internal, and what's just for operators.

## Who Sees What

<div class="mermaid">
flowchart TD
    classDef public fill:#f1f5f9,stroke:#475569
    classDef service fill:#e6f4f1,stroke:#0f766e
    classDef operator fill:#fff4e6,stroke:#c2410c

    RIDER["User-facing: Streamlit UI"]:::public
    SERVICE["API routes: /health, /predict, /rank, /spots"]:::service
    OPERATOR["Internal: /metrics, Airflow, MLflow, Prometheus"]:::operator
    DOCS["Public docs: this website, screenshots"]:::public

    RIDER --> SERVICE
    SERVICE --> OPERATOR
    OPERATOR -. "screenshots only" .-> DOCS
</div>

## Surface Types

| Type | Examples | Who uses it | Access |
|------|----------|-------------|--------|
| User-facing | Streamlit UI, `/features/online/demo` | Users, reviewers | Public |
| API endpoints | `/health`, `/predict`, `/rank`, `/spots` | Clients, tests | Public |
| Operator tools | `/metrics`, Airflow, MLflow, Prometheus | Maintainers | Private |
| CI/CD | GitHub Actions, Terraform | Maintainers | Review-gated |
| Documentation | This site, screenshots | Everyone | Public |

## Key Rules

- `/metrics` is **not** user-facing — it's an operator endpoint
- Streamlit is rider-facing; its System tab adds light run controls (trigger the pipeline, view run history — Airflow DAGs locally, the Cloud Workflows cascade in cloud), but it is not a deployment or infra console
- GitHub Actions handles delivery, not runtime scheduling
- Public docs use screenshots or rendered data, never live embeds of Airflow/MLflow/Prometheus

## By Environment

| Environment | Public | Private |
|-------------|--------|---------|
| Local | FastAPI app, Streamlit | Airflow, MLflow, Prometheus |
| Cloud | Cloud Run API, Streamlit UI | MLflow, monitoring |
| Docs site | Rendered pages | Nothing live |

Same principle everywhere: the app is the product, operator tools stay behind the curtain.
