"""build_emacs — generate an Org-powered Emacs admin client for this backend.

Usage:
    python manage.py build_emacs --api-host https://admin.example.com
                                 [--out ./admineverywhere-admin.el]
                                 [--schema schema.json]
                                 [--package-name admineverywhere-admin]
                                 [--path-prefix /api/]

--api-host    : deployed API origin baked into the package (https,
                dotted DNS, no localhost/wildcards — see
                admineverywhere.branding.normalize_api_host)
--schema      : read the OpenAPI document from a file instead of
                generating it from this project's URLconf
--package-name: elisp feature/header name of the generated package

The generated single-file package is Org-first (records as headlines
with properties drawers), built for LARGE data (paginated buffers),
with Org TODO write-back and a plain-text AI helper (gptel when
installed, any OpenAI-compatible endpoint otherwise).  Auth comes from
auth-source or the ADMINEVERYWHERE_API_TOKEN env var — never baked.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from admineverywhere import emacs_gen, schema_resources
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
    help = ("Generate an Org-powered Emacs admin client (single .el file) "
            "from the project's OpenAPI schema")

    def add_arguments(self, parser):
        parser.add_argument("--api-host", required=True,
                            help="Deployed API origin, e.g. https://admin.example.com")
        parser.add_argument("--out", default="./admineverywhere-admin.el",
                            help="Output path (default: ./admineverywhere-admin.el)")
        parser.add_argument("--schema", default=None,
                            help="OpenAPI JSON file (default: generate from URLconf)")
        parser.add_argument("--package-name", default="admineverywhere-admin",
                            help="elisp package/feature name (default: admineverywhere-admin)")
        parser.add_argument("--path-prefix", default="/api/",
                            help="API path prefix that scopes admin resources")

    def handle(self, *args, **options):
        # Option dests are underscored by argparse; call_command accepts
        # either form in kwargs but hands handle() the dest names.
        api_host_arg = options["api_host"]
        out_path = Path(options["out"])
        package_name = options["package_name"]
        path_prefix = options["path_prefix"]

        if options["schema"]:
            schema_file = Path(options["schema"])
            if not schema_file.is_file():
                raise CommandError(f"schema file not found: {schema_file}")
            import json
            schema = json.loads(schema_file.read_text())
        else:
            schema = _generate_schema()

        # Same https-only host rule the thin client's CSP and build_mcp
        # use: admin tooling must not be droppable at localhost origins.
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

        out_path.write_text(emacs_gen.render_elisp(
            resources, api_host, package_name, _plugin_version()))
        self.stdout.write(self.style.SUCCESS(
            f"Emacs package written: {out_path} "
            f"({len(resources)} resources, feature '{package_name}') -> {api_host}"))
        self.stdout.write(
            f"  load it, then M-x aw-open / aw-todos / aw-ask")
