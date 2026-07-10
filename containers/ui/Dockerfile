FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    FOEHNCAST_PROJECT_ROOT=/workspace \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/

WORKDIR /workspace

COPY pyproject.toml uv.lock config.yaml ./
COPY .streamlit ./.streamlit
COPY src ./src
COPY ui ./ui

RUN python -m venv /opt/venv \
    && uv sync --frozen --no-default-groups --no-editable \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /workspace /opt/venv

USER appuser

EXPOSE 8501

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["streamlit", "run", "ui/app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
