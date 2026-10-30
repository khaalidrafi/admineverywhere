"""Tests for build_emacs — the Org-powered Emacs admin client generator.

The generated artifact is a single-file Emacs package: an Org buffer per
API resource (paginated for large data), Org TODO write-back, record
editing via properties drawers, and a plain-text AI helper. Tests pin
the generator's output shape and determinism; the elisp byte-compile leg
runs only where emacs exists (CI builders do not ship it).
"""
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

SCHEMA = {"paths": {
    "/api/products/": {"get": {}, "post": {}},
    "/api/products/{id}/": {"get": {}, "patch": {}, "delete": {}},
    "/api/orders/": {"get": {}, "post": {}},
    "/api/orders/{id}/": {"get": {}, "patch": {}},
}}


@pytest.fixture
def schema_file(tmp_path):
    p = tmp_path / "schema.json"
    p.write_text(json.dumps(SCHEMA))
    return p


def _build(tmp_path, schema_file, **extra):
    out = tmp_path / "client.el"
    call_command("build_emacs", out=str(out), schema=str(schema_file),
                 api_host="https://admin.example.com", stdout=io.StringIO(), **extra)
    return out


class TestBuildEmacsCommand:
    def test_writes_deterministic_single_file_package(self, tmp_path, schema_file):
        out1, out2 = _build(tmp_path, schema_file), _build(tmp_path, schema_file)
        assert out1.read_bytes() == out2.read_bytes()
        text = out1.read_text()
        assert "-*- lexical-binding: t; -*-" in text
        # standalone: no framework imports, no baked secrets
        for banned in ("admineverywhere-brand", "token123", "import "):
            assert banned not in text

    def test_package_headers_and_setup_snippet(self, tmp_path, schema_file):
        text = _build(tmp_path, schema_file, package_name="freshorama-admin").read_text()
        assert ";;; freshorama-admin.el --- Org-powered admin client" in text
        assert "(provide 'freshorama-admin)" in text
        # the global law: setup code ships as use-package
        assert "(use-package freshorama-admin" in text
        assert 'aw-api-host "https://admin.example.com"' in text

    def test_org_surfaces_baked_for_each_resource(self, tmp_path, schema_file):
        text = _build(tmp_path, schema_file).read_text()
        for marker in ("defun aw-open", "defun aw-todos", "defun aw-ask",
                       "defun aw--request", "defun aw--page-next",
                       "org-after-todo-state-change", ":PROPERTIES:"):
            assert marker in text
        assert "products" in text and "orders" in text

    def test_large_data_defaults(self, tmp_path, schema_file):
        text = _build(tmp_path, schema_file).read_text()
        assert 'aw-page-size 50' in text

    def test_rejects_localhost_loudly(self, tmp_path, schema_file):
        with pytest.raises(CommandError, match="localhost"):
            call_command("build_emacs", out=str(tmp_path / "x.el"),
                         schema=str(schema_file), api_host="https://localhost",
                         stdout=io.StringIO())

    @pytest.mark.skipif(shutil.which("emacs") is None,
                        reason="emacs not installed on this machine")
    def test_elisp_byte_compiles(self, tmp_path, schema_file):
        out = _build(tmp_path, schema_file)
        proc = subprocess.run(
            ["emacs", "--batch", "-Q", "-f", "batch-byte-compile", str(out)],
            capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
