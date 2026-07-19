FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    FOEHNCAST_PROJECT_ROOT=/workspace \
    FOEHNCAST_FEAST_REPO_PATH=/workspace/feature_repo \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/
COPY containers/app/start-app.sh /usr/local/bin/start-app.sh

WORKDIR /workspace

COPY pyproject.toml uv.lock config.yaml ./
COPY feature_repo ./feature_repo
COPY src ./src

RUN python -m venv /opt/venv \
    && uv sync --frozen --no-default-groups --group feast --no-editable \
    && chmod 755 /usr/local/bin/start-app.sh \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /workspace /opt/venv

USER appuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-app.sh"]
