# Seasonality

FoehnCast should account for seasonality, but in a simple way.

## Why It Matters

Swiss kite spots do not behave the same way all year.
Summer thermals, winter pressure systems, daylight, and temperature patterns all affect when a spot becomes rideable. If the model only sees raw weather values, it may miss some of that structure.

## What We Should Add First

The first version should use a small set of time features derived from the forecast timestamp:

- `hour_of_day_sin`
- `hour_of_day_cos`
- `day_of_year_sin`
- `day_of_year_cos`

These features are simple and work well for repeating patterns. They let the model learn that 14:00 is close to 15:00, and that late June is close to early July.

## What We Should Not Add Yet

We should avoid a more complex seasonal design for now.

- No separate model per season.
- No long list of month dummy columns unless the simple features are not enough.
- No extra architecture just for seasonality.

The goal is to improve the model with the smallest clear change.

## Where It Fits In FTI

Seasonality belongs in the feature layer.

- The feature pipeline should create the time features from each forecast timestamp.
- The training pipeline should train on those features.
- The inference pipeline should build the same features from the live forecast timestamps.

This keeps training and inference consistent.

## How We Should Validate It

We should compare a baseline model against a seasonal-feature model in MLflow.

We should only keep the new features if they improve at least one of these:

- overall error metrics
- ranking quality
- stability across different months

## Recommendation

Yes, FoehnCast should account for seasonality.

The first implementation should stay simple: add cyclical time features, retrain, and compare results before making the design more complex.
