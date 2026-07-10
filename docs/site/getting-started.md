# Quick Start

Two options: try the **live demo** (zero setup), or run everything **locally with Docker**.

## Option 1: Hosted Demo (offline)

The GCP Cloud Run deployment ran for the course duration and has been taken
down to avoid idle cost. The local stack below provides the same system, and
the [Cloud Deployment](system/cloud-architecture.md) page documents how to
deploy your own copy with Terraform.

## Option 2: Run Locally

### Prerequisites

- Docker

### Steps

```bash
git clone https://github.com/javihslu/foehncast.git
cd foehncast
./scripts/bootstrap-local.sh
```

The script starts the local stack and runs a smoke test. No cloud credentials are needed.

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

- [Operator Runbook](system/delivery-and-operator-workflow.md) — how CI/CD pushes to Cloud Run
- [Cloud Deployment](system/cloud-architecture.md) — what runs where in GCP

## Next Steps

- [Architecture](system/architecture.md) — how the FTI split works
- [Local Stack](system/local-evaluator.md) — more detail on the Docker stack
- [Repository](system/repository.md) — where to find things in the code
