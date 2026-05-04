FROM apache/airflow:2.10.5-python3.12

USER root

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && rm -rf /var/lib/apt/lists/*

USER airflow
WORKDIR /workspace

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    AIRFLOW_HOME=/workspace/airflow \
    AIRFLOW__CORE__DAGS_FOLDER=/workspace/dags \
    PYTHONPATH=/workspace/src

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "-lc", "cd /workspace && uv pip install --system -e . && airflow standalone"]
