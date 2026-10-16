"""P0: demo-backend dev-only settings must warn loudly at import.

The demo rig runs wide open (DEBUG=True, ALLOWED_HOSTS=['*'],
CORS_ALLOW_ALL_ORIGINS=True). Anyone importing these settings outside the
local demo must be told immediately — at startup, not in an incident
review. Loads the real settings module from the repo via a file import
(the rest of the plugin suite uses conftest's own minimal settings and
never touches this file).
"""
import importlib.util
from pathlib import Path

import pytest

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "demo-backend" / "core" / "settings.py"


def _import_settings():
    spec = importlib.util.spec_from_file_location("demo_settings_under_test", SETTINGS_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDevOnlyWarning:
    def test_warns_without_explicit_dev_flag(self, monkeypatch):
        monkeypatch.delenv("DEMO_DEV", raising=False)
        with pytest.warns(UserWarning, match="DEV-ONLY"):
            _import_settings()

    def test_silent_with_explicit_dev_flag(self, monkeypatch, recwarn):
        monkeypatch.setenv("DEMO_DEV", "1")
        mod = _import_settings()
        # no DEV-ONLY warning once explicitly acknowledged ...
        assert not [w for w in recwarn if "DEV-ONLY" in str(w.message)]
        # ... and the behavior itself is unchanged (a loud warning, not a fix)
        assert mod.DEBUG is True
        assert mod.CORS_ALLOW_ALL_ORIGINS is True
        assert mod.ALLOWED_HOSTS == ["*"]
