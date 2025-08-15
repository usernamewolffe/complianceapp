from .base import *
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = list(INSTALLED_APPS) + [
    "incidents",
]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

