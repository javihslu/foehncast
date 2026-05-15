# Use Case and Data

FoehnCast is a trip-planning tool for one rider profile and a fixed set of Swiss kite spots. It answers one question: where is the best session worth driving to next?

The scope stays intentionally narrow. The project ranks a small known spot set for one rider baseline instead of trying to be a universal weather portal.

## Decision Model

<div class="mermaid">
flowchart TD
        WX[Weather forecasts] --> QUAL[Per-spot quality]
        SPOT[Spot metadata and shore orientation] --> QUAL
        QUAL --> RANK[Rank session options]
        WINDOW[Rideable time window] --> RANK
        RIDER[Rider profile] --> RANK
        DRIVE[OSRM drive time] --> RANK
</div>

## What Shapes The Ranking

<div class="grid cards" markdown>

- **Wind quality**

    The model predicts how good each spot looks for the configured rider profile.

- **Session window**

    Longer rideable periods score better than short spikes.

- **Drive time**

    Distance matters because the system is choosing a trip, not only a forecast.

- **Spot fit**

    Shore orientation and local spot rules shape whether the forecast is useful.

</div>

## Rider Baseline

| Field | Baseline value |
|-------|----------------|
| Home location | Schwyz |
| Weight | 80 kg |
| Quiver | 5 / 7 / 8 / 10 / 12 m2 |

This baseline keeps the ranking problem consistent across the project. The model does not try to optimize for every possible rider at once.

## Spots in Scope

| Spot | Canton | Difficulty | Water | Ideal wind window |
|------|--------|------------|-------|-------------------|
| Silvaplana | GR | intermediate | lake | 180°-270° |
| Urnersee | UR | intermediate | lake | 150°-210° |
| Lac de Neuchatel | NE | beginner | lake | 200°-310° |
| Bodensee | TG | beginner | lake | 180°-300° |
| Walensee | SG | intermediate | lake | 220°-320° |
| Thunersee | BE | advanced | lake | 220°-330° |

These six spots define the ranking scope.

## Main Inputs

| Input | Role |
|-------|------|
| Open-Meteo | forecast weather inputs for feature generation and prediction |
| OSRM | drive-time inputs for trip ranking |
| Spot metadata | local wind context, shore orientation, and spot-level rules |

Open-Meteo supplies the weather signal. OSRM supplies travel time. Spot metadata keeps the ranking grounded in the local riding context.

## Why The Scope Stays Fixed

- It keeps the labeling and ranking problem aligned with one real rider scenario.
- It makes route-time personalization meaningful instead of theoretical.
- It avoids turning the project into a generic weather portal with weak decision support.
- It keeps implementation work focused on one concrete product question.

See [Architecture](architecture.md) for the system structure and [Feature Pipeline](feature-pipeline.md) for how the data moves through the stack.
