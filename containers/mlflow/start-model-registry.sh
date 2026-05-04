#!/bin/sh

# Start the local MLflow server with clear settings for artifacts and
# metadata.

set -eu

mlflow_host="${MLFLOW_HOST:-0.0.0.0}"
mlflow_port="${MLFLOW_PORT:-5001}"
artifact_destination="${MLFLOW_ARTIFACT_DESTINATION:-s3://artifacts}"
backend_store_uri="${MLFLOW_BACKEND_STORE_URI:-sqlite:///metadata/metadata.sqlite}"

exec mlflow server \
  --host "$mlflow_host" \
  --port "$mlflow_port" \
  --artifacts-destination "$artifact_destination" \
  --backend-store-uri "$backend_store_uri" \
  --disable-security-middleware
