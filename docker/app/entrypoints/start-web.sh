#!/bin/sh
set -eu

mkdir -p /app/run /app/staticfiles /app/media

python manage.py migrate --noinput
python manage.py collectstatic --noinput

set -- gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-1}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"

if [ "${GUNICORN_RELOAD:-0}" = "1" ]; then
  set -- "$@" --reload
fi

exec "$@"
