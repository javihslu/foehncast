FROM apache/airflow:3.3.0-python3.12

USER root

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/
COPY containers/airflow/init-airflow.sh /usr/local/bin/init-airflow.sh
COPY containers/airflow/start-airflow-webserver.sh /usr/local/bin/start-airflow-webserver.sh
COPY containers/airflow/start-airflow-dag-processor.sh /usr/local/bin/start-airflow-dag-processor.sh
COPY containers/airflow/start-airflow-scheduler.sh /usr/local/bin/start-airflow-scheduler.sh
COPY containers/airflow/start-airflow-triggerer.sh /usr/local/bin/start-airflow-triggerer.sh

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && chmod 755 /usr/local/bin/init-airflow.sh \
    /usr/local/bin/start-airflow-webserver.sh \
    /usr/local/bin/start-airflow-dag-processor.sh \
    /usr/local/bin/start-airflow-scheduler.sh \
    /usr/local/bin/start-airflow-triggerer.sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY src ./src

USER airflow

ENV UV_LINK_MODE=copy \
    PATH=/usr/local/bin:$PATH

RUN python -m venv /home/airflow/.local/feast-venv \
    && /usr/local/bin/uv pip install --python /home/airflow/.local/feast-venv/bin/python \
    "feast[gcp]>=0.63.0" \
    && /usr/local/bin/uv pip install --python /home/airflow/.local/bin/python \
    "apache-airflow-providers-standard==1.12.3" \
    -e . \
    && ln -sf /usr/local/bin/uv /home/airflow/.local/bin/uv \
    && ln -sf /usr/local/bin/uvx /home/airflow/.local/bin/uvx

ENV PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    AIRFLOW_HOME=/workspace/airflow \
    AIRFLOW__CORE__DAGS_FOLDER=/workspace/dags \
    FOEHNCAST_FEAST_PYTHON=/home/airflow/.local/feast-venv/bin/python \
    FOEHNCAST_PROJECT_ROOT=/workspace \
    PYTHONPATH=/workspace/src

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["airflow", "version"]
