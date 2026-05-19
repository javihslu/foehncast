# FoehnCast Docs

FoehnCast tells you which Swiss kiteboarding spot is worth the drive today. It combines live weather forecasts, wind features, drive times, and a trained quality model into a single ranked recommendation.

This site covers how the system works, how to set it up, and how the cloud deployment is structured.

## What It Does

<div class="mermaid">
flowchart TD
    WX[Weather forecasts + spot data] --> RANK[Rank spots by quality]
    RIDER[Rider profile + drive time] --> RANK
    RANK --> DECIDE[Pick the best spot]
</div>

## Key Features

<div class="grid cards fc-feature-grid" markdown>

- **Spot ranking**

    Compares Swiss lake spots using a trained model instead of raw forecast numbers.

- **Personalized**

    Weights wind, drive time, and rider preferences into one score.

- **Same code everywhere**

    API, UI, and pipelines share the same Python modules.

- **Reproducible**

    FTI split + DVC + containers = same results on any machine.

</div>

## System Flow

<div class="mermaid">
flowchart LR
    INGEST[Fetch forecasts] --> FEATURES[Engineer features] --> TRAIN[Train model] --> SERVE[Serve rankings]
</div>

## Where to Start

<div class="grid cards" markdown>

- **[Overview](overview.md)**

    How the system is organized and where local vs. cloud differ.

- **[Getting Started](getting-started.md)**

    Run it locally with Docker in 3 steps.

- **[Use Case and Data](system/use-case.md)**

    What data goes in and what comes out.

- **[Architecture](system/architecture.md)**

    The FTI split, pipelines, and deployment targets.

</div>
