# Repository

## Current Layout

```text
src/foehncast/
  config.py
  feature_pipeline/
    ingest.py
    engineer.py
    validate.py
    store.py
  training_pipeline/
  inference_pipeline/
  monitoring/
  spots/
dags/
tests/
docs/
```

## Central Configuration

```python
def load_config(path: Path | None = None) -> dict[str, Any]:
    global _config
    if _config is None or path is not None:
        p = path or _CONFIG_PATH
        with open(p) as f:
            _config = yaml.safe_load(f)
    return _config
```

The repository uses one YAML configuration file instead of scattering constants across modules.

## Feature Engineering Entry Point

```python
def engineer_features(
    df: pd.DataFrame, shore_orientation_deg: float
) -> pd.DataFrame:
    out = df.copy()
    out["wind_steadiness"] = wind_steadiness(df)
    out["gust_factor"] = gust_factor(df)
    out["shore_alignment"] = shore_alignment(df, shore_orientation_deg)
    return out
```

This function is the current bridge between raw weather data and the model feature vector.
