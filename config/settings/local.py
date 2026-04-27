from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Allow all CORS in development
CORS_ALLOW_ALL_ORIGINS = True

# Show full errors in development
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
