# Getting Started

This page keeps setup intentionally simple. The supported contributor path is the local evaluator flow with Docker. The shared cloud path is maintainer-only and documented separately.

## Default Path

This is the default path for almost every reader.

1. Install Docker.
2. Clone the repository.
3. Run `./scripts/bootstrap-local.sh`.

You do not need `gcloud`, Terraform, GitHub Actions variables, or a local compiler toolchain for this path.

<div class="mermaid">
flowchart TD
  DOCKER["fab:fa-docker Docker"] --> BOOT["./scripts/bootstrap-local.sh"]
  BOOT --> APP["FastAPI app"]
  BOOT --> AIR["Airflow"]
  BOOT --> MLF["MLflow"]
  BOOT --> MON["Prometheus + Grafana"]
  BOOT --> DATA["MinIO + Feast emulator"]
</div>

The bootstrap starts the local evaluator stack, waits for the feature-to-training hand-off, verifies starter monitoring resources, and prints alternate endpoints when default ports are busy. The optional `development_env` container stays off unless you explicitly ask for notebook or dev-shell workflows. See [Local Evaluator](system/local-evaluator.md) for the full runtime contract.

## Local Endpoints

| Surface | URL | Role |
|------|-----|------|
| App | `http://127.0.0.1:8000` | service surface for health, prediction, and ranking |
| App metrics | `http://127.0.0.1:8000/metrics` | service-owned monitoring surface |
| Airflow | `http://127.0.0.1:8080` | operator surface for orchestration |
| MLflow | `http://127.0.0.1:5001` | operator surface for runs and model versions |
| Prometheus | `http://127.0.0.1:9090` | operator surface for scraped metrics |
| Grafana | `http://127.0.0.1:3000` | operator surface for dashboards and alerts |
| Streamlit | `http://127.0.0.1:8501` | rider console with live rankings and model card |

The objectstore UI and the Feast emulator endpoint are printed by the bootstrap helper when the stack comes up. For the full surface boundary, use [Interfaces and Surfaces](system/interfaces-and-surfaces.md).

Example check:

```bash
curl -fsS -X POST http://127.0.0.1:8000/rank \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana","urnersee"]}'
```

## Maintainer Path

Most contributors can stop at the local evaluator path. If you maintain the shared cloud environment, start with [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md). The cloud path stays separate from the default contributor path and does not belong in the first-run setup.

Hosted deployment keeps the runtime scope tight. Runtime services deploy to the cloud path. Local notebooks, docs tooling, and local emulators stay local or CI-only.

## Read Next

- [Local Evaluator](system/local-evaluator.md) for the full local runtime contract.
- [Interfaces and Surfaces](system/interfaces-and-surfaces.md) for rider, service, and operator boundaries.
- [Repository](system/repository.md) for the project layout.
