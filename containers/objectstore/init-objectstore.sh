#!/bin/sh

# Wait for MinIO, create the artifacts bucket if needed, then write a health
# file for other services.

set -eu

alias_name="local"
endpoint_url="http://objectstore:9000"
bucket_name="${OBJECTSTORE_BUCKET}"
marker_file="/tmp/objectstore-init-complete"

until mc alias set "$alias_name" "$endpoint_url" "$OBJECTSTORE_ACCESS_KEY" "$OBJECTSTORE_SECRET_KEY"; do
  sleep 1
done

mc mb --ignore-existing "$alias_name/$bucket_name"
touch "$marker_file"
exec tail -f /dev/null
