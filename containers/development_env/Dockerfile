FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/home/appuser/.venv \
    PATH=/home/appuser/.venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY containers/development_env/start-development-env.sh /usr/local/bin/start-development-env.sh
COPY containers/development_env/start-jupyter-server.sh /usr/local/bin/start-jupyter-server.sh

RUN chmod 755 /usr/local/bin/start-development-env.sh /usr/local/bin/start-jupyter-server.sh \
    && chown -R appuser:appuser /workspace /home/appuser

USER appuser

RUN uv sync --frozen

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-development-env.sh"]
