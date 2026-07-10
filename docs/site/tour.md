# Visual tour

What the running system looks like, captured from the local Docker stack.

## Rider console

![Rider console](assets/tour/rider-console.png)

*Ride-quality and wind forecasts, six-spot ranking, and the champion model card.*

## Regional wind map

![Regional wind map](assets/tour/wind-map.png)

*Per-spot wind arrows over the region: direction points downwind, color marks rideable status, with an hour slider across the forecast.*

## Orchestration

![Airflow DAGs](assets/tour/airflow-dags.png)

![Training pipeline](assets/tour/training-pipeline.png)

*The five FoehnCast DAGs, and the training pipeline whose model-registry asset events trigger inference.*

## Experiment tracking

![MLflow runs](assets/tour/mlflow-runs.png)

*Pipeline-triggered training runs, two of them registered as model versions.*

## Model registry

![MLflow registry](assets/tour/mlflow-registry.png)

*`foehncast-quality` with version 2 carrying the champion alias served by the API.*
