"""build_cli — generate a standalone terminal admin CLI for this backend.

Usage:
    python manage.py build_cli --api-host https://admin.example.com
                               [--out ./admin_cli.py]
                               [--schema schema.json]
                               [--cli-name admineverywhere-cli]
                               [--token-env ADMINEVERYWHERE_API_TOKEN]
                               [--path-prefix /api/]

--api-host  : deployed API origin baked into the CLI (https, dotted DNS,
              no localhost/wildcards — see
              admineverywhere.branding.normalize_api_host)
--schema    : read the OpenAPI document from a file instead of generating
              it from this project's URLconf (needs drf-spectacular)
--path-prefix: only paths under this prefix become commands
--cli-name  : program name (also the config dir under ~/.config)

The generated CLI is stdlib-only Python; every command (resources,
custom actions, sign-in path) is derived from the OpenAPI schema at
build time, so the CLI can never drift from the API. The order machine
is never re-encoded: transition steps stay in the API.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from admineverywhere import cli_gen, schema_resources
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


def _auth_path(paths: dict, prefix: str) -> str:
    """Pick the sign-in path from the schema; fall back to the
    conventional DRF token path so generation stays deterministic."""
    for path in sorted(paths or {}):
        if path.startswith(prefix) and path.rstrip("/").endswith("auth/token"):
            return path
    return "/api/auth/token/"


class Command(BaseCommand):
    help = ("Generate a standalone terminal admin CLI from the project's "
            "OpenAPI schema — plain store commands, never drifts from "
            "the API")

    def add_arguments(self, parser):
        parser.add_argument("--api-host", required=True,
                            help="Deployed API origin, e.g. https://admin.example.com")
        parser.add_argument("--out", default="./admin_cli.py",
                            help="Output path for the generated CLI (default: ./admin_cli.py)")
        parser.add_argument("--schema", default=None,
                            help="OpenAPI JSON file (default: generate from URLconf)")
        parser.add_argument("--cli-name", default="admineverywhere-cli",
                            help="Program name and config dir (default: admineverywhere-cli)")
        parser.add_argument("--token-env", default="ADMINEVERYWHERE_API_TOKEN",
                            help="Env var the generated CLI also reads the token from")
        parser.add_argument("--path-prefix", default="/api/",
                            help="API path prefix that scopes commands")

    def handle(self, *args, **options):
        api_host_arg = options["api_host"]
        out_path = Path(options["out"])
        cli_name = options["cli_name"]
        token_env = options["token_env"]
        path_prefix = options["path_prefix"]
        if options["schema"]:
            schema_file = Path(options["schema"])
            if not schema_file.is_file():
                raise CommandError(f"schema file not found: {schema_file}")
            schema = json.loads(schema_file.read_text())
        else:
            schema = _generate_schema()

        # Same https-only host rule the thin client's CSP uses: the CLI
        # must not be droppable at localhost or wildcard origins.
        try:
            api_host = normalize_api_host(api_host_arg)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        paths = schema.get("paths", {})
        resources = schema_resources.derive_resources(paths, prefix=path_prefix)
        if not resources:
            raise CommandError(
                f"no resources found under {path_prefix} — check "
                "--path-prefix or the schema")
        actions = cli_gen.derive_actions(
            paths, prefix=path_prefix, reserved={
                p for r in resources for p in (r["list_path"], r["detail_path"])
                if p})

        out_path.write_text(cli_gen.render_cli(
            resources, actions, api_host, cli_name, token_env,
            _auth_path(paths, path_prefix), _plugin_version()))
        self.stdout.write(self.style.SUCCESS(
            f"CLI written: {out_path} ({len(resources)} resources, "
            f"{len(actions)} actions) -> {api_host}"))
        self.stdout.write(f"  run: python3 {out_path} --help")
