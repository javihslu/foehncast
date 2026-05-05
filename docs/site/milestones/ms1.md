# MS1 Proposal

<span class="fc-pill fc-pill--done">Completed</span>

MS1 fixed the project baseline. It defined the problem, the first architecture, the starting feature set, and the assumptions that later milestones were allowed to refine.

!!! note "How to read this page"

    This page summarizes the original proposal as a baseline, not as a frozen copy of the final implementation.
    The rider-specific use case and the Feature-Training-Inference split stayed stable.
    The main refinements came later in forecast horizon, storage defaults, and the cloud deployment path.

## Proposal In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Question</strong></p>
<p>Which Swiss kite spot is most worth the drive for one rider profile in the next few days?</p>
</li>
<li>
<p><strong>Inputs</strong></p>
<p>Forecast weather, drive time, and spot-specific wind context.</p>
</li>
<li>
<p><strong>Output</strong></p>
<p>A quality score that can be turned into a ranked list of candidate sessions.</p>
</li>
<li>
<p><strong>System shape</strong></p>
<p>Separate feature, training, and inference pipelines instead of one monolithic weather app.</p>
</li>
</ul>
</div>

<div class="mermaid">
flowchart LR
    Q[Rider question] --> D[Weather and route data]
    D --> F[Feature engineering]
    F --> M[Quality model]
    M --> R[Spot ranking]
</div>

## Baseline Scope

| Area | MS1 baseline |
|------|--------------|
| User | one rider profile instead of a generic public forecast |
| Geography | six Swiss lake spots |
| Primary weather source | Open-Meteo forecast and archive APIs |
| Route personalization | OSRM drive-time lookup from Schwyz |
| Validation reference | MeteoSwiss kept as a reference source, not the primary runtime feed |
| Prediction target | a quality index used to rank session options |

| Rider profile | Baseline choice |
|--------------|-----------------|
| Weight | 80 kg |
| Home location | Schwyz |
| Quiver | 5 / 7 / 8 / 10 / 12 m2 |

## Baseline FTI Architecture

The proposal already used the Feature-Training-Inference split that still anchors the project today.

<div class="mermaid">
flowchart LR
    subgraph FP[Feature pipeline]
        ING[Ingest forecast data]
        ENG[Engineer wind features]
        STO[Store curated rows]
        ING --> ENG --> STO
    end

    subgraph TP[Training pipeline]
        LAB[Label training rows]
        TRN[Train quality model]
        REG[Register in MLflow]
        LAB --> TRN --> REG
    end

    subgraph IP[Inference pipeline]
        PRED[Predict quality]
        RANK[Rank spot options]
        API[Serve the API]
        PRED --> RANK --> API
    end

    STO --> LAB
    REG --> PRED
</div>

## Proposal Feature Baseline

Instead of treating the first model as a long raw feature dump, it is easier to read it as three layers.

| Feature layer | Proposal baseline | Later refinement |
|---------------|-------------------|------------------|
| Wind state | `wind_speed_10m`, `wind_speed_80m`, `wind_direction_10m`, `wind_gusts_10m` | still central in the implemented model |
| Weather context | `temperature_2m`, `relative_humidity_2m` | expanded later with more weather fields in the shared config |
| Engineered kite features | `wind_steadiness`, `gust_factor`, `shore_alignment` | kept, with cyclical time features added later |

<div class="mermaid">
flowchart TD
    RAW[Raw weather fields] --> BASE[Baseline feature vector]
    ENG[Engineered wind features] --> BASE
    BASE --> MODEL[Quality index model]
    DRIVE[Drive time] --> RANK[Final ranking layer]
    MODEL --> RANK
</div>

## What MS1 Fixed And What Changed Later

| Proposal decision | Why it mattered in MS1 | Later refinement |
|-------------------|------------------------|------------------|
| Rider-specific ranking | kept the project narrow and practical | still the core use case |
| FTI architecture | separated data preparation, model training, and serving from the start | stayed stable and is now implemented end to end |
| Open-Meteo + OSRM baseline | made the first data path concrete and testable | still part of the working stack |
| MLflow baseline | gave the project an experiment and registry backbone early | stayed stable |
| Local-first start | reduced early infrastructure risk | still the default execution path |
| Forecast horizon | the proposal discussed a wider forecast window | the current config uses a 7-day forecast window |
| Feature store and cloud path | the proposal leaned heavily toward Feast, BigQuery, and Cloud Run | the current repo keeps Feast optional, local storage as the default baseline, and documents both an online compose host and an optional Cloud Run path |

## Why MS1 Still Matters

- It explains why the project is personalized instead of generic.
- It defines the architectural split that later milestones still follow.
- It provides the baseline against which later implementation choices can be compared.
- It makes the later changes easier to read: the project matured without changing its core question.

See [MS2 Backend](ms2.md) for the implemented local stack and [Architecture](../system/architecture.md) for the current system view.
