# Getting Started

Two options: try the **live demo** (zero setup), or run everything **locally with Docker**.

## Option 1: Live Demo

These are running on GCP Cloud Run right now — just click:

| What | URL |
|------|-----|
| Streamlit UI | <https://foehncast-ui-290885878569.europe-west6.run.app/> |
| API | <https://foehncast-serve-290885878569.europe-west6.run.app/> |
| Prometheus metrics | <https://foehncast-serve-290885878569.europe-west6.run.app/metrics> |
| MLflow | <https://foehncast-mlflow-290885878569.europe-west6.run.app/> (needs IAM) |

## Option 2: Run Locally

### Prerequisites

- Docker (that's it)

### Steps

```bash
git clone https://github.com/javihslu/foehncast.git
cd foehncast
./scripts/bootstrap-local.sh
```

The script spins up everything and runs a smoke test. No cloud credentials needed.

<div class="mermaid">
flowchart TD
  DOCKER["Docker"] --> BOOT["bootstrap-local.sh"]
  BOOT --> APP["FastAPI app :8000"]
  BOOT --> AIR["Airflow :8080"]
  BOOT --> MLF["MLflow :5001"]
  BOOT --> MON["Prometheus :9090"]
  BOOT --> DATA["MinIO + Feast"]
</div>

### What You Get

| Service | URL |
|---------|-----|
| App (API) | `http://127.0.0.1:8000` |
| Airflow | `http://127.0.0.1:8080` |
| MLflow | `http://127.0.0.1:5001` |
| Prometheus | `http://127.0.0.1:9090` |
| Streamlit | `http://127.0.0.1:8501` |

### Test It

```bash
curl -X POST http://127.0.0.1:8000/rank \
  -H 'content-type: application/json' \
  -d '{"spot_ids":["silvaplana","urnersee"]}'
```

## For Maintainers

If you're deploying to GCP (not needed for evaluation), see:

- [Delivery Workflow](system/delivery-and-operator-workflow.md) — how CI/CD pushes to Cloud Run
- [Cloud Architecture](system/cloud-architecture.md) — what runs where in GCP

## Next Steps

- [Architecture](system/architecture.md) — how the FTI split works
- [Local Evaluator](system/local-evaluator.md) — more detail on the Docker stack
- [Repository](system/repository.md) — where to find things in the code
