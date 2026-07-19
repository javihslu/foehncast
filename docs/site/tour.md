# Visual tour

What the running system looks like, captured from the local Docker stack.

## Rider console

![Rider console](assets/kit/02-rider-console.png)

*Session-quality heatmap across the six spots; the selected cell drives the wind dial and the metrics bubble, with the serving champion model in the sidebar.*

## Regional wind map

![Regional wind map](assets/kit/10-wind-map.png)

*Per-spot wind over the region: each wedge points downwind and its length is the speed, with an hour slider across the forecast and the rider home marked.*

## Orchestration

![Airflow DAGs](assets/kit/06-airflow-dags.png)

![Training pipeline](assets/kit/09-airflow-training-pipeline.png)

*The five FoehnCast DAGs, and the training pipeline whose model-registry asset events trigger inference.*

## Experiment tracking

![MLflow runs](assets/kit/07-mlflow-experiments.png)

*Pipeline-triggered training runs, two of them registered as model versions.*

## Model registry

![MLflow registry](assets/kit/08-mlflow-registry.png)

*`foehncast-quality` with version 2 carrying the champion alias served by the API.*
