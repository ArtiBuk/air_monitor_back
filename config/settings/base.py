import os
from pathlib import Path

from celery.schedules import crontab
from kombu import Exchange, Queue

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENVIRONMENT = os.getenv("DJANGO_ENV", "local").lower()


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = env(name)
    if raw is None:
        return default
    return int(raw)


SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-air-monitor-dev-key")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [host.strip() for host in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = env("DJANGO_TIME_ZONE", "Asia/Krasnoyarsk")
USE_I18N = True
USE_TZ = True

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

LOCAL_APPS = [
    "apps.common",
    "apps.users",
    "apps.authentication",
    "apps.monitoring",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestLogMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "air_monitor"),
        "USER": env("POSTGRES_USER", "air_monitor"),
        "PASSWORD": env("POSTGRES_PASSWORD", "air_monitor"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

JWT_ALGORITHM = env("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TTL_MINUTES = env_int("JWT_ACCESS_TTL_MINUTES", 30)
JWT_REFRESH_TTL_DAYS = env_int("JWT_REFRESH_TTL_DAYS", 14)
JWT_ISSUER = env("JWT_ISSUER", "air-monitor-back")
JWT_ACCESS_COOKIE_NAME = env("JWT_ACCESS_COOKIE_NAME", "access_token")
JWT_REFRESH_COOKIE_NAME = env("JWT_REFRESH_COOKIE_NAME", "refresh_token")
JWT_COOKIE_SECURE = env_bool("JWT_COOKIE_SECURE", False)
JWT_COOKIE_HTTPONLY = env_bool("JWT_COOKIE_HTTPONLY", True)
JWT_COOKIE_SAMESITE = env("JWT_COOKIE_SAMESITE", "Lax")
JWT_COOKIE_DOMAIN = env("JWT_COOKIE_DOMAIN")
JWT_ACCESS_COOKIE_PATH = env("JWT_ACCESS_COOKIE_PATH", "/")
JWT_REFRESH_COOKIE_PATH = env("JWT_REFRESH_COOKIE_PATH", "/api/auth/")

MONITORING_INTERVAL = env("MONITORING_INTERVAL", "Interval1H")
MONITORING_WINDOW_HOURS = env_int("MONITORING_WINDOW_HOURS", 1)
MONITORING_COLLECTION_LOOKBACK_HOURS = env_int("MONITORING_COLLECTION_LOOKBACK_HOURS", 48)
MONITORING_FORECAST_HORIZON_HOURS = env_int("MONITORING_FORECAST_HORIZON_HOURS", 24)
MONITORING_INPUT_WINDOW_HOURS = env_int("MONITORING_INPUT_WINDOW_HOURS", 72)

REDIS_HOST = env("REDIS_HOST", "localhost")
REDIS_PORT = env("REDIS_PORT", "6379")
REDIS_DB = env("REDIS_DB", "0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_DEFAULT_EXCHANGE = "air-monitor"
CELERY_TASK_DEFAULT_EXCHANGE_TYPE = "direct"
CELERY_TASK_DEFAULT_ROUTING_KEY = "default"
CELERY_TASK_QUEUES = (
    Queue("default", Exchange("air-monitor"), routing_key="default"),
    Queue("monitoring", Exchange("air-monitor"), routing_key="monitoring"),
    Queue("ml", Exchange("air-monitor"), routing_key="ml"),
)
CELERY_TASK_ROUTES = {
    "apps.monitoring.tasks.collect_recent_observations": {"queue": "monitoring", "routing_key": "monitoring"},
    "apps.monitoring.tasks.collect_observations_window": {"queue": "monitoring", "routing_key": "monitoring"},
    "apps.monitoring.tasks.build_dataset_snapshot": {"queue": "ml", "routing_key": "ml"},
    "apps.monitoring.tasks.train_model_version": {"queue": "ml", "routing_key": "ml"},
    "apps.monitoring.tasks.generate_forecast_run": {"queue": "ml", "routing_key": "ml"},
    "apps.monitoring.tasks.generate_hourly_forecast": {"queue": "ml", "routing_key": "ml"},
}
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 900)
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 1200)
CELERY_WORKER_MAX_TASKS_PER_CHILD = env_int("CELERY_WORKER_MAX_TASKS_PER_CHILD", 100)
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": env_int("CELERY_VISIBILITY_TIMEOUT", 3600)}
CELERY_BEAT_SCHEDULE_FILENAME = env("CELERY_BEAT_SCHEDULE_FILENAME", str(BASE_DIR / "run" / "celerybeat-schedule"))
CELERY_BEAT_SCHEDULE = {
    "collect-recent-observations-hourly": {
        "task": "apps.monitoring.tasks.collect_recent_observations",
        "schedule": crontab(minute=5),
    },
    "generate-forecast-hourly": {
        "task": "apps.monitoring.tasks.generate_hourly_forecast",
        "schedule": crontab(minute=15),
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "request": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "request_console": {
            "class": "logging.StreamHandler",
            "formatter": "request",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "api.requests": {
            "handlers": ["request_console"],
            "level": env("API_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "apps.authentication": {
            "handlers": ["console"],
            "level": env("AUTH_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "apps.monitoring": {
            "handlers": ["console"],
            "level": env("MONITORING_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": env("CELERY_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "celery.app.trace": {
            "handlers": ["console"],
            "level": env("CELERY_TRACE_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": env("DJANGO_DB_LOG_LEVEL", "WARNING"),
            "propagate": False,
        },
    },
}
