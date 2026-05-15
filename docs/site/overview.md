# Overview

FoehnCast is a local-first ML system for deciding where to kite next. This page explains how the system is organized, how the docs are split, and where local and cloud designs stay the same or differ.

## Shared System Core

<div class="mermaid">
flowchart LR
  %% Branded colors
  classDef app fill:#222,stroke:#333,color:#fff
  classDef data fill:#ececff,stroke:#9370db,color:#000
  classDef pipeline fill:#e1f5fe,stroke:#01579b,color:#000
  classDef registry fill:#fff,stroke:#d32f2f,color:#000

  DATA["Raw Forecasts"]:::data

  subgraph BuildPath ["Build path"]
    direction TB
    FEAT["Feature Pipeline"]:::pipeline
    CURATED["Curated Features"]:::data
    TRAIN["Training Pipeline"]:::pipeline
    REG["MLflow Registry"]:::registry
    FEAT --> CURATED --> TRAIN --> REG
  end

  subgraph ServePath ["Serving path"]
    direction TB
    SERVE["FastAPI App"]:::app
    RANK["Ranked Sessions"]:::data
    SERVE --> RANK
  end

  DATA --> FEAT
  CURATED --> SERVE
  REG --> SERVE
</div>

The core design stays stable across runtimes. FoehnCast collects weather data, builds curated features, trains and registers a model, and serves ranked session options through the application layer.

## Local And Cloud In One View

<div class="mermaid">
flowchart TD
  %% Style definitions
  classDef shared fill:#f5f5f5,stroke:#333,stroke-dasharray: 5 5
  classDef local fill:#e1f5fe,stroke:#01579b
  classDef cloud fill:#fff8e1,stroke:#f57f17

  CORE["Shared ML core"]:::shared

  subgraph LocalStack ["fab:fa-docker Local lane"]
    direction LR
    LOPS["Airflow + MLflow + monitoring"]:::local
    LAPP["MinIO + Feast + FastAPI"]:::local
  end

  subgraph CloudStack ["fab:fa-google Cloud lane"]
    direction LR
    CDATA["BigQuery + GCS + Datastore"]:::cloud
    CAPI["Cloud Run public API"]:::cloud
    COPS["Private operator lane"]:::cloud
  end

  CORE --> LocalStack
  CORE --> CloudStack
  LOPS --> LAPP
  CDATA --> CAPI
  CDATA --> COPS
</div>

<div class="fc-compare-note">
The common components matter more than the hosting details. Comparison pages should show the shared core first, then the deployment-specific differences.
</div>

## Read The Docs In This Order

1. [Use Case and Data](system/use-case.md) explains the rider problem, spot scope, and inputs.
2. [Getting Started](getting-started.md) gets the local evaluator running.
3. [Architecture](system/architecture.md) shows the stable system boundaries.
4. [Feature Pipeline](system/feature-pipeline.md), [Training Pipeline](system/training-pipeline.md), and [Inference Pipeline](system/inference-pipeline.md) explain the three main flows.
5. [Interfaces and Surfaces](system/interfaces-and-surfaces.md), [Monitoring](system/monitoring.md), and [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md) explain exposure, operations, and delivery.

## Documentation Map

<div class="grid cards" markdown>

- **Product scope**

  Use [Use Case and Data](system/use-case.md) for the rider story, the fixed spot set, and the data inputs.

- **Local-first setup**

  Use [Getting Started](getting-started.md) and [Local Evaluator](system/local-evaluator.md) for the default contributor path.

- **System design**

  Use [Architecture](system/architecture.md), [Configuration and Contracts](system/configuration-and-contracts.md), and [Interfaces and Surfaces](system/interfaces-and-surfaces.md) for the stable design rules.

- **Deployment comparison**

  Use [Hosted Full-Stack](system/hosted-full-stack.md), [Cloud Mapping](system/cloud-mapping.md), and [Delivery and Operator Workflow](system/delivery-and-operator-workflow.md) when comparing local and cloud responsibilities.

- **Pipelines**

  Use [Feature Pipeline](system/feature-pipeline.md), [Training Pipeline](system/training-pipeline.md), and [Inference Pipeline](system/inference-pipeline.md) for the execution flow.

- **Operations**

  Use [Monitoring](system/monitoring.md) for metrics, alerts, and evidence.

</div>
