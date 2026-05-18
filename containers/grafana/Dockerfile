FROM grafana/grafana:11.3.0

# Self-contained Grafana image with all dashboards, provisioning, and config
# baked in. Cloud Run (and other volume-free runtimes) use this image directly.
# Local Compose can still volume-mount over these paths for live editing.
#
# Build context must be the repository root:
#   docker build --platform linux/amd64 -f containers/grafana/Dockerfile .
#
# Pinned to 11.3.0 (LTS line) to avoid panel-plugin lookup failures observed
# on the floating `latest` tag (e.g. 13.x renames + Scenes migration issues).

# Defaults that alerting provisioning needs at startup.
ENV FOEHNCAST_GRAFANA_ALERT_EMAIL=alerts@example.invalid
COPY --chown=grafana:root grafana_work/etc/grafana.ini /etc/grafana/grafana.ini
COPY --chown=grafana:root grafana_work/etc/provisioning /etc/grafana/provisioning
COPY --chown=grafana:root grafana_work/dashboards /opt/grafana/dashboards

# Entrypoint that injects a GCP metadata token for GMP auth on Cloud Run.
COPY --chown=grafana:root containers/grafana/entrypoint.sh /entrypoint.sh

EXPOSE 3000
ENTRYPOINT ["/entrypoint.sh"]
