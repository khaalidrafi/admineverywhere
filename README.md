# admincraft

A branded, extensible, AI-powered admin app builder for any Django REST
Framework backend — pip-installable plugin (branding + schema tooling) plus a
Tauri 2 / Svelte 5 thin client that renders your entire CRUD UI from your
drf-spectacular OpenAPI schema. Includes an OpenAI-compatible streaming AI
assistant (Ctrl+K) that knows your models. One `brand.json` rebrands the whole
app in under a second. Tauri 2 targets Android .apk, Windows .exe and Linux
.AppImage — prebuilt for every release (see
[Releases](https://github.com/khaalidrafi/admincraft/releases)), or build
locally / from source via Nix/Guix.

**Repo:** `khaalidrafi/admincraft` · stack: Django plugin (pip) +
Tauri 2 + Svelte 5 + Tailwind 4 + DRF/drf-spectacular backend.

## Try it in 3 steps

```bash
# 1. Run the demo backend (Django 5 + DRF + drf-spectacular, seeded)
cd demo-backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt -e ../plugin
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo && .venv/bin/python manage.py runserver
#    (login: admin / admin123 · schema: http://localhost:8000/api/schema/)

# 2. Run the thin client (vite dev; works identically inside Tauri)
cd ../app && npm install && npm run dev            # -> http://localhost:5173

# 3. Rebrand it — edit app/brands/freshorama/brand.json (or use minimal-light), then:
cd ../demo-backend && .venv/bin/python manage.py build_admin --brand ../app/brands/minimal-light/brand.json --app ../app
```

Screenshot flow worth demoing: login → dashboard widgets (record counts,
14-day activity chart, daily quote) → Product table → New Order (FK
dropdowns + enum) → **Ctrl+K** → ask "what models do I have?" and watch it
stream. Then run the rebrand command above and reload — whole app, new
identity, one second.

## Layout

| dir | what |
| --- | --- |
| `plugin/` | pip package `admincraft` — `build_admin` (brand injection), `dump_schema`, branding engine (53 pytest cases) |
| `app/` | Tauri 2 + Svelte 5 thin client — schema-driven CRUD, widgets, AI chat (51 vitest cases) |
| `demo-backend/` | realistic DRF backend exercising every field type (FK, enum, decimal, date, bool) |
| `app/brands/` | two example brands: `freshorama` (dark SaaS) + `minimal-light` (light) |
| `frontend-dist/` | stub for the Nix flake input — the repo ships no prebuilt web assets |
| `docs/` | E2E screenshots |
| `.github/workflows/` | `build-all.yml` — live CI: test gate + six build legs + tag-triggered releases (`build-demo.yml.disabled` — the old parked demo-CI) |
| `AGENTS.md` | repo-specific agent notes — constraints, hard-won contracts, commands, current state |
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
cd app && npm test                    # 51 vitest (schema normalizer, SSE parser)
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 53 pytest
```

## Builds & releases (CI — live)

`.github/workflows/build-all.yml` runs on every push and PR to `ai/main`:
a test gate (51 vitest + 53 pytest) first, then six build legs — web
bundle, Windows NSIS `.exe`, Linux `.AppImage`, Android `.apk` (aarch64,
debug-signed) and the Nix + Guix packages. Every run uploads its
artifacts (14-day retention) so you can grab a client, point it at your
own DRF API on the login screen, and start managing your models —
nothing bundled, nothing calls home.

Push a `v*` tag and the same pipeline also cuts a GitHub Release with all
assets attached. Current set (see
[v0.1.0](https://github.com/khaalidrafi/admincraft/releases/tag/v0.1.0)):

| asset | platform | how to use |
| --- | --- | --- |
| `admincraft-0.1.0-py3-none-any.whl` (+ sdist) | any Python ≥ 3.10 | `pip install` — the Django plugin |
| `admincraft_0.1.0_x64-setup.exe` | Windows | run the NSIS installer |
| `admincraft_0.1.0_amd64.AppImage` | most distros | `chmod +x` and run |
| `admincraft-0.1.0-android-aarch64-debug.apk` | Android (aarch64) | `adb install` — debug-signed for testing |
| `admincraft-0.1.0-web.tar.gz` | any (browser) | serve the contents statically, open, log in |
| `admincraft-0.1.0-nix.tar.gz` / `-guix.tar.gz` | Nix / Guix | verified store-path builds (absolute `/nix/store` / `/gnu/store` paths) |
| `SHA256SUMS.txt` | — | checksums for everything above |

## Nix

Per the nixpkgs manual (Rust chapter) — `buildRustPackage` with
`cargoLock.lockFile`, so dependencies vendor straight from `Cargo.lock`
with no manual hashes. The web bundle is injected via the `frontend-dist`
flake input (the repo ships no prebuilt assets — see `frontend-dist/`):

```bash
nix build --override-input frontend-dist "$(nix store add-path app/dist)" .#admincraft
./result/bin/admincraft
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

The binary lands in `$(guix build -f guix.scm)/bin/admincraft`.

## Notes

- AI chat: streaming, no tool calling / history persistence (v2 material).
- Dev-only values in `demo-backend/` (CORS allow-all, DEBUG) — see
  `AI-REVIEW.org` before reusing anywhere.
- Placeholder icons are generated with `npx tauri icon`; replace for client releases.
- Prebuilt clients ship on the
  [Releases](https://github.com/khaalidrafi/admincraft/releases) page
  (tag-triggered CI). They are demo/test-only builds — nothing bundled,
  nothing calls home.
