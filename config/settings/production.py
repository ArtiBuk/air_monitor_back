from . import base as base_settings
from .base import *  # noqa: F401,F403

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = base_settings.env_bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = base_settings.env_bool("CSRF_COOKIE_SECURE", True)
JWT_COOKIE_SECURE = base_settings.env_bool("JWT_COOKIE_SECURE", True)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = base_settings.env_int("SECURE_HSTS_SECONDS", 3600)
