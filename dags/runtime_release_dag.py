"""Airflow DAG for recording reviewed runtime release handoff requests."""

from __future__ import annotations

from datetime import datetime

try:
    from airflow.providers.standard.operators.python import PythonOperator
    from airflow.sdk import DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.runtime_release import record_runtime_release_request

    with DAG(
        dag_id="runtime_release",
        description=(
            "Accept one reviewed GitHub-to-runtime handoff request and persist "
            "an observable acknowledgement for operators."
        ),
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        is_paused_upon_creation=False,
        tags=["foehncast", "runtime"],
    ) as dag:
        record_runtime_release = PythonOperator(
            task_id="record_runtime_release_request",
            python_callable=record_runtime_release_request,
            op_kwargs={
                "request_json": "{{ dag_run.conf | tojson if dag_run and dag_run.conf else '{}' }}",
                "dag_run_id": "{{ run_id }}",
                "dag_id": "runtime_release",
            },
        )
