# Media Kit

Assets for articles and posts about FoehnCast. All files are produced from the live system; screenshots are retina resolution (3200 px wide), the cover is 2560x1280.

## Cover

![FoehnCast cover](assets/kit/01-cover.png)

[Download cover](assets/kit/01-cover.png)

## Motion

| File | Content | Length |
|------|---------|--------|
| [foehncast-demo.mp4](assets/kit/foehncast-demo.mp4) | Full tour: rider console, dial trigger, system panel, Airflow, MLflow | 36 s |
| [console-hero.gif](assets/kit/console-hero.gif) | Session-quality heatmap with cell selection driving the wind dial and metrics | 9 s loop |
| [dial-interaction.gif](assets/kit/dial-interaction.gif) | A freshness dial as run button: hover, trigger, busy state | 5 s loop |
| [ops-tour.mp4](assets/kit/ops-tour.mp4) | System tab: pipeline rails, prediction health, shadow scoring, drift | 10 s |
| [airflow-assets.mp4](assets/kit/airflow-assets.mp4) | Airflow DAGs and the asset dependency graph | 24 s |
| [mlflow-registry.mp4](assets/kit/mlflow-registry.mp4) | MLflow registry with champion and candidate aliases | 12 s |

## Screenshots

| File | Content |
|------|---------|
| [02-rider-console.png](assets/kit/02-rider-console.png) | Rider console with a selected session cell: heatmap, wind dial, metrics bubble, champion panel |
| [05-rider-console-local.png](assets/kit/05-rider-console-local.png) | Rider console overview: six-spot session-quality heatmap and freshness dials |
| [06-airflow-dags.png](assets/kit/06-airflow-dags.png) | Airflow with the five FoehnCast DAGs |
| [07-mlflow-experiments.png](assets/kit/07-mlflow-experiments.png) | MLflow experiment tracking with pipeline-triggered runs |
| [08-mlflow-registry.png](assets/kit/08-mlflow-registry.png) | MLflow model registry with the champion alias |
| [09-airflow-training-pipeline.png](assets/kit/09-airflow-training-pipeline.png) | Training DAG detail with asset-triggered inference |
| [10-wind-map.png](assets/kit/10-wind-map.png) | Regional wind map with per-spot direction, strength, and rideability |

## Diagrams

| File | Content |
|------|---------|
| [03-diagram-fti-pipelines.png](assets/kit/03-diagram-fti-pipelines.png) | Feature/Training/Inference architecture |
| [04-diagram-cloud-architecture.png](assets/kit/04-diagram-cloud-architecture.png) | Cloud deployment layout (Cloud Run, Workflows, BigQuery) |

Screenshots show the local Docker stack; the cloud deployment renders the identical interface by design. The project description and suggested copy live with the repository README and the [documentation start page](index.md).
