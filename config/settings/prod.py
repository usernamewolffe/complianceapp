from .base import *
import os
import dj_database_url
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

DEBUG = False
ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h]

DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=600,
        ssl_require=os.getenv("DB_SSL_REQUIRE", "true").lower() == "true",
    )
}

def env_bool(name, default="true"):
    return os.getenv(name, default).lower() == "true"

# HTTPS & cookies (toggle locally with envs)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", "true")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", "true")
CSRF_COOKIE_SECURE   = env_bool("CSRF_COOKIE_SECURE", "true")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", "true")
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", "true")

dsn = os.getenv("SENTRY_DSN")
if dsn:
    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration()],
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
    )
