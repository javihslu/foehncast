#!/bin/sh

# Remove an old pid file, then start the Airflow webserver.

set -eu

airflow_home="/workspace/airflow"

rm -f "$airflow_home/airflow-webserver.pid"
exec airflow webserver
