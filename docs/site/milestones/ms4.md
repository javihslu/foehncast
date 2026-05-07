# MS4 Final Code

<span class="fc-pill fc-pill--progress">Final integration</span>

MS4 is the wrap-up milestone. The local stack already runs end to end with real forecast data, so the final work is integration: keep the validated backend intact while improving the hosted path, automation, monitoring, and public handoff.

## MS4 Focus

| Area | Current baseline | MS4 objective |
|------|------------------|---------------|
| Architecture | Feature, training, and inference modules run together locally | Preserve the same split in the hosted path |
| Reproducibility | Docker Compose and `bootstrap-local.sh` provide a clean local path | Keep the cloud setup aligned with Terraform and the docs |
| Automation | Airflow DAGs run locally and deployment scaffolding exists | Tighten the repeatable online deployment flow |
| Monitoring | Minimal baseline | Add enough service and model visibility for the final handoff |

## Wrap-Up Roadmap

<div class="mermaid">
flowchart LR
    LOCAL[Local real-data execution] --> DOCS[Simple public docs and demo path]
    DOCS --> CLOUD[Cloud data and runtime mapping]
    CLOUD --> AUTO[Automation and repeatable delivery]
    AUTO --> MON[Monitoring and final freeze]
</div>

## What MS4 Should Demonstrate

- The local stack is not a mock-up. It already executes the real pipeline split.
- The cloud plan reuses the validated modules instead of inventing a new architecture.
- The last step is operational maturity: repeatable delivery, monitoring, and final packaging.

## Current Integration Priorities

| Priority | Why it matters |
|----------|----------------|
| Simpler public documentation | the repo and docs should explain the system quickly without burying the core story |
| Cleaner hosted operator path | cloud setup should stay repeatable and easier to reason about than ad hoc manual steps |
| Stronger automation | the remote Terraform and image-publishing flow should remain the default repeatable delivery path |
| Enough monitoring for handoff | the final submission should show service and model visibility, not just raw deployment |

See [Cloud Mapping](../system/cloud-mapping.md) for the hosted direction and [Getting Started](../getting-started.md) for the operator-facing setup split.
