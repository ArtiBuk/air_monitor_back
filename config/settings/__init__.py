from .base import *  # noqa: F401,F403

environment = globals().get("ENVIRONMENT", "local")

if environment == "production":
    from .production import *  # noqa: F401,F403
elif environment == "test":
    from .test import *  # noqa: F401,F403
else:
    from .local import *  # noqa: F401,F403
