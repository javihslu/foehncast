# Seasonality

Swiss kite spots behave differently across seasons — summer thermals, winter pressure systems, daylight changes. We handle this with cyclical time features instead of separate seasonal models.

## Features

The feature pipeline creates four time-derived columns:

| Feature | Encodes |
|---------|---------|
| `hour_of_day_sin/cos` | Time of day (smooth wrap at midnight) |
| `day_of_year_sin/cos` | Season (smooth wrap at year-end) |

Sin/cos encoding means the model understands that 23:00 is close to 00:00, and December 31 is close to January 1.

## Where They're Used

| Pipeline | Role |
|----------|------|
| Feature | Creates the cyclical columns from forecast timestamps |
| Training | Includes them in the model feature vector |
| Inference | Rebuilds them from live timestamps (same function) |

## Why Keep It Simple

- No separate summer/winter models
- No wide month-dummy encoding
- No special seasonal architecture
- Just four extra features that give the tree-based model time context

If we ever need more seasonal complexity, it has to prove itself through better model metrics first.
