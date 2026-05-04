FROM ghcr.io/mlflow/mlflow:v3.7.0

COPY start-model-registry.sh /usr/local/bin/start-model-registry.sh

RUN pip install --no-cache-dir boto3 \
    && chmod 755 /usr/local/bin/start-model-registry.sh
