"""dump_schema — fetch the backend OpenAPI schema and save it as JSON.

Usage:
    python manage.py dump_schema [--url http://127.0.0.1:8000/api/schema/]
                                 [--out admin-schema.json] [--token SECRET]

Handy for offline inspection and for filing bug reports against schema
changes. The thin client fetches the schema live at runtime; this command
is the developer's debug mirror of the same document.
"""
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

from django.core.management.base import BaseCommand, CommandError

from ai_dashboard import branding  # for branding.urlopen monkeypatching in tests


class Command(BaseCommand):
    help = "Fetch the drf-spectacular OpenAPI schema and save it as JSON"

    def add_arguments(self, parser):
        parser.add_argument("--url", default="http://127.0.0.1:8000/api/schema/",
                            help="OpenAPI schema URL (drf-spectacular)")
        parser.add_argument("--out", default="admin-schema.json", help="Output file")
        parser.add_argument("--token", default=None, help="DRF token for auth'd schemas")

    def handle(self, *args, **options):
        headers = {"Accept": "application/json"}
        if options["token"]:
            headers["Authorization"] = f"Token {options['token']}"
        req = Request(options["url"], headers=headers)
        try:
            with branding.urlopen(req, timeout=15) as resp:  # noqa: SIM117
                data = json.loads(resp.read())
        except (HTTPError, URLError) as exc:
            raise CommandError(f"could not fetch {options['url']}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"response was not JSON (is ?format=json supported?): {exc}") from exc

        out = Path(options["out"])
        out.write_text(json.dumps(data, indent=2) + "\n")
        n_paths = len(data.get("paths", {}))
        self.stdout.write(self.style.SUCCESS(
            f"saved {n_paths} paths from {options['url']} -> {out}"))
