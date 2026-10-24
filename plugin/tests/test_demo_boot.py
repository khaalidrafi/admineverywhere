"""P0 boot gate: the demo rig must actually boot, not just import.

Nothing in this suite used to prove the demo backend works: branding is pure
I/O and conftest configures its own minimal in-memory settings, so no test
ever imported `core.urls`. `381bed3` (package rename) deleted
`demo-backend/shop/urls.py` while `core/urls.py:15` kept
`include("shop.urls")` — 48/48 green on a rig that died on the first request.
This file is the check that was missing.

Deliberately runs the probe in a SUBPROCESS rather than in-process: conftest
has already called django.setup() with the plugin's minimal settings, and
Django settings are process-global and immutable once configured. A child
interpreter is the only way to boot the *real* settings module here, and it
also matches how the rig is actually started (`manage.py runserver`).

Skips only when demo-backend/manage.py is absent (a plugin-only checkout).
It does NOT skip when the boot fails — a missing dependency or a broken
URLConf must read as a failure, which is the whole point.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO_ROOT = Path(__file__).resolve().parents[2] / "demo-backend"

pytestmark = pytest.mark.skipif(
    not (DEMO_ROOT / "manage.py").exists(),
    reason="demo-backend not present (plugin-only checkout)",
)

# Boots the real settings module, runs Django's system checks (the same ones
# `manage.py check` runs, incl. django.core.checks.urls.check_url_config,
# which imports ROOT_URLCONF and is what fails on a deleted URLConf), then
# resolves the routes we care about. Prints one JSON object on the last line.
BOOT_PROBE = """
import json, sys
import django
django.setup()
from django.core.management import call_command
from django.urls import resolve

try:
    call_command("check")
    check_ok = True
except SystemExit as exc:                      # check returns non-zero via SystemExit
    check_ok = exc.code == 0
except Exception:
    check_ok = False

resolved = {}
for path in ["/api/auth/token/", "/api/products/", "/api/schema/"]:
    try:
        match = resolve(path)
        # DRF's as_view() hands back a plain function named `view`; the real
        # identity of an APIView route is its `cls`, not `func.__name__`.
        view_cls = getattr(match.func, "cls", None)
        resolved[path] = {
            "callback": getattr(match.func, "__name__", "?"),
            "cls": getattr(view_cls, "__name__", None),
            "cls_module": getattr(view_cls, "__module__", None),
            "url_name": match.url_name,
        }
    except Exception as exc:
        resolved[path] = {"error": type(exc).__name__}

print(json.dumps({"check_ok": check_ok, "resolved": resolved}))
"""


@pytest.fixture(scope="session")
def boot_probe():
    """One subprocess boot per session, shared by every assertion below."""
    from core.devpaths import child_pythonpath

    env = {
        **os.environ,
        # manage.py puts its own dir on sys.path; a bare -c script does not,
        # so `core` and `shop` need it explicitly — and so does the plugin,
        # because this env overwrites any inherited PYTHONPATH by design.
        "PYTHONPATH": child_pythonpath(str(DEMO_ROOT)),
        "DJANGO_SETTINGS_MODULE": "core.settings",
        "DEMO_DEV": "1",  # ack for the DEV-ONLY settings warning (see settings.py)
    }
    proc = subprocess.run(
        [sys.executable, "-c", BOOT_PROBE],
        cwd=str(DEMO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    stdout_lines = proc.stdout.strip().splitlines()
    payload = stdout_lines[-1] if stdout_lines else ""
    return {
        "returncode": proc.returncode,
        "data": json.loads(payload) if payload.startswith("{") else None,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _fail_detail(boot):
    return (
        f"rc={boot['returncode']}\n"
        f"--- stdout ---\n{boot['stdout']}\n"
        f"--- stderr ---\n{boot['stderr'][-2000:]}"
    )


class TestDemoBootGate:
    def test_probe_process_exits_clean(self, boot_probe):
        # A crash during import/setup exits non-zero before any JSON is printed.
        assert boot_probe["data"] is not None, _fail_detail(boot_probe)

    def test_system_check_passes(self, boot_probe):
        assert boot_probe["data"]["check_ok"] is True, _fail_detail(boot_probe)

    def test_token_post_path_is_pinned_in_code(self, boot_probe):
        """`api/auth/token/` must resolve to DRF's token view.

        The MVP smoke ticket told the operator to POST to `/api-token-auth/`,
        which is Django's default path and 404s on this rig — core/urls.py:10
        mounts it as `api/auth/token/`. Pinning the working path here means the
        next person who writes a smoke doc gets told the truth by a red test.
        """
        match = boot_probe["data"]["resolved"]["/api/auth/token/"]
        assert "error" not in match, f"/api/auth/token/ does not resolve: {match}"
        assert match["cls"] == "ObtainAuthToken", match
        assert match["cls_module"] == "rest_framework.authtoken.views", match

    def test_shop_router_urls_resolve(self, boot_probe):
        """Proves `include("shop.urls")` — the exact module 381bed3 deleted."""
        match = boot_probe["data"]["resolved"]["/api/products/"]
        assert "error" not in match, f"/api/products/ does not resolve: {match}"
        assert match["url_name"] == "product-list", match

    def test_openapi_schema_route_resolves(self, boot_probe):
        """The thin client derives everything from this endpoint; boot must reach it."""
        match = boot_probe["data"]["resolved"]["/api/schema/"]
        assert "error" not in match, f"/api/schema/ does not resolve: {match}"
        assert match["url_name"] == "schema", match
