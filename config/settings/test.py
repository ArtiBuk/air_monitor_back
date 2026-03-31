from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = False

TEST_DB_DIR = BASE_DIR / ".testdb"
TEST_DB_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": TEST_DB_DIR / "db.sqlite3",
        "TEST": {
            "NAME": TEST_DB_DIR / "test_db.sqlite3",
        },
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_STORE_EAGER_RESULT = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

JWT_COOKIE_SECURE = False
