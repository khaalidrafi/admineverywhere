"""P0: demo-backend dev-only settings must warn loudly at import — and
REFUSE TO SERVE without the explicit ack.

The demo rig runs wide open (DEBUG=True, ALLOWED_HOSTS=['*'],
CORS_ALLOW_ALL_ORIGINS=True). Anyone importing these settings outside the
local demo must be told immediately — at startup, not in an incident
review. Since FR-R007 phase b (2026-11-02 audit follow-up) a warning is
not enough for the one case that matters: actually SERVING. A deploy of
the rig with real data scrolls the warning past nobody, so any serving
invocation (runserver/gunicorn/uwsgi/...) hard-exits unless DEMO_DEV=1
acknowledges the demo context; non-serving commands (check, migrate,
shell, the gate legs) keep the warning-only behavior so CI and developer
tooling never feel the gate. Loads the real settings module from the
repo via a file import (the rest of the plugin suite uses conftest's own
minimal settings and never touches this file).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "demo-backend" / "core" / "settings.py"


def _import_settings(argv=None):
    if argv is not None:
        sys.argv = argv
    spec = importlib.util.spec_from_file_location("demo_settings_under_test", SETTINGS_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDevOnlyWarning:
    def test_warns_without_explicit_dev_flag(self, monkeypatch):
        monkeypatch.delenv("DEMO_DEV", raising=False)
        monkeypatch.setattr(sys, "argv", ["manage.py", "check"])
        with pytest.warns(UserWarning, match="DEV-ONLY"):
            _import_settings()

    def test_silent_with_explicit_dev_flag(self, monkeypatch, recwarn):
        monkeypatch.setenv("DEMO_DEV", "1")
        monkeypatch.setattr(sys, "argv", ["manage.py", "check"])
        mod = _import_settings()
        # no DEV-ONLY warning once explicitly acknowledged ...
        assert not [w for w in recwarn if "DEV-ONLY" in str(w.message)]
        # ... and the behavior itself is unchanged (a loud warning, not a fix)
        assert mod.DEBUG is True
        assert mod.CORS_ALLOW_ALL_ORIGINS is True
        assert mod.ALLOWED_HOSTS == ["*"]


class TestServingHardExit:
    """The gate that turns the warning into a wall: serving dies, tooling
    does not. manage.py check / makemigrations (the landing-gate legs and
    the CI review workflow) must keep working without DEMO_DEV."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["manage.py", "runserver", "--noreload"],
            ["gunicorn", "core.wsgi:application", "-b", "0.0.0.0:8000"],
            ["uwsgi", "--http", ":8000", "--module", "core.wsgi"],
            ["/usr/local/bin/daphne", "-p", "8000", "core.asgi:application"],
            ["python", "/srv/demo/core/wsgi.py"],
        ],
    )
    def test_serving_without_ack_is_fatal(self, monkeypatch, argv):
        monkeypatch.delenv("DEMO_DEV", raising=False)
        with pytest.raises(SystemExit, match="DEV-ONLY"):
            _import_settings(argv)

    def test_serving_with_ack_boots(self, monkeypatch):
        monkeypatch.setenv("DEMO_DEV", "1")
        mod = _import_settings(["manage.py", "runserver", "--noreload"])
        assert mod.DEBUG is True  # the ack keeps the demo posture intact

    @pytest.mark.parametrize(
        "argv",
        [
            ["manage.py", "check"],
            ["manage.py", "makemigrations", "--check", "--dry-run"],
            ["manage.py", "shell"],
            ["manage.py", "seed_demo", "--verbosity", "0"],
            ["pytest", "plugin/tests"],
        ],
    )
    def test_non_serving_commands_warn_but_run(self, monkeypatch, argv):
        monkeypatch.delenv("DEMO_DEV", raising=False)
        with pytest.warns(UserWarning, match="DEV-ONLY"):
            mod = _import_settings(argv)
        assert mod.DEBUG is True  # warning only — no exit for tooling

    def test_empty_argv_defaults_to_warning_not_exit(self, monkeypatch):
        monkeypatch.delenv("DEMO_DEV", raising=False)
        with pytest.warns(UserWarning, match="DEV-ONLY"):
            _import_settings([])
