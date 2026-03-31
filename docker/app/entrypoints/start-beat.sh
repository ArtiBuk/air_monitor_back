#!/bin/sh
set -eu

mkdir -p /app/run

exec celery -A config beat \
  --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
  --schedule "${CELERY_BEAT_SCHEDULE_FILENAME:-/app/run/celerybeat-schedule}"
