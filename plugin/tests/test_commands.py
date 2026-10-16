"""Tests for management commands build_admin + dump_schema."""
import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest
from django.core.management import CommandError, call_command

from admincraft import branding

from test_branding import VALID_BRAND, TINY_PNG, TINY_SVG  # noqa: F401


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
        "app": {"windows": [{"title": "Old"}]},
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
