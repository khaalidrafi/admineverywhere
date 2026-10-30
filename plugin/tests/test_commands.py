"""Tests for management commands build_admin + dump_schema."""
import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest
from django.core.management import CommandError, call_command

from admineverywhere import branding

from test_branding import VALID_BRAND, TINY_PNG, TINY_SVG  # noqa: F401
from test_branding_api import PROD_CSP  # noqa: F401 (CSP tests moved there)


def _make_brand(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/logo.svg").write_bytes(TINY_SVG)
    (tmp_path / "assets/icon.png").write_bytes(TINY_PNG)
    (tmp_path / "brand.json").write_text(json.dumps(VALID_BRAND))
    return tmp_path / "brand.json"


def _make_app(tmp_path):
    app = tmp_path / "app"
    (app / "public").mkdir(parents=True)
    (app / "src-tauri").mkdir()
    (app / "src-tauri" / "tauri.conf.json").write_text(json.dumps({
        "productName": "Old",
        "app": {"windows": [{"title": "Old"}],
                "security": {"csp": PROD_CSP}},
    }))
    return app

class TestBuildAdminCommand:
    def test_rebrands_app(self, tmp_path):
        brand_path = _make_brand(tmp_path)
        app = _make_app(tmp_path)
        out = io.StringIO()
        call_command("build_admin", brand=str(brand_path), app=str(app), stdout=out)
        assert (app / "public" / "brand.css").exists()
        text = out.getvalue()
        assert "Freshorama" in text
        # command reports what it wrote
        assert "brand.css" in text

    def test_invalid_brand_fails_loudly(self, tmp_path):
        (tmp_path / "bad.json").write_text(json.dumps({"appName": "x"}))
        app = _make_app(tmp_path)
        with pytest.raises(Exception):
            call_command("build_admin", brand=str(tmp_path / "bad.json"),
                         app=str(app), stdout=io.StringIO())

    def test_missing_brand_path_fails(self, tmp_path):
        app = _make_app(tmp_path)
        with pytest.raises(CommandError, match="brand file not found"):
            call_command("build_admin", brand=str(tmp_path / "ghost.json"),
                         app=str(app), stdout=io.StringIO())


class TestDumpSchemaCommand:
    def test_fetches_and_writes_schema(self, tmp_path, monkeypatch):
        schema = {"openapi": "3.0.3", "paths": {"/api/products/": {}},
                  "info": {"title": "Demo Shop API"}}

        class FakeResponse:
            def read(self):
                return json.dumps(schema).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            FakeResponse.last_req = req
            return FakeResponse()

        monkeypatch.setattr(branding, "urlopen", fake_urlopen)
        out = tmp_path / "schema.json"
        call_command("dump_schema", url="http://x/api/schema/",
                     out=str(out), stdout=io.StringIO())
        assert json.loads(out.read_text())["paths"] == schema["paths"]
        # token auth header passed through when requested
        call_command("dump_schema", url="http://x/api/schema/",
                     out=str(out), token="tok123", stdout=io.StringIO())
        req = FakeResponse.last_req
        assert req.headers.get("Authorization") == "Token tok123"

    def test_connection_error_is_clean(self, tmp_path, monkeypatch):
        def boom(req, timeout=None):
            raise URLError("no server")
        monkeypatch.setattr(branding, "urlopen", boom)
        with pytest.raises(Exception):
            call_command("dump_schema", url="http://x/api/schema/",
                         out=str(tmp_path / "schema.json"), stdout=io.StringIO())


class TestBuildAdminApiHost:
    """--api-host: CSP placeholder substitution at the CLI boundary."""

    def test_substitutes_and_reports_origin(self, tmp_path):
        brand_path = _make_brand(tmp_path)
        app = _make_app(tmp_path)
        out = io.StringIO()
        call_command("build_admin", brand=str(brand_path), app=str(app),
                     api_host="admin.example.com", stdout=out)
        conf = json.loads((app / "src-tauri" / "tauri.conf.json").read_text())
        csp = conf["app"]["security"]["csp"]
        assert "https://admin.example.com" in csp
        assert "API_HOST" not in csp
        assert "csp connect-src -> https://admin.example.com" in out.getvalue()

    def test_rejects_localhost_loudly(self, tmp_path):
        brand_path = _make_brand(tmp_path)
        app = _make_app(tmp_path)
        with pytest.raises(CommandError, match="localhost"):
            call_command("build_admin", brand=str(brand_path), app=str(app),
                         api_host="https://localhost", stdout=io.StringIO())

    def test_rejects_wildcard_loudly(self, tmp_path):
        brand_path = _make_brand(tmp_path)
        app = _make_app(tmp_path)
        with pytest.raises(CommandError, match="wildcard"):
            call_command("build_admin", brand=str(brand_path), app=str(app),
                         api_host="https://*.example.com", stdout=io.StringIO())

    def test_drift_csp_without_placeholder_fails(self, tmp_path):
        # CSP already carries another origin: a new --api-host must fail
        # loudly instead of silently keeping the stale host
        brand_path = _make_brand(tmp_path)
        app = _make_app(tmp_path)
        conf_path = app / "src-tauri" / "tauri.conf.json"
        conf = json.loads(conf_path.read_text())
        conf["app"]["security"]["csp"] = PROD_CSP.replace(
            "https://API_HOST", "https://old.example.com")
        conf_path.write_text(json.dumps(conf))
        with pytest.raises(CommandError, match="drift"):
            call_command("build_admin", brand=str(brand_path), app=str(app),
                         api_host="https://admin.example.com", stdout=io.StringIO())


class TestBuildAdminTargets:
    """--targets: the user chooses what to build (web, desktop, android,
    mcp, emacs).  apk/exe/AppImage are what the desktop/android targets
    produce; mcp/emacs generate agent/Org tooling from the API schema."""

    def test_parse_targets_mapping_and_validation(self):
        from admineverywhere.management.commands.build_admin import parse_targets
        assert parse_targets(None, build=False) == []
        # legacy --build flag == web target, unchanged behavior
        assert parse_targets(None, build=True) == ["web"]
        assert parse_targets("mcp, emacs", build=False) == ["mcp", "emacs"]
        assert parse_targets("web", build=True) == ["web"]
        with pytest.raises(ValueError, match="bogus"):
            parse_targets("web,bogus", build=False)

    def test_targets_mcp_and_emacs_build_both(self, tmp_path, monkeypatch):
        from admineverywhere.management.commands.build_admin import (
            VALID_TARGETS,  # noqa: F401 — guards the flag docs against drift
        )
        monkeypatch.chdir(tmp_path)   # generated artifacts land in tmp cwd
        (tmp_path / "brand").mkdir()  # _make_brand expects an existing dir
        brand_path = _make_brand(tmp_path / "brand")
        app = _make_app(tmp_path / "app")
        out = io.StringIO()
        call_command("build_admin", brand=str(brand_path), app=str(app),
                     targets="mcp,emacs",
                     api_host="https://admin.example.com", stdout=out)
        assert (tmp_path / "mcp_admin_server.py").is_file()
        assert (tmp_path / "admineverywhere-admin.el").is_file()
        assert "MCP server written" in out.getvalue()
        assert "Emacs package written" in out.getvalue()

    def test_targets_invalid_rejected(self, tmp_path):
        brand_path = _make_brand(tmp_path)
        app = _make_app(tmp_path)
        with pytest.raises(CommandError, match="bogus"):
            call_command("build_admin", brand=str(brand_path), app=str(app),
                         targets="mcp,bogus", stdout=io.StringIO())
