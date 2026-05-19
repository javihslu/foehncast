# Use Case and Data

FoehnCast helps you pick the best Swiss kiteboarding spot for today. One rider, six spots, one question: where should I drive?

We keep the scope small on purpose — it's a real decision for a real rider, not a generic weather app.

## How the Ranking Works

<div class="mermaid">
flowchart TD
        WX[Weather forecasts] --> QUAL[Per-spot quality score]
        SPOT[Spot metadata + shore orientation] --> QUAL
        QUAL --> RANK[Rank spots]
        WINDOW[Rideable time window] --> RANK
        RIDER[Rider profile] --> RANK
        DRIVE[Drive time from home] --> RANK
</div>

## What Goes Into the Score

<div class="grid cards" markdown>

- **Wind quality**

    The model predicts how good conditions look at each spot.

- **Session length**

    Longer rideable windows beat short spikes.

- **Drive time**

    We're choosing a trip, not just reading a forecast.

- **Spot fit**

    Shore orientation and local rules matter — not every wind direction works everywhere.

</div>

## Rider Profile

| Field | Value |
|-------|-------|
| Home | Schwyz |
| Weight | 80 kg |
| Kite sizes | 5 / 7 / 8 / 10 / 12 m² |

One fixed profile keeps the problem consistent. The model doesn't try to serve every rider.

## Spots

| Spot | Canton | Level | Ideal wind |
|------|--------|-------|-----------|
| Silvaplana | GR | intermediate | 180°–270° |
| Urnersee | UR | intermediate | 150°–210° |
| Lac de Neuchatel | NE | beginner | 200°–310° |
| Bodensee | TG | beginner | 180°–300° |
| Walensee | SG | intermediate | 220°–320° |
| Thunersee | BE | advanced | 220°–330° |

## Data Sources

| Source | What it provides |
|--------|-----------------|
| Open-Meteo | Weather forecasts (wind, gusts, temperature, etc.) |
| OSRM | Drive time from home to each spot |
| Spot metadata | Shore orientation, difficulty, local rules |

## Why Fixed Scope

- Keeps labeling aligned with one real rider scenario
- Makes drive-time ranking meaningful (not theoretical)
- Avoids becoming a generic weather portal
- One clear product question = focused implementation
