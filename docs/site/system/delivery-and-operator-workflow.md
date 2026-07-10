# Operator Runbook

Contributors run locally with Docker. Maintainers deploy to GCP through GitHub Actions + Terraform. This page explains both paths.

## Two Paths

<div class="mermaid">
flowchart TD
    subgraph Contributor ["Contributor (everyone)"]
        direction LR
        CLONE["Clone repo"] --> LOCAL["bootstrap-local.sh"] --> DONE["Local stack running"]
    end

    subgraph Maintainer ["Maintainer (cloud deploy)"]
        direction LR
        SHELL["Cloud Shell"] --> BGCP["bootstrap-gcp.sh"] --> TF["Terraform + Actions"]
        TF --> RUN["Cloud Run"]
    end
</div>

| Path | Who | Tools needed | Result |
|------|-----|-------------|--------|
| Local | Everyone | Docker only | Full local stack |
| Cloud bootstrap | Maintainer (once) | `gcloud`, Cloud Shell | Remote TF backend + repo vars |
| Day-2 delivery | Maintainer | GitHub Actions + Terraform | Updated cloud services |

## Contributor Path

```bash
git clone ... && cd foehncast && ./scripts/bootstrap-local.sh
```

No `gcloud`, no Terraform, no GitHub secrets needed.

## Cloud Bootstrap (One-Time)

Run from Google Cloud Shell:

```bash
./scripts/bootstrap-gcp.sh --bootstrap-only --configure-github-actions
```

This is interactive — it walks you through project/billing setup, creates the Terraform backend, and syncs repo variables to GitHub.

## Day-2 Delivery

After bootstrap, everything goes through GitHub Actions:

| Workflow | What it does |
|----------|-------------|
| `terraform.yml` | Plan/apply/destroy infrastructure |
| Cloud Build triggers | Build and push container images (GCP-native) |

Repository variables store project IDs, bucket names, and Cloud Run settings. No secrets in repo vars — those stay in runtime env or Secret Manager.

## Orchestration

Airflow (local Docker Compose) handles:

- DAG scheduling and retries
- Asset-triggered pipeline runs
- Runtime release handoff

Cloud Workflows + Scheduler handle cloud-side automation.

## Runtime Release

Model promotion and rollback use a single script:

```bash
scripts/trigger-runtime-release.sh <action> <coordinates>
```

Actions: `deploy_candidate`, `promote_candidate`, `rollback_live`

The script calls the Airflow API, waits for the DAG to finish, and captures the result.

## Retry Runbook

| Problem | Where to fix | How |
|---------|-------------|-----|
| Terraform or image build fails | GitHub Actions | Fix input, rerun workflow |
| Feature pipeline fails | Local Airflow | Retrigger with explicit logical date |
| Training needs rerun | Local Airflow | Manual `training_pipeline` run |
| Deploy/promote/rollback fails | Local terminal | Rerun the trigger script |

## GitHub vs. GCP Boundary

| GitHub owns | GCP owns |
|-------------|----------|
| Source, lint, test | Runtime serving |
| Terraform plan/apply | Image builds (Cloud Build) |
| Reviewed delivery | Metrics and telemetry |
| | Cloud Run responses |
| | Runtime scheduling |

GitHub owns CI and infrastructure declarations. GCP owns builds, serving, and runtime.
