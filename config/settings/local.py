from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Trust all ngrok and localhost origins in development
CSRF_TRUSTED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "https://*.ngrok-free.app",
    "https://*.ngrok-free.dev",
    "https://*.ngrok.io",
]

# Allow all CORS in development
CORS_ALLOW_ALL_ORIGINS = True

# Show full errors in development
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
