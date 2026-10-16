"""Shared pytest setup: minimal Django settings so management commands run.

We configure Django in-memory here (no DB needed — branding is pure I/O).
"""
import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "ai_dashboard",
            ],
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            USE_TZ=True,
        )
        django.setup()
