# Inference Pipeline

The inference pipeline serves predictions through a FastAPI app. It loads a model from MLflow, fetches live forecasts, engineers features, predicts quality, and ranks spots.

## Request Flow

<div class="mermaid">
flowchart TD
    subgraph Request ["Request path"]
        direction TB
        REQ["Spot IDs from client"]
        WX["Fetch Open-Meteo forecast"]
        ENG["Engineer features"]
        REQ --> WX --> ENG
    end

    subgraph Model ["Model path"]
        direction TB
        REG["MLflow registry"]
        MOD["Predict with champion model"]
        REG --> MOD
    end

    subgraph Output ["Output"]
        direction TB
        PRE["/predict → quality scores"]
        RNK["/rank → sorted spots"]
        PRE --> RNK
    end

    ENG --> MOD --> PRE
</div>

## API Endpoints

| Route | What it returns |
|-------|----------------|
| `/health` | App status + served model alias and version |
| `/spots` | List of configured spots |
| `/predict` | Per-spot forecast with `quality_index` values |
| `/rank` | Spots scored and sorted for the rider profile |
| `/features/online` | Feast-backed feature lookup (optional) |
| `/metrics` | Prometheus metrics (for monitoring, not users) |

## How Prediction Works

1. Client sends spot IDs → app resolves them against `config.yaml`
2. App fetches live forecast from Open-Meteo (capped at 14h horizon)
3. Same `engineer_features()` function as the feature pipeline builds the feature vector
4. Model predicts `quality_index` for each forecast row
5. Response includes timestamps + continuous quality scores + model version

## How Ranking Works

`/rank` is not a second model. It reuses `/predict` output and scores spots with:

| Weight | Factor | Default |
|--------|--------|---------|
| 0.6 | Peak quality score | Highest `quality_index` in the window |
| 0.3 | Ride-vs-drive ratio | Session hours ÷ drive hours |
| 0.1 | Session duration | Hours above rideable threshold |

Drive time comes from OSRM. Weights live in `config.yaml`.

## Model Loading

- Model name: `foehncast-quality`
- Default alias: `champion`
- Override: `FOEHNCAST_MLFLOW_SERVING_ALIAS` env var
- `/health` shows which alias and version is active

## Scheduled Inference (Airflow)

The `inference_pipeline` DAG also runs predictions in batch:

- Triggered by the model-registry asset (new model → auto-run)
- Predicts across all configured spots
- Emits prediction log for monitoring and hindcast validation

This keeps prediction history populated even without live traffic.

## Streamlit UI

The Streamlit demo (`ui/app.py`) calls the same `/predict` and `/rank` endpoints and presents:

- Ranked spot cards with rider-friendly quality labels
- Current model version and forecast window
- Live metric charts from PromQL queries
