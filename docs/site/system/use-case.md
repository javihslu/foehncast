# Use Case and Data

FoehnCast is not a generic forecast portal. It is a planning tool for one rider profile and a fixed set of Swiss kite spots.

## Rider Profile

```yaml
rider:
  home_location: Schwyz
  weight_kg: 80
  quiver_m2: [5, 7, 8, 10, 12]
```

## Spots in Scope

| Spot | Canton | Difficulty | Water | Ideal wind window |
|------|--------|------------|-------|-------------------|
| Silvaplana | GR | intermediate | lake | 180°-270° |
| Urnersee | UR | intermediate | lake | 150°-210° |
| Lac de Neuchatel | NE | beginner | lake | 200°-310° |
| Bodensee | TG | beginner | lake | 180°-300° |
| Walensee | SG | intermediate | lake | 220°-320° |
| Thunersee | BE | advanced | lake | 220°-330° |

## Data Sources

| Source | Purpose | Status |
|--------|---------|--------|
| Open-Meteo | Forecast and archive weather data | implemented |
| OSRM | Drive-time input for ranking | planned |
| MeteoSwiss | Observation reference for validation | planned |
