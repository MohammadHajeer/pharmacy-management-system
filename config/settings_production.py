"""Production settings for the Render deployment.

The existing ``config.settings`` module remains the local-development
configuration. Render selects this module through ``DJANGO_SETTINGS_MODULE``.
"""

import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


def _required_environment_value(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in the production environment.")
    return value


def _csv_environment_values(name):
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


SECRET_KEY = _required_environment_value("DJANGO_SECRET_KEY")
DEBUG = False

render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
ALLOWED_HOSTS = _csv_environment_values("ALLOWED_HOSTS")
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS or RENDER_EXTERNAL_HOSTNAME must be set in production."
    )

CSRF_TRUSTED_ORIGINS = _csv_environment_values("CSRF_TRUSTED_ORIGINS")
render_origin = f"https://{render_hostname}" if render_hostname else ""
if render_origin and render_origin not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(render_origin)

database_url = _required_environment_value("DATABASE_URL")
DATABASES = {
    "default": dj_database_url.parse(
        database_url,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )
}

# Keep the browser-reload app installed because Mohammad's shared base template
# loads its tag library. With DEBUG disabled the tag emits nothing; production
# additionally removes its middleware and URL endpoint below.
MIDDLEWARE = [  # noqa: F405
    middleware
    for middleware in MIDDLEWARE
    if middleware != "django_browser_reload.middleware.BrowserReloadMiddleware"
]
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
ROOT_URLCONF = "config.urls_production"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# The current Phase 1 application does not send email. Keep a production SMTP
# backend configured so future mail never falls back to the development console
# backend; operators can provide SMTP values without a code change.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": os.getenv("EMAIL_HOST", "localhost"),
            "port": int(os.getenv("EMAIL_PORT", "25")),
            "username": os.getenv("EMAIL_HOST_USER") or None,
            "password": os.getenv("EMAIL_HOST_PASSWORD") or None,
            "use_tls": os.getenv("EMAIL_USE_TLS", "false").lower() == "true",
            "use_ssl": os.getenv("EMAIL_USE_SSL", "false").lower() == "true",
            "timeout": 10,
        },
    }
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
