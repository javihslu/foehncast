# Use Case and Data

FoehnCast is not a generic forecast portal. It is a decision tool for one rider profile and a fixed set of Swiss kite spots, built around a simple question: where is the best session worth driving to next?

!!! note "Scope matters here"

    The project stays intentionally narrow.
    It ranks a small set of known spots for one rider baseline instead of trying to be a universal weather product.

## Use Case In One View

<div class="grid cards">
<ul>
<li>
<p><strong>Rider</strong></p>
<p>The baseline user is one rider based in Schwyz with a fixed quiver and weight profile.</p>
</li>
<li>
<p><strong>Decision</strong></p>
<p>The output is not just a forecast. It is a ranked session choice across multiple spots.</p>
</li>
<li>
<p><strong>Personalization</strong></p>
<p>Drive time, rider profile, and shore-specific wind context matter alongside raw weather.</p>
</li>
<li>
<p><strong>Scope</strong></p>
<p>The system is intentionally limited to six Swiss lake spots so the ranking logic stays concrete and testable.</p>
</li>
</ul>
</div>

<div class="mermaid">
flowchart LR
    WX[Weather forecasts] --> QUAL[Per-spot quality prediction]
    SPOT[Spot metadata and shore orientation] --> QUAL
    QUAL --> RANK[Ranked session options]
    RIDER[Rider profile] --> RANK
    DRIVE[OSRM drive time] --> RANK
</div>

## Rider Profile

| Field | Baseline value |
|-------|----------------|
| Home location | Schwyz |
| Weight | 80 kg |
| Quiver | 5 / 7 / 8 / 10 / 12 m2 |

This baseline keeps the ranking problem consistent across the project. The model does not try to optimize for every possible rider at once.

## What The System Ranks

The ranking layer combines more than one signal.

| Factor | Why it matters |
|--------|----------------|
| Predicted quality index | identifies whether a spot looks rideable and how good the session could be |
| Session duration | rewards spots that stay rideable for longer windows |
| Drive time | discounts distant options that are not worth the trip |

That is why the system is better described as a trip-planning tool than as a plain weather dashboard.

## Spots in Scope

| Spot | Canton | Difficulty | Water | Ideal wind window |
|------|--------|------------|-------|-------------------|
| Silvaplana | GR | intermediate | lake | 180°-270° |
| Urnersee | UR | intermediate | lake | 150°-210° |
| Lac de Neuchatel | NE | beginner | lake | 200°-310° |
| Bodensee | TG | beginner | lake | 180°-300° |
| Walensee | SG | intermediate | lake | 220°-320° |
| Thunersee | BE | advanced | lake | 220°-330° |

These are not example rows. They are the actual fixed spot set used in the current configuration baseline.

## Data Sources

| Source | Role in the project | Current status |
|--------|---------------------|----------------|
| Open-Meteo | primary forecast and archive weather source | implemented |
| OSRM | drive-time personalization for ranking | implemented |
| MeteoSwiss | possible observation reference for later validation | planned |

Open-Meteo supplies the forecast data, OSRM already contributes travel-time ranking inputs, and MeteoSwiss remains a possible future reference source rather than an active dependency in the current stack.

## Why The Scope Is Fixed

- It keeps the labeling and ranking problem aligned with one real rider scenario.
- It makes route-time personalization meaningful instead of theoretical.
- It avoids turning the course project into a generic weather portal with weak decision support.
- It keeps later milestone changes focused on implementation maturity rather than on changing the product question.

See [MS1 Proposal](../milestones/ms1.md) for the original baseline and [Architecture](architecture.md) for the current system structure.
