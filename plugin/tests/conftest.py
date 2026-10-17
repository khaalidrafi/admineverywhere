"""Shared pytest setup: minimal Django settings so management commands run.

We configure Django in-memory here (no DB needed — branding is pure I/O),
plus the runtime-branding API surface: DRF authtoken (auth fixture) and
ROOT_URLCONF pointing at the real shipped admincraft.urlconf.
"""
import django
import pytest
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            SECRET_KEY="pytest-only-not-secret",
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rest_framework",
                "rest_framework.authtoken",
                "admincraft",
            ],
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            ROOT_URLCONF="admincraft.urls",
            USE_TZ=True,
        )
        django.setup()


@pytest.fixture(scope="session", autouse=True)
def _migrate_db():
    """Create auth/token tables in the in-memory sqlite (no pytest-django)."""
    from django.core.management import call_command
    call_command("migrate", verbosity=0, interactive=False)
