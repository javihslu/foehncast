FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/
COPY containers/app/start-app.sh /usr/local/bin/start-app.sh

WORKDIR /workspace

COPY pyproject.toml uv.lock config.yaml ./
COPY src ./src

RUN python -m venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python -e . \
    && chmod 755 /usr/local/bin/start-app.sh \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /workspace /opt/venv

USER appuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-app.sh"]
