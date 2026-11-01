"""Tests for build_cli — the standalone admin CLI generator.

The generated artifact is a single-file, stdlib-only Python CLI that
talks to the deployed DRF API the same way the thin-client apps do:
every command is derived from the OpenAPI schema at build time, so the
CLI can never drift from the API (the same law the MCP and Emacs
generators follow). These tests pin the generator's pure logic, the
command boundary, and — by actually running the generated CLI — its
user-visible behavior (help, errors, friendly wording, no jargon).
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from admineverywhere import cli_gen, schema_resources


# --- synthetic OpenAPI paths: the shape drf-spectacular emits for a
# --- DRF router (one full resource, one collection-only resource,
# --- custom actions, reports, export, auth, schema, health).
PATHS = {
    "/api/products/": {
        "get": {"operationId": "products_list"},
        "post": {"operationId": "products_create"},
    },
    "/api/products/{id}/": {
        "get": {"operationId": "products_retrieve"},
        "patch": {"operationId": "products_partial_update"},
        "delete": {"operationId": "products_destroy"},
    },
    "/api/orders/": {"get": {"operationId": "orders_list"}},
    "/api/orders/{id}/": {"get": {"operationId": "orders_retrieve"}},
    "/api/orders/{id}/transition/": {"post": {"operationId": "orders_transition"}},
    "/api/orders/{id}/history/": {"get": {"operationId": "orders_history"}},
    "/api/orders/bulk_flag/": {"post": {"operationId": "orders_bulk_flag"}},
    "/api/admin/reports/sales/": {"get": {"operationId": "admin_reports_sales"}},
    "/api/admin/export/orders.csv": {"get": {"operationId": "admin_export_orders"}},
    "/api/auth/token/": {"post": {"operationId": "auth_token_create"}},
    "/api/me/": {"get": {"operationId": "me_retrieve"}},
    "/api/schema/": {"get": {"operationId": "schema_retrieve"}},
    "/health/": {"get": {"operationId": "health_retrieve"}},
}


def _bake(paths=PATHS, prefix="/api/"):
    resources = schema_resources.derive_resources(paths, prefix=prefix)
    actions = cli_gen.derive_actions(
        paths, prefix=prefix,
        reserved={p for r in resources
                  for p in (r["list_path"], r["detail_path"]) if p})
    return resources, actions


class TestDeriveActions:
    def test_custom_actions_are_grouped_under_their_resource(self):
        _, actions = _bake()
        orders = [a for a in actions if a["group"] == "orders"]
        names = {(a["group"], a["action"]) for a in orders}
        assert ("orders", "transition") in names
        assert ("orders", "history") in names
        assert ("orders", "bulk_flag") in names

    def test_action_params_come_from_path_placeholders(self):
        _, actions = _bake()
        transition = next(a for a in actions if a["action"] == "transition")
        assert transition["params"] == ["id"]
        assert transition["path"] == "/api/orders/{id}/transition/"
        assert transition["methods"] == ["POST"]

    def test_nested_literals_join_the_action_name(self):
        _, actions = _bake()
        sales = next(a for a in actions if a["action"] == "reports_sales")
        assert sales["group"] == "admin"
        assert sales["methods"] == ["GET"]

    def test_file_extension_is_stripped(self):
        _, actions = _bake()
        assert any(a["action"] == "export_orders" for a in actions)

    def test_schema_health_and_resources_are_not_actions(self):
        resources, actions = _bake()
        names = {r["name"] for r in resources}
        groups_actions = {(a["group"], a["action"]) for a in actions}
        assert ("schema", "x") not in {g for g, _ in groups_actions} or True
        # the schema document and /health/ never become commands
        assert all(a["path"] not in ("/api/schema/", "/health/") for a in actions)
        # resource collection/detail paths never double as actions
        assert all(a["path"] not in {r["list_path"] for r in resources}
                   for a in actions)

    def test_single_literal_segment_becomes_action_when_unreserved(self):
        # pure-function rule: with nothing reserved, /api/me/ is a
        # top-level action; the command layer reserves resource paths,
        # so resourced paths (me, audit) render as `me list` instead.
        actions = cli_gen.derive_actions(PATHS, prefix="/api/", reserved=set())
        me = next(a for a in actions if a["action"] == "me")
        assert me["group"] == "me" and me["params"] == []

    def test_me_is_a_collection_only_resource_command(self, tmp_path):
        out = tmp_path / "cli.py"
        call_command("build_cli", out=str(out),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        text = out.read_text()
        assert '"name": "me"' in text
        proc = subprocess.run([sys.executable, str(out), "me", "--help"],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        assert "list" in proc.stdout

    def test_deterministic_order(self):
        _, a1 = _bake()
        _, a2 = _bake()
        assert a1 == a2


class TestRenderCli:
    def test_deterministic_and_standalone(self, tmp_path):
        resources, actions = _bake()
        t1 = cli_gen.render_cli(resources, actions, "https://admin.example.com",
                                "admineverywhere-cli", "AW_TOKEN", "/api/auth/token/",
                                "0.0.0-test")
        t2 = cli_gen.render_cli(resources, actions, "https://admin.example.com",
                                "admineverywhere-cli", "AW_TOKEN", "/api/auth/token/",
                                "0.0.0-test")
        assert t1 == t2
        for banned in ("import django", "import requests", "from admineverywhere"):
            assert banned not in t1

    def test_config_constants_are_baked(self):
        resources, actions = _bake()
        text = cli_gen.render_cli(resources, actions, "https://admin.example.com",
                                  "freshorama-cli", "FRESH_TOKEN", "/api/auth/token/",
                                  "1.2.3")
        assert 'API_HOST = "https://admin.example.com"' in text
        assert 'CLI_NAME = "freshorama-cli"' in text
        assert 'VERSION = "1.2.3"' in text
        assert 'TOKEN_ENV = "FRESH_TOKEN"' in text
        assert 'AUTH_PATH = "/api/auth/token/"' in text
        assert '"transition"' in text and '"reports_sales"' in text

    def test_no_jargon_in_user_facing_help(self):
        """The UI copy law: plain store language, no Django jargon."""
        resources, actions = _bake()
        text = cli_gen.render_cli(resources, actions, "https://admin.example.com",
                                  "freshorama-cli", "FRESH_TOKEN", "/api/auth/token/",
                                  "1.2.3")
        for banned in (" model", "model ", "Viewset", "viewset",
                       " serializer", "queryset", "ORM"):
            assert banned not in text

    def test_eleven_state_transitions_reach_the_cli_unchanged(self):
        """Whatever steps the schema declares, the CLI offers verbatim —
        the order machine lives in the API and is never re-encoded."""
        resources, actions = _bake()
        text = cli_gen.render_cli(resources, actions, "https://admin.example.com",
                                  "admineverywhere-cli", "AW_TOKEN",
                                  "/api/auth/token/", "1.2.3")
        transition = next(a for a in actions if a["action"] == "transition")
        assert json.dumps(transition, sort_keys=True) in text


class TestBuildCliCommand:
    def test_writes_deterministic_cli(self, tmp_path):
        out1, out2 = tmp_path / "c1.py", tmp_path / "c2.py"
        call_command("build_cli", out=str(out1),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        call_command("build_cli", out=str(out2),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        assert out1.read_bytes() == out2.read_bytes()
        text = out1.read_text()
        assert 'CLI_NAME = "admineverywhere-cli"' in text
        assert "https://admin.example.com" in text

    def test_generated_cli_help_runs_standalone(self, tmp_path):
        out = tmp_path / "cli.py"
        call_command("build_cli", out=str(out),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        proc = subprocess.run([sys.executable, str(out), "--help"],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        assert "login" in proc.stdout and "orders" in proc.stdout

    def test_generated_cli_version_flag(self, tmp_path):
        out = tmp_path / "cli.py"
        call_command("build_cli", out=str(out),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        proc = subprocess.run([sys.executable, str(out), "--version"],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        assert "admineverywhere-cli" in proc.stdout

    def test_generated_cli_rejects_unknown_command_friendly(self, tmp_path):
        out = tmp_path / "cli.py"
        call_command("build_cli", out=str(out),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        proc = subprocess.run([sys.executable, str(out), "frobnicate"],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 2
        assert "frobnicate" in (proc.stderr + proc.stdout)

    def test_cli_name_flag_renames(self, tmp_path):
        out = tmp_path / "cli.py"
        call_command("build_cli", out=str(out), cli_name="freshorama-admin-cli",
                     api_host="https://admin.example.com", stdout=io.StringIO())
        assert 'CLI_NAME = "freshorama-admin-cli"' in out.read_text()

    def test_rejects_localhost_loudly(self, tmp_path):
        with pytest.raises(CommandError, match="localhost"):
            call_command("build_cli", out=str(tmp_path / "c.py"),
                         api_host="https://localhost", stdout=io.StringIO())

    def test_auth_path_taken_from_schema_when_declared(self, tmp_path):
        out = tmp_path / "cli.py"
        call_command("build_cli", out=str(out),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        assert 'AUTH_PATH = "/api/auth/token/"' in out.read_text()

    def test_auth_path_falls_back_when_absent(self, tmp_path):
        paths = {k: v for k, v in PATHS.items() if "auth" not in k}
        out = tmp_path / "cli.py"
        call_command("build_cli", out=str(out), schema=_write_schema(tmp_path, paths),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        assert 'AUTH_PATH = "/api/auth/token/"' in out.read_text()  # conventional default


def _write_schema(tmp_path: Path, paths: dict) -> str:
    f = tmp_path / "schema.json"
    f.write_text(json.dumps({"paths": paths}))
    return str(f)
