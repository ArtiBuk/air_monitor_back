#!/bin/sh
set -eu

celery -A config inspect ping -d "${CELERY_HEALTHCHECK_NODE:-worker@${HOSTNAME}}" | grep -q "pong"
