"""Airflow DAG for scheduled data and prediction drift detection."""

from __future__ import annotations

from datetime import datetime
import os

try:
    from airflow.providers.standard.operators.python import PythonOperator
    from airflow.sdk import Asset, DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.airflow_assets import drift_report_asset_uri
    from foehncast.orchestration import (
        resolve_airflow_schedule,
        run_feature_drift_detection_step,
        run_prediction_drift_detection_step,
    )

    drift_dataset = os.getenv("AIRFLOW_DRIFT_DATASET", "train").strip() or "train"
    drift_schedule = resolve_airflow_schedule(
        os.getenv("AIRFLOW_DRIFT_SCHEDULE"),
        default="0 */12 * * *",
    )
    drift_report_asset = Asset(
        name=f"{drift_dataset}_drift_report",
        uri=drift_report_asset_uri(drift_dataset),
    )

    with DAG(
        dag_id="drift_detection",
        description=(
            "Detect data drift across stored features and prediction drift "
            "from the inference log.  Pushes StatsD metrics for Prometheus "
            "scraping and Grafana alerting."
        ),
        start_date=datetime(2024, 1, 1),
        schedule=drift_schedule,
        catchup=False,
        is_paused_upon_creation=False,
        tags=["foehncast", "monitoring"],
    ) as dag:
        detect_feature_drift = PythonOperator(
            task_id="detect_feature_drift",
            python_callable=run_feature_drift_detection_step,
            outlets=[drift_report_asset],
            op_kwargs={"dataset": drift_dataset},
        )

        detect_prediction_drift = PythonOperator(
            task_id="detect_prediction_drift",
            python_callable=run_prediction_drift_detection_step,
            outlets=[drift_report_asset],
        )

        detect_feature_drift >> detect_prediction_drift
