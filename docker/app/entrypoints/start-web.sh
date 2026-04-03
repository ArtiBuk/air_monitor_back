#!/bin/sh
set -eu

mkdir -p /app/run /app/staticfiles /app/media

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ['DJANGO_SUPERUSER_EMAIL']
password = os.environ['DJANGO_SUPERUSER_PASSWORD']
defaults = {
    'first_name': os.environ.get('DJANGO_SUPERUSER_FIRST_NAME', ''),
    'last_name': os.environ.get('DJANGO_SUPERUSER_LAST_NAME', ''),
    'is_staff': True,
    'is_superuser': True,
    'is_active': True,
}
user, created = User.objects.get_or_create(email=email, defaults=defaults)
for key, value in defaults.items():
    setattr(user, key, value)
user.set_password(password)
user.save()
print(f'bootstrap superuser email={email} created={created}')
"
fi

set -- gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-1}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"

if [ "${GUNICORN_RELOAD:-0}" = "1" ]; then
  set -- "$@" --reload
fi

exec "$@"
