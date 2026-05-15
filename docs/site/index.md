# FoehnCast Docs

FoehnCast ranks Swiss kiteboarding spots for one rider profile by combining live weather forecasts, engineered wind features, drive-time information, and a trained quality model. Use the repository README for the short summary. Use this site for setup help, product scope, runtime notes, and operator guidance.

## Product In One View

<div class="mermaid">
flowchart LR
    WX[Forecast + spot context] --> RANK[Rank session options]
    RIDER[Rider + drive context] --> RANK
    RANK --> DECIDE[Choose where to ride next]
</div>

## Main Capabilities

<div class="grid cards fc-feature-grid" markdown>

- **Rank the next session**

    Compare a fixed set of Swiss lake spots instead of browsing a generic forecast map.

- **Personalize the choice**

    Combine weather, rider profile, spot context, and drive time in one ranking decision.

- **Serve the same product through code and UI**

    Expose the model through API routes and rider-facing demo surfaces built on the same inference path.

- **Keep the system reproducible**

    Separate feature, training, and inference so local validation and deployment share the same core design.

</div>

## System Flow

<div class="mermaid">
flowchart LR
    INGEST[Ingest forecasts] --> FEATURES[Build curated features] --> TRAIN[Train and register model] --> SERVE[Serve prediction and ranking]
</div>

## Read Next

<div class="grid cards" markdown>

- **Overview**

    Read [Overview](overview.md) for the documentation map, the shared system core, and the local-versus-cloud split.

- **Getting Started**

    Read [Getting Started](getting-started.md) for the default local evaluator path.

- **Use Case and Data**

    Read [Use Case and Data](system/use-case.md) for the rider scope, spots, and inputs.

- **Architecture**

    Read [Architecture](system/architecture.md) for the feature, training, and inference boundaries.

</div>
