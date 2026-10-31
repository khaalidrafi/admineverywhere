"""build_admin — rebrand the thin-client app from one brand.json.

Usage:
    python manage.py build_admin --brand brands/fresh.json [--app ./app]
                                  [--targets web,desktop,android,mcp,emacs]
                                  [--build] [--api-host https://admin.example.com]

--app       : thin-client directory (default: ./app)
--targets   : what to build, comma-separated.  The user chooses:
                web     - the browser bundle (npm run build -> app/dist)
                desktop - Windows .exe / Linux .AppImage (npm run tauri build)
                android - universal .apk (npm run tauri android build)
                mcp     - standalone MCP admin server (agents run admin
                          tasks against the API; see build_mcp)
                emacs   - Org-powered Emacs admin package (see build_emacs)
              mcp/emacs need --api-host.  The generated files are named
              from the brand slug (appName "Freshorama Admin" ->
              "freshorama-admin"): the mcp server lands at
              ./<slug>-mcp-server.py, the emacs package at
              ./<slug>-admin.el (cwd).
--build     : legacy shorthand for --targets web, kept unchanged
--api-host  : deployed API origin substituted for the CSP's API_HOST
              placeholder (validated: https, dotted DNS, no localhost, no
              wildcards — see admineverywhere.branding.normalize_api_host)
"""
from django.core.management.base import BaseCommand, CommandError

from admineverywhere import branding

# The build menu. desktop/android shells out to tauri (their release
# bundles are the .exe/.AppImage/.apk assets); mcp/emacs generate agent
# and Org tooling from the same OpenAPI schema the thin client uses.
VALID_TARGETS = ("web", "desktop", "android", "mcp", "emacs")


def parse_targets(targets, build):
    """Resolve --targets/--build into a target list (pure, for tests)."""
    if targets is not None:
        picked = [t.strip() for t in targets.split(",") if t.strip()]
        bad = [t for t in picked if t not in VALID_TARGETS]
        if bad:
            raise ValueError(
                "unknown targets: %s (valid: %s)" % (
                    ", ".join(bad), ", ".join(VALID_TARGETS)))
        return picked
    return ["web"] if build else []


class Command(BaseCommand):
    help = ("Inject a brand.json into the thin-client app "
            "(CSS vars, assets, window title, CSP API_HOST substitution) "
            "and optionally build any of the release/generator targets")

    def add_arguments(self, parser):
        parser.add_argument("--brand", required=True, help="Path to brand.json")
        parser.add_argument("--app", default="app", help="Thin-client app directory (default: ./app)")
        parser.add_argument("--targets", default=None,
                            help="Comma-separated build menu: %s "
                                 "(default: nothing but the rebrand)" % ", ".join(VALID_TARGETS))
        parser.add_argument("--build", action="store_true",
                            help="Legacy shorthand for --targets web")
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
        for group in ("written", "copied", "patched", "skipped"):
            for f in summary.get(group, []):
                self.stdout.write(f"  {group}: {f}")
        if summary.get("csp_api_host"):
            self.stdout.write(self.style.SUCCESS(
                f"  csp connect-src -> {summary['csp_api_host']}"))

        try:
            targets = parse_targets(options["targets"], options["build"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        for target in targets:
            if target == "web":
                self._npm(app_dir, ["run", "build"])
            elif target == "desktop":
                self._npm(app_dir, ["run", "tauri", "build"])
            elif target == "android":
                self._npm(app_dir, ["run", "tauri", "android", "build"])
            elif target in ("mcp", "emacs"):
                self._generate(options, target, app_name)

        if targets:
            self.stdout.write(f"Targets built: {', '.join(targets)}")

    def _npm(self, app_dir, args):
        import subprocess
        cmd = ["npm", *args]
        self.stdout.write(f"running {' '.join(cmd)} ...")
        proc = subprocess.run(cmd, cwd=app_dir)
        if proc.returncode != 0:
            raise CommandError(f"{' '.join(cmd)} failed")

    def _generate(self, options, target, app_name):
        """Run build_mcp / build_emacs with the shared --api-host.

        The output filename carries the brand slug (appName "Freshorama
        Admin" -> "freshorama-admin-mcp-server.py"), so a host running
        several branded builds never mixes its generated admin tooling.
        """
        from django.core.management import call_command
        api_host = options.get("api_host")
        if not api_host:
            raise CommandError(f"--targets {target} requires --api-host")
        slug = branding.brand_slug(app_name)
        kw = dict(api_host=api_host, stdout=self.stdout)
        if target == "mcp":
            call_command("build_mcp", out=f"{slug}-mcp-server.py", **kw)
        else:
            call_command("build_emacs", out=f"{slug}-admin.el", **kw)
