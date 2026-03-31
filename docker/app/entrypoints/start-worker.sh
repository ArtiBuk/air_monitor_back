#!/bin/sh
set -eu

mkdir -p /app/run

exec celery -A config worker \
  --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
  --hostname="${CELERY_WORKER_NAME:-worker@%h}" \
  --queues="${CELERY_WORKER_QUEUES:-default,monitoring,ml}"
