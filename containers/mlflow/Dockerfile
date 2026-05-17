FROM ghcr.io/mlflow/mlflow:v3.12.0

COPY start-model-registry.sh /usr/local/bin/start-model-registry.sh

RUN pip install --no-cache-dir boto3 google-cloud-storage psycopg2-binary \
    && chmod 755 /usr/local/bin/start-model-registry.sh

CMD ["/usr/local/bin/start-model-registry.sh"]
