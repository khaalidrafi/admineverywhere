"""Shared pytest setup: minimal Django settings so management commands run.

We configure Django in-memory here (no DB needed — branding is pure I/O),
plus the runtime-branding API surface: DRF authtoken (auth fixture) and
ROOT_URLCONF pointing at the real shipped admincraft.urlconf.

FR-R001 merge note: the demo rig (shop + DRF extras) is mounted in the same
configure() block so test_order_lifecycle.py can exercise the live order API
contract in-process; demo-backend is prepended to sys.path because CI runs
pytest from the repo root. The rig's URLconf/DRF policy is scoped to that
module only (see _demo_rig) so every other module keeps exactly the
configuration it shipped with. Still no pytest-django — Django's own test
utilities create/teardown the per-module test database.
"""
import sys
from pathlib import Path

import django
import pytest
from django.conf import settings

DEMO_ROOT = Path(__file__).resolve().parents[2] / "demo-backend"

# Modules (basenames) that run against the demo rig.
DEMO_RIG_MODULES = {
    "test_order_lifecycle",
    "test_audit_actions",
    "test_csv_export",
    "test_rbac_roles",
    "test_seed_demo",
}

# Demo-rig DRF policy (lives here so the override stays in one place).
DEMO_REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
DEMO_SPECTACULAR_SETTINGS = {
    "TITLE": "Demo Shop API (test)",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Mirror core/settings.py:66 — without it the in-process document differs
    # from the live rig on 12 of 13 paths and can never guard the client's
    # proof fixture (test_schema_drift.py measures the parity this keeps).
    "COMPONENT_SPLIT_REQUEST": True,
}


def pytest_configure():
    if str(DEMO_ROOT) not in sys.path:
        sys.path.insert(0, str(DEMO_ROOT))
    # INSTALLED_APPS below names the plugin, and the documented `pip install -e
    # ../plugin` is impossible on a lane without setuptools: boot it from this
    # checkout instead of dying with INTERNALERROR over a seat's diff.
    from core.devpaths import ensure_admincraft_on_path
    ensure_admincraft_on_path()
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
                # FR-R001 demo rig: shop app + DRF schema/docs stack
                "drf_spectacular",
                "corsheaders",
                "shop",
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


@pytest.fixture(autouse=True)
def _demo_rig(request):
    """Scope the demo rig's URLconf + DRF policy to the rig modules.

    Every other module (upstream branding/API tests included) runs under the
    exact configuration it shipped with; the FR-R001/FR-R003 modules
    (test_order_lifecycle, test_audit_actions) additionally get
    ROOT_URLCONF=core.urls and the demo REST_FRAMEWORK/SPECTACULAR
    policy for the duration of each test (including the spectacular schema
    generation call).
    """
    if request.module.__name__.split(".")[-1] not in DEMO_RIG_MODULES:
        yield
        return
    from django.test.utils import override_settings

    with override_settings(
        ROOT_URLCONF="core.urls",
        REST_FRAMEWORK=DEMO_REST_FRAMEWORK,
        SPECTACULAR_SETTINGS=DEMO_SPECTACULAR_SETTINGS,
    ):
        yield
