"""build_admin — rebrand the thin-client app from one brand.json.

Usage:
    python manage.py build_admin --brand brands/fresh.json [--app ./app] [--build]
                                  [--api-host https://admin.example.com]

--app       : thin-client directory (default: ./app)
--build     : additionally run `npm run build` inside the app dir
--api-host  : deployed API origin substituted for the CSP's API_HOST
              placeholder (validated: https, dotted DNS, no localhost, no
              wildcards — see admincraft.branding.normalize_api_host)
"""
from django.core.management.base import BaseCommand, CommandError

from admincraft import branding


class Command(BaseCommand):
    help = ("Inject a brand.json into the thin-client app "
            "(CSS vars, assets, window title, CSP API_HOST substitution)")

    def add_arguments(self, parser):
        parser.add_argument("--brand", required=True, help="Path to brand.json")
        parser.add_argument("--app", default="app", help="Thin-client app directory (default: ./app)")
        parser.add_argument("--build", action="store_true",
                            help="Also run `npm run build` inside the app directory")
        parser.add_argument("--api-host", default=None,
                            help="Deployed API origin substituted for the CSP's "
                                 "https://API_HOST placeholder (e.g. https://admin.example.com). "
                                 "localhost/wildcards are rejected.")

    def handle(self, *args, **options):
        from pathlib import Path
        app_dir = Path(options["app"])
        if not app_dir.is_dir():
            raise CommandError(f"app directory not found: {app_dir}")

        try:
            summary = branding.inject_brand(app_dir, options["brand"],
                                            api_host=options.get("api_host"))
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        app_name = branding.load_brand(options["brand"])["appName"]
        self.stdout.write(self.style.SUCCESS(
            f"Branded app as '{app_name}' from {options['brand']} -> {app_dir}"))
        for group in ("written", "copied", "patched"):
            for f in summary.get(group, []):
                self.stdout.write(f"  {group[:-1]}: {f}")
        if summary.get("csp_api_host"):
            self.stdout.write(self.style.SUCCESS(
                f"  csp connect-src -> {summary['csp_api_host']}"))

        if options["build"]:
            import subprocess
            self.stdout.write("running npm run build ...")
            proc = subprocess.run(["npm", "run", "build"], cwd=app_dir)
            if proc.returncode != 0:
                raise CommandError("npm run build failed")

        self.stdout.write("Next: cd app && npm run tauri build (or: dev)")
