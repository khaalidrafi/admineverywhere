# admineverywhere

A branded, extensible, AI-powered admin app builder for any Django REST
Framework backend — pip-installable plugin (branding + schema tooling + a
runtime branding API) plus a Tauri 2 / Svelte 5 thin client that renders
your entire CRUD UI from your drf-spectacular OpenAPI schema. Includes an
OpenAI-compatible streaming AI assistant (Ctrl+K) that knows your models.
**Brand it however you like:** one `brand.json` rebrands the whole app in
under a second, and once your backend runs the plugin you can rebrand from
*inside the app* (Settings → Branding: name, colors, font, logo — applied
live, no rebuild). Release builds ship a neutral default identity
("Admineverywhere") that every user replaces with their own. Tauri 2 targets
Android .apk, Windows .exe and Linux .AppImage — prebuilt for every
release (see
[Releases](https://github.com/khaalidrafi/admineverywhere/releases)), or build
locally / from source via Nix/Guix. Two agent skills
([`skills/`](skills/)) can onboard an existing repo onto admineverywhere and
craft the branding for you — guided, or fully automatic from your
project's own source.

**Repo:** `khaalidrafi/admineverywhere` · stack: Django plugin (pip) +
Tauri 2 + Svelte 5 + Tailwind 4 + DRF/drf-spectacular backend.

## Try it in 3 steps

```bash
# 1. Run the demo backend (Django 5 + DRF + drf-spectacular, seeded)
cd demo-backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt -e ../plugin
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo && .venv/bin/python manage.py runserver
#    (login: admin / admin123 · schema: http://localhost:8000/api/schema/)
#    (role demo: auditor / audit123 — non-superuser holding only the
#     `auditors` group, so the managers-only actions are visibly hidden —
#     and manager / manager123, non-superuser holding only `managers`, so
#     the same gate visibly opens on a real claim rather than on the
#     superuser bypass)

# 2. Run the thin client (vite dev; works identically inside Tauri)
cd ../app && npm install && npm run dev            # -> http://localhost:5173

# 3. Rebrand it — two ways:
#    a) from inside the app: login, Settings → Branding (saved to the backend,
#       applied live — name, colors, font, logo)
#    b) build-time: apply a brand.json to the shipped bundle + launcher identity
cd ../demo-backend && .venv/bin/python manage.py build_admin --brand ../app/brands/minimal-light/brand.json --app ../app
#    For a deploy build, also pass --api-host https://your-admin.example.com —
#    it substitutes the production CSP's https://API_HOST placeholder with
#    the real origin (https only; localhost/wildcards are rejected).

# 4. Or let the agent skills do all of it (guided OR fully automatic):
python ../skills/admineverywhere-build/scripts/derive_brand.py --root <your-repo> --out <your-repo>/brand
```

## Build what you need (choose your targets)

`build_admin --targets` is the build menu — pick exactly what you want:
`web` (browser bundle), `desktop` (Windows `.exe` / Linux `.AppImage`),
`android` (universal `.apk`), `mcp` (standalone MCP admin server), and
`emacs` (Org-powered Emacs package).

```bash
# Freshorama example: brand the client, then build the web bundle AND the
# agent tooling from the same OpenAPI schema.
cd demo-backend
.venv/bin/python manage.py build_admin --brand ../app/brands/freshorama/brand.json \
    --app ../app --targets web,mcp,emacs --api-host https://admin.example.com

# MCP: register the generated server with your agent client
#   command: python3  args: ["./mcp_admin_server.py"]
#   env:     ADMINEVERYWHERE_API_TOKEN=<token>
# Emacs: load the generated package, then M-x aw-open / aw-todos / aw-ask
#   (records as Org headlines, TODO states write back to the API, and the
#    current Org subtree becomes the AI context — see the file header).
```

Prebuilt desktop/mobile/web bundles ship on the
[Releases](https://github.com/khaalidrafi/admineverywhere/releases) page;
`mcp`/`emacs` artifacts are generated locally because they bake YOUR API
host and resource roster into the file.

Screenshot flow worth demoing: login → dashboard widgets (record counts,
14-day activity chart, daily quote) → Product table → New Order (FK
dropdowns + enum) → **Ctrl+K** → ask "what models do I have?" and watch it
stream. Then open Settings → Branding, change the name and colors and hit
Save — whole app, new identity, one second, no rebuild.

## Layout

| dir | what |
| --- | --- |
| `plugin/` | pip package `admineverywhere` — `build_admin` (brand injection + CSP API_HOST substitution + `--targets` build menu), `build_mcp` (standalone MCP admin server), `build_emacs` (Org-powered Emacs package), `dump_schema`, branding engine + runtime branding API |
| `app/` | Tauri 2 + Svelte 5 thin client — schema-driven CRUD, widgets, AI chat, in-app brand editor (58 vitest cases) |
| `demo-backend/` | realistic DRF backend exercising every field type (FK, enum, decimal, date, bool) |
| `app/brands/` | `default/` (the neutral shipped identity) + two examples: `freshorama` (dark SaaS) + `minimal-light` (light) |
| `skills/` | agent skills: `admineverywhere-onboard` (wire an existing repo onto admineverywhere) + `admineverywhere-build` (guided or source-derived branding; ask/auto modes) |
| `frontend-dist/` | stub for the Nix flake input — the repo ships no prebuilt web assets |
| `docs/` | E2E screenshots |
| `.github/workflows/` | `build-all.yml` — live CI: test gate + six build legs + tag-triggered releases (`build-demo.yml.disabled` — the old parked demo-CI) |
| `docs/DEVGUIDE.md` | repo dev guide (moved from AGENTS.md 2026-10-21 — a repo-root AGENTS.md is never created): constraints, hard-won contracts, commands |
| `flake.nix` | Nix package — `rustPlatform.buildRustPackage` + `cargoLock` (nixpkgs manual recipe) |
| `guix.scm` | Guix package — `gnu-build-system`, vendored Cargo, offline `--frozen` (Guix manual recipe) |

## Extending

- **New dashboard widget** = drop one `.svelte` file in `app/src/widgets/`
  with `<script module>export const meta = { title, size: 'sm'|'lg' }</script>`.
  No registration, no config.
- **New backend**: point `app/public/config.json` (or the API URL field on
  the login screen) at any DRF + drf-spectacular server using token auth.
- **AI provider**: any OpenAI-compatible endpoint (OpenAI, Groq, Ollama, LM
  Studio…) — set Base URL / key / model in the chat panel settings. The key
  goes to the OS keychain in the packaged app.

## Tests

```bash
cd app && npm test                    # 58 vitest (schema normalizer, SSE parser, branding)
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 114 pytest
```

## Builds & releases (CI — live)

`.github/workflows/build-all.yml` runs on every push and PR to `ai/main`:
a test gate (58 vitest + 114 pytest) first, then six build legs — web
bundle, Windows NSIS `.exe`, Linux `.AppImage`, Android `.apk` (universal:
`arm64-v8a` + `armeabi-v7a`, Android 7.0+, signed with the committed stable
debug key) and the Nix + Guix packages. Every run uploads its
artifacts (14-day retention) so you can grab a client, point it at your
own DRF API on the login screen, and start managing your models —
nothing bundled, nothing calls home.

Push a `v*` tag and the same pipeline also cuts a GitHub Release with all
assets attached. Current set (see
[v0.1.2](https://github.com/khaalidrafi/admineverywhere/releases/tag/v0.1.2) —
the first release carrying the neutral "Admineverywhere" identity):

| asset | platform | how to use |
| --- | --- | --- |
| `admineverywhere-0.1.2-py3-none-any.whl` (+ sdist) | any Python ≥ 3.10 | `pip install` — the Django plugin |
| `admineverywhere_0.1.2_x64-setup.exe` | Windows | run the NSIS installer |
| `admineverywhere_0.1.2_amd64.AppImage` | most distros | `chmod +x` and run |
| `admineverywhere-0.1.2-android-universal-debug.apk` | Android 7.0+ (64- & 32-bit) | enable *install unknown apps*, then sideload; stable debug-signed. Installing over v0.1.1 works (same key); devices still on the v0.1.0 apk must uninstall once (one-time key change) |
| `admineverywhere-0.1.2-web.tar.gz` | any (browser) | serve the contents statically, open, log in |
| `admineverywhere-0.1.2-nix.tar.gz` / `-guix.tar.gz` | Nix / Guix | verified store-path builds (absolute `/nix/store` / `/gnu/store` paths) |
| `SHA256SUMS.txt` | — | checksums for everything above |

## Nix

Per the nixpkgs manual (Rust chapter) — `buildRustPackage` with
`cargoLock.lockFile`, so dependencies vendor straight from `Cargo.lock`
with no manual hashes. The web bundle is injected via the `frontend-dist`
flake input (the repo ships no prebuilt assets — see `frontend-dist/`):

```bash
nix build --override-input frontend-dist "$(nix store add-path app/dist)" .#admineverywhere
./result/bin/admineverywhere
```

(Build the web bundle first: `cd app && npm ci && npm run build`.)
`nix develop` drops you in a shell with node, cargo, and webkitgtk.

## Guix

Per the Guix manual (Defining Packages) — a package record on
`gnu-build-system`. Tauri's ~600-crate tree doesn't fit
`cargo-build-system`'s per-crate inputs, so crates are vendored ahead of
the build and compiled offline:

```bash
(cd app && npm ci && npm run build)
(cd app/src-tauri && mkdir -p .cargo && cargo vendor vendor > .cargo/config.toml)
guix build -f guix.scm
```

The binary lands in `$(guix build -f guix.scm)/bin/admineverywhere`.

## Notes

- AI chat: streaming, no tool calling / history persistence (v2 material).
- Dev-only values in `demo-backend/` (CORS allow-all, DEBUG) — see
  `AI-REVIEW.org` before reusing anywhere.
- Launcher icons: generated neutral grid marks (regenerate per client with
  `npx tauri icon <1024px png>`); the in-app logo/favicon are runtime-
  brandable without a rebuild.
- Prebuilt clients ship on the
  [Releases](https://github.com/khaalidrafi/admineverywhere/releases) page
  (tag-triggered CI). They carry the neutral identity — nothing bundled,
  nothing calls home; users register their own API and brand.
