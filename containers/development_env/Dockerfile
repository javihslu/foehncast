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
COPY start-development-env.sh /usr/local/bin/start-development-env.sh

RUN useradd --create-home --shell /bin/bash appuser
RUN chmod 755 /usr/local/bin/start-development-env.sh

WORKDIR /workspace
USER appuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-development-env.sh"]
