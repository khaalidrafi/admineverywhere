"""
Django settings for the demo backend. DEV-ONLY values are marked.
Everything aggressive here (CORS allow-all, DEBUG) is intentional for
local testing only — see AI-REVIEW.org before reusing anywhere.
"""
import os
import sys
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-only-not-secret"
DEBUG = True  # DEV ONLY
ALLOWED_HOSTS = ["*"]  # DEV ONLY

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "corsheaders",
    "admineverywhere",  # the plugin under test (pip install -e ../plugin)
    "shop",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# DEV ONLY: the SPA runs on localhost:5173 (vite) and inside Tauri.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = ["*"]

ROOT_URLCONF = "core.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": []},
}]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Demo Shop API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,  # separate request/response schemas
}

# Runtime brand store for the in-app branding editor (see
# admineverywhere.brandstore): one dir with brand.json + logo/favicon. The
# editor creates it on first save; until then the client shows its
# bundled static brand. Runtime state — never commit it.
ADMINEVERYWHERE_BRAND_DIR = BASE_DIR / "admineverywhere_brand"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# P0: loud dev-only guard — the aggressive values above are intentionally
# UNCHANGED. This rig runs wide open (tracebacks on, any host, any origin).
# Anyone importing these settings outside the local demo must find out at
# startup, not in an incident review:
#   * SERVING invocations (runserver, gunicorn, uwsgi, daphne, ... or a bare
#     wsgi/asgi script) hard-exit without the explicit ack — FR-R007 phase b
#     (2026-11-02 audit follow-up): a warning scrolls past nobody during a
#     deploy of the rig with real data; a wall stops it.
#   * every other invocation (check, migrate, shell, the gate legs, the test
#     runner) keeps the loud UserWarning, so CI and developer tooling never
#     feel the gate.
# Acknowledge the demo rig explicitly to serve it:  DEMO_DEV=1 manage.py runserver
# ---------------------------------------------------------------------------
_SERVING_MARKERS = (
    "runserver",
    "gunicorn",
    "uwsgi",
    "daphne",
    "hypercorn",
    "granian",
    "wsgi",
    "asgi",
)


def _is_serving_invocation() -> bool:
    """True when the process booting these settings would serve requests.

    Settings are imported during management-command execution, so sys.argv
    names the command at this point. The markers substring-match the joined
    argv, which covers every shape a deploy actually tries: the subcommand
    (``manage.py runserver``), the server binary (``/usr/local/bin/daphne``),
    the WSGI/ASGI module tail (``gunicorn core.wsgi:application``) and bare
    entry-point scripts (``python core/wsgi.py``). Failing closed is the
    point: a path that merely LOOKS like serving gets the same wall, and
    the ack is one environment variable away.
    """
    joined = " ".join(sys.argv or [])
    return any(marker in joined for marker in _SERVING_MARKERS)


def _dev_only_active() -> list[str]:
    """Names of the dangerous demo values that are currently switched on."""
    active = []
    if DEBUG:
        active.append("DEBUG=True")
    if "*" in ALLOWED_HOSTS:
        active.append("ALLOWED_HOSTS=['*']")
    if CORS_ALLOW_ALL_ORIGINS:
        active.append("CORS_ALLOW_ALL_ORIGINS=True")
    if CORS_ALLOW_HEADERS == ["*"]:
        active.append("CORS_ALLOW_HEADERS=['*']")
    return active


if _dev_only_active() and os.environ.get("DEMO_DEV") != "1":
    if _is_serving_invocation():
        raise SystemExit(
            "demo-backend settings are DEV-ONLY ("
            + ", ".join(_dev_only_active())
            + ") — refusing to serve. This rig must never face a real network: "
            "deploy the host project's own settings instead. To run the local "
            "demo, acknowledge explicitly with DEMO_DEV=1."
        )
    warnings.warn(
        "demo-backend settings are DEV-ONLY ("
        + ", ".join(_dev_only_active())
        + ") — never deploy this rig; see AI-REVIEW.org. "
        "Set DEMO_DEV=1 to acknowledge and silence this warning.",
        stacklevel=2,
    )
