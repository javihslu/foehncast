FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/workspace/.venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /workspace
USER appuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "-lc", "uv sync && tail -f /dev/null"]
