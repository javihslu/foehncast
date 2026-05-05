# Seasonality

Seasonality is already handled in FoehnCast through cyclical time features derived from the forecast timestamp. The project does not split the model by season; it encodes repeating daily and yearly patterns directly in the feature table.

## Why It Matters

Swiss kite spots do not behave the same way all year.
Summer thermals, winter pressure systems, daylight, and temperature patterns all affect when a spot becomes rideable. If the model only sees raw weather values, it may miss some of that structure.

## Current Implementation

The feature pipeline currently engineers four timestamp-derived fields:

- `hour_of_day_sin`
- `hour_of_day_cos`
- `day_of_year_sin`
- `day_of_year_cos`

These features let the model learn that 14:00 is close to 15:00, and that late June is close to early July, without introducing a discontinuity at midnight or year-end.

## Where It Fits In FTI

- The feature pipeline creates the cyclical time fields from each forecast timestamp.
- The training pipeline consumes those fields as part of the model feature vector.
- The inference pipeline builds the same fields from live forecast timestamps.

This keeps training and inference aligned around the same time encoding.

## Why The Current Scope Stays Simple

The current implementation favors the smallest feature set that can still capture recurring patterns.

- No separate seasonal model families.
- No wide month-dummy design.
- No extra architecture dedicated only to seasonal logic.

That keeps the project within course scope while still giving the model useful time context.

## How It Can Be Evaluated

Seasonality changes can be evaluated through the same training and MLflow workflow used for the rest of the model.

- compare training runs with and without additional seasonal features
- inspect error metrics and ranking quality across different parts of the year
- keep only changes that improve the model enough to justify the added complexity

## Summary

FoehnCast already accounts for seasonality in a lightweight way. The current design is to keep cyclical time features in the shared feature layer and only add more seasonal complexity if model evidence makes that worthwhile.
