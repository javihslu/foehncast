"""Airflow DAG for scheduled inference across all configured spots."""

from __future__ import annotations

from datetime import datetime, timedelta

try:
    from airflow.providers.standard.operators.python import PythonOperator
    from airflow.sdk import Asset, DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.airflow_assets import (
        inference_prediction_log_asset_uri,
        mlflow_registry_asset_uri,
    )
    from foehncast.orchestration import run_inference_pipeline_step

    model_registry_asset = Asset(
        name="foehncast_mlflow_model_registry",
        uri=mlflow_registry_asset_uri(),
    )
    prediction_log_asset = Asset(
        name="foehncast_inference_prediction_log",
        uri=inference_prediction_log_asset_uri(),
    )

    with DAG(
        dag_id="inference_pipeline",
        description=(
            "Run predictions for all configured spots using the champion model, "
            "write the prediction log, and emit monitoring metrics.  Triggered "
            "automatically after model registration or manually from the Airflow UI."
        ),
        start_date=datetime(2024, 1, 1),
        schedule=[model_registry_asset],
        catchup=False,
        is_paused_upon_creation=False,
        tags=["foehncast", "inference"],
        # The task loads the champion model over HTTP from the registry, so a
        # restarting registry fails the whole run on the first call. Retry it.
        default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    ) as dag:
        run_inference = PythonOperator(
            task_id="run_inference",
            python_callable=run_inference_pipeline_step,
            inlets=[model_registry_asset],
            outlets=[prediction_log_asset],
        )
