"""Tests for build_mcp — the MCP-server generator.

The generated artifact must be a standalone, stdlib-only MCP server:
agents point it at a DRF + drf-spectacular backend and control admin
tasks (CRUD per model + runtime branding) over the MCP stdio protocol.
These tests pin the generator's pure logic, the command boundary, and —
by actually running the generated server — the MCP handshake itself.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from admineverywhere import mcp_gen, schema_resources


# --- synthetic OpenAPI paths: the shape drf-spectacular emits for a
# --- DRF router with one ModelViewSet plus the schema endpoint.
PATHS = {
    "/api/products/": {
        "get": {"operationId": "products_list", "summary": "List products"},
        "post": {"operationId": "products_create"},
    },
    "/api/products/{id}/": {
        "get": {"operationId": "products_retrieve"},
        "put": {"operationId": "products_update"},
        "patch": {"operationId": "products_partial_update"},
        "delete": {"operationId": "products_destroy"},
    },
    "/api/orders/": {
        "get": {"operationId": "orders_list"},
        "post": {"operationId": "orders_create"},
    },
    "/api/orders/{id}/": {
        "get": {"operationId": "orders_retrieve"},
        "patch": {"operationId": "orders_partial_update"},
    },
    "/api/schema/": {"get": {"operationId": "schema_retrieve"}},
}


class TestDeriveResources:
    def test_crud_ops_from_list_and_detail_paths(self):
        resources = schema_resources.derive_resources(PATHS, prefix="/api/")
        by_name = {r["name"]: r for r in resources}
        assert set(by_name) == {"products", "orders"}  # /api/schema/ excluded
        products = by_name["products"]
        assert products["list_path"] == "/api/products/"
        assert products["detail_path"] == "/api/products/{id}/"
        assert products["create"] is True and products["update"] is True
        assert products["destroy"] is True

    def test_detail_methods_map_to_flags(self):
        by_name = {r["name"]: r for r in schema_resources.derive_resources(PATHS, prefix="/api/")}
        orders = by_name["orders"]
        assert orders["destroy"] is False          # no DELETE on detail
        assert orders["update"] is True            # PATCH counts as update

    def test_paths_outside_prefix_ignored(self):
        paths = {"/api/x/": {"get": {}}, "/other/y/": {"get": {}}}
        resources = schema_resources.derive_resources(paths, prefix="/api/")
        assert [r["name"] for r in resources] == ["x"]

    def test_collection_only_resource_has_no_detail(self):
        resources = schema_resources.derive_resources({"/api/ping/": {"get": {}}}, prefix="/api/")
        assert resources[0]["detail_path"] is None
        assert resources[0]["retrieve"] is False


class TestBuildTools:
    def test_tool_names_and_input_schemas(self):
        tools = schema_resources.build_tools(schema_resources.derive_resources(PATHS, prefix="/api/"))
        names = [t["name"] for t in tools]
        # Full roster: resources sorted by name, ops in fixed order, static
        # discovery/branding tools last. Deterministic — agents see a
        # stable tool list across regenerations.
        assert names == ["orders_list", "orders_retrieve", "orders_create",
                         "orders_update", "products_list", "products_retrieve",
                         "products_create", "products_update", "products_destroy",
                         "api_overview", "branding_get", "branding_set"]
        list_tool = tools[0]
        assert list_tool["inputSchema"]["type"] == "object"
        assert "page" in list_tool["inputSchema"]["properties"]
        assert list_tool["inputSchema"]["required"] == []

    def test_update_tool_takes_data_object(self):
        tools = schema_resources.build_tools(schema_resources.derive_resources(PATHS, prefix="/api/"))
        update = next(t for t in tools if t["name"] == "products_update")
        assert update["inputSchema"]["properties"]["data"]["type"] == "object"
        assert update["inputSchema"]["required"] == ["id", "data"]


class TestBuildMcpCommand:
    def test_writes_standalone_deterministic_server(self, tmp_path):
        out1, out2 = tmp_path / "s1.py", tmp_path / "s2.py"
        call_command("build_mcp", out=str(out1),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        call_command("build_mcp", out=str(out2),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        text = out1.read_text()
        assert out1.read_bytes() == out2.read_bytes()      # deterministic build
        assert 'DEFAULT_TOKEN_ENV = "ADMINEVERYWHERE_API_TOKEN"' in text
        assert "https://admin.example.com" in text
        assert "2024-11-05" in text                        # MCP protocol version
        assert "products_list" in text and "branding_set" in text
        # standalone: no framework imports in the generated artifact
        for banned in ("import django", "import requests", "from admineverywhere"):
            assert banned not in text

    def test_generated_server_speaks_mcp(self, tmp_path):
        """Run the generated server and complete the MCP handshake."""
        out = tmp_path / "server.py"
        call_command("build_mcp", out=str(out),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05",
                            "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        listing = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        proc = subprocess.run(
            [sys.executable, str(out)],
            input="".join(json.dumps(m) + "\n" for m in (hello, initialized, listing)),
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
        assert lines[0]["result"]["serverInfo"]["name"] == "admineverywhere-mcp"
        assert lines[0]["result"]["protocolVersion"] == "2024-11-05"
        tools = lines[1]["result"]["tools"]
        assert {t["name"] for t in tools} >= {"api_overview", "branding_get", "branding_set"}

    def test_rejects_localhost_loudly(self, tmp_path):
        with pytest.raises(CommandError, match="localhost"):
            call_command("build_mcp", out=str(tmp_path / "s.py"),
                         api_host="https://localhost", stdout=io.StringIO())

    def test_server_name_flag_renames(self, tmp_path):
        out = tmp_path / "s.py"
        call_command("build_mcp", out=str(out), server_name="freshorama-mcp",
                     api_host="https://admin.example.com", stdout=io.StringIO())
        assert 'SERVER_NAME = "freshorama-mcp"' in out.read_text()

    def test_generated_server_rejects_unknown_method(self, tmp_path):
        out = tmp_path / "server.py"
        call_command("build_mcp", out=str(out),
                     api_host="https://admin.example.com", stdout=io.StringIO())
        req = {"jsonrpc": "2.0", "id": 9, "method": "resources/list"}
        proc = subprocess.run([sys.executable, str(out)],
                              input=json.dumps(req) + "\n",
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        resp = json.loads(proc.stdout.splitlines()[0])
        assert resp["error"]["code"] == -32601
