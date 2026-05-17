FROM grafana/grafana

# Self-contained Grafana image with all dashboards, provisioning, and config
# baked in. Cloud Run (and other volume-free runtimes) use this image directly.
# Local Compose can still volume-mount over these paths for live editing.
#
# Build context must be the repository root:
#   docker build --platform linux/amd64 -f containers/grafana/Dockerfile .

# Defaults that alerting provisioning needs at startup.
ENV FOEHNCAST_GRAFANA_ALERT_EMAIL=alerts@example.invalid

COPY --chown=grafana:root grafana_work/etc/grafana.ini /etc/grafana/grafana.ini
COPY --chown=grafana:root grafana_work/etc/provisioning /etc/grafana/provisioning
COPY --chown=grafana:root grafana_work/dashboards /opt/grafana/dashboards

EXPOSE 3000
