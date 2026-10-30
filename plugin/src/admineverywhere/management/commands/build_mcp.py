"""build_mcp — generate a standalone MCP server for this backend.

Usage:
    python manage.py build_mcp --api-host https://admin.example.com
                               [--out ./mcp_admin_server.py]
                               [--schema schema.json]
                               [--server-name admineverywhere-mcp]
                               [--token-env ADMINEVERYWHERE_API_TOKEN]
                               [--path-prefix /api/]

--api-host  : deployed API origin baked into the server (https, dotted
              DNS, no localhost/wildcards — see
              admineverywhere.branding.normalize_api_host)
--schema    : read the OpenAPI document from a file instead of generating
              it from this project's URLconf (needs drf-spectacular)
--path-prefix: only paths under this prefix become admin resources

The generated server speaks the MCP stdio protocol (newline-delimited
JSON-RPC 2.0) and exposes one CRUD tool-set per API model resource plus
the runtime branding API, so MCP-capable agents can run admin tasks —
the agent connects, an operator approves the tool set, and every call
hits the real DRF API with a token from the environment.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from admineverywhere import mcp_gen, schema_resources
from admineverywhere.branding import normalize_api_host


def _plugin_version() -> str:
    try:
        from importlib.metadata import version
        return version("admineverywhere")
    except Exception:                                    # pragma: no cover
        return "dev"


def _generate_schema() -> dict:
    """Generate the OpenAPI document from this project's URLconf."""
    try:
        from drf_spectacular.generators import SchemaGenerator
    except ImportError as exc:
        raise CommandError(
            "drf-spectacular is required to generate the schema; "
            "pass --schema <file> to use a saved document instead") from exc
    return SchemaGenerator().get_schema(public=True)


class Command(BaseCommand):
    help = ("Generate a standalone MCP admin server (stdio) from the "
            "project's OpenAPI schema — agents control admin tasks via MCP")

    def add_arguments(self, parser):
        parser.add_argument("--api-host", required=True,
                            help="Deployed API origin, e.g. https://admin.example.com")
        parser.add_argument("--out", default="./mcp_admin_server.py",
                            help="Output path for the generated server (default: ./mcp_admin_server.py)")
        parser.add_argument("--schema", default=None,
                            help="OpenAPI JSON file (default: generate from URLconf)")
        parser.add_argument("--server-name", default="admineverywhere-mcp",
                            help="serverInfo name advertised over MCP")
        parser.add_argument("--token-env", default="ADMINEVERYWHERE_API_TOKEN",
                            help="Env var the generated server reads the API token from")
        parser.add_argument("--path-prefix", default="/api/",
                            help="API path prefix that scopes admin resources")

    def handle(self, *args, **options):
        # Option dests are underscored by argparse; call_command accepts
        # either form in kwargs but hands handle() the dest names.
        api_host_arg = options["api_host"]
        out_path = Path(options["out"])
        server_name = options["server_name"]
        token_env = options["token_env"]
        path_prefix = options["path_prefix"]
        if options["schema"]:
            schema_file = Path(options["schema"])
            if not schema_file.is_file():
                raise CommandError(f"schema file not found: {schema_file}")
            import json
            schema = json.loads(schema_file.read_text())
        else:
            schema = _generate_schema()

        # Same https-only host rule the thin client's CSP uses: the MCP
        # server must not be droppable at localhost or wildcard origins.
        try:
            api_host = normalize_api_host(api_host_arg)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        resources = schema_resources.derive_resources(
            schema.get("paths", {}), prefix=path_prefix)
        if not resources:
            raise CommandError(
                f"no resources found under {path_prefix} — check "
                "--path-prefix or the schema")
        tools = schema_resources.build_tools(resources)

        out_path.write_text(mcp_gen.render_server(
            tools, resources, api_host, server_name,
            token_env, _plugin_version()))
        self.stdout.write(self.style.SUCCESS(
            f"MCP server written: {out_path} "
            f"({len(resources)} resources, {len(tools)} tools) -> {api_host}"))
        self.stdout.write(
            f"  run: {token_env}=<token> python3 {out_path}")
