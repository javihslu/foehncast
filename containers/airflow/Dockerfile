FROM apache/airflow:2.10.5-python3.12

USER root

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/
COPY containers/airflow/init-airflow.sh /usr/local/bin/init-airflow.sh
COPY containers/airflow/start-airflow-webserver.sh /usr/local/bin/start-airflow-webserver.sh
COPY containers/airflow/start-airflow-scheduler.sh /usr/local/bin/start-airflow-scheduler.sh
COPY containers/airflow/start-airflow-triggerer.sh /usr/local/bin/start-airflow-triggerer.sh
COPY containers/airflow/webserver_config.py /opt/airflow/webserver_config.py
COPY containers/airflow/webserver_config_cloud.py /opt/airflow/webserver_config_cloud.py

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && chmod 755 /usr/local/bin/init-airflow.sh \
    /usr/local/bin/start-airflow-webserver.sh \
    /usr/local/bin/start-airflow-scheduler.sh \
    /usr/local/bin/start-airflow-triggerer.sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY src ./src

USER airflow

ENV UV_LINK_MODE=copy

RUN uv pip install --python /home/airflow/.local/bin/python -e .

ENV PYTHONUNBUFFERED=1 \
    AIRFLOW_HOME=/workspace/airflow \
    AIRFLOW__CORE__DAGS_FOLDER=/workspace/dags \
    PYTHONPATH=/workspace/src

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["airflow", "version"]
