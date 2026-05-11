#!/bin/sh

# Remove stale pid files, then start the Airflow API server.

set -eu

airflow_home="/workspace/airflow"

rm -f "$airflow_home/airflow-webserver.pid" "$airflow_home/airflow-api-server.pid"
exec airflow api-server
