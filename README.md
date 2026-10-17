# admincraft

A branded, extensible, AI-powered admin app builder for any Django REST
Framework backend — pip-installable plugin (branding + schema tooling) plus a
Tauri 2 / Svelte 5 thin client that renders your entire CRUD UI from your
drf-spectacular OpenAPI schema. Includes an OpenAI-compatible streaming AI
assistant (Ctrl+K) that knows your models. One `brand.json` rebrands the whole
app in under a second. Ships as Android .apk, Windows .exe and Linux
.AppImage.

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
| `plugin/` | pip package `admincraft` — `build_admin` (brand injection), `dump_schema`, branding engine (29 pytest cases) |
| `app/` | Tauri 2 + Svelte 5 thin client — schema-driven CRUD, widgets, AI chat (51 vitest cases) |
| `demo-backend/` | realistic DRF backend exercising every field type (FK, enum, decimal, date, bool) |
| `app/brands/` | two example brands: `freshorama` (dark SaaS) + `minimal-light` (light) |
| `frontend-dist/` | stub for the Nix flake input — the repo ships no prebuilt web assets |
| `docs/` | E2E screenshots |
| `.github/workflows/` | `build-demo.yml.disabled` — demo-CI **parked** (credits); re-enable by renaming back to `.yml` |
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
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 29 pytest
```

## Demo builds (CI — currently parked)

CI is **disabled** to save Actions credits on this private repo: the
workflow is parked at `.github/workflows/build-demo.yml.disabled` (Actions
only reads `*.yml` there, so it is inert — no dispatch, no tag triggers).
Its purpose was demo/test-only binaries: launch one, type your DRF API URL
+ credentials on the login screen, and you're managing your models —
nothing is bundled, nothing calls home. Three dispatched runs failed
during bring-up (web/windows/linux jobs green; android/nix/guix
unverified).

To re-enable: `git mv .github/workflows/build-demo.yml.disabled .github/workflows/build-demo.yml`, then run it manually (Actions → *Demo builds* →
Run workflow) or push a `v*` tag. It never triggers on plain pushes (CI
credits — flip the repo public and standard runners are free). Expected
artifacts once green (14-day retention):

| artifact | platform | how to use |
| --- | --- | --- |
| `demo-web-dist` | any (browser) | serve `dist/` statically, open, log in |
| `demo-windows-setup` | Windows | run the NSIS `.exe` installer |
| `demo-linux-appimage` / `demo-linux-deb` | most distros | `chmod +x` & run, or install the deb |
| `demo-android-apk` | Android (aarch64) | `adb install` — debug-signed for testing |
| `demo-nix-out-path` | NixOS / any Linux + Nix | verified `nix build` result |
| `demo-guix-package` | Guix System | verified `guix build` result |

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
- Demo CI is parked (`.github/workflows/build-demo.yml.disabled`) —
  rename back to `.yml` and dispatch (Actions → *Demo builds*) to build
  demo bundles. Artifacts are demo/test-only — no releases.
