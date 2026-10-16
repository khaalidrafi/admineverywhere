# AGENTS.md — admincraft

Repo-specific notes for AI agents working in this repository. Global agent
instructions (authorship, commit hygiene, review-first workflow, reply
style) apply as-is and are deliberately not repeated here.

## What this repo is

A branded, AI-assisted admin app builder for an **existing** Django REST
Framework backend. No Django runs locally in the shipped product: `plugin/`
is a pip package (branding engine + schema tooling) installed in the
*server* project, and `app/` is a Tauri 2 / Svelte 5 / Tailwind 4 thin
client that talks to any DRF + drf-spectacular API with token auth. The
whole CRUD UI, dashboard widgets and the Ctrl+K streaming chat are derived
from the OpenAPI schema. `demo-backend/` is a throwaway rig: fixture source
for tests plus a live backend for browser E2E (login `admin` / `admin123`).

Product constraints — do not relax:

- AI chat is OpenAI-compatible only (OpenAI / Groq / Ollama / LM Studio /
  Mistral — one code path). No Anthropic. No tool calling, no provider
  abstraction, no history persistence (all v2 material).
- All visual identity comes from a single `brand.json` (colors, radius,
  font, logo). Components carry zero hard-coded colors: Tailwind 4
  `@theme inline` maps `--color-*` utilities onto the runtime `--brand-*`
  variables written by `build_admin`.
- New dashboard widget = drop one `.svelte` file in `app/src/widgets/`
  exporting `const meta = { title, size }` — auto-discovered via
  `import.meta.glob`. No registry to edit.
- Deliberately out of scope: virtual scrolling, command palette, alerts.

## Layout

| path | role |
| --- | --- |
| `plugin/` | pip package `admincraft` — `branding.py`, `build_admin`, `dump_schema` (29 pytest, written first) |
| `app/` | thin client — Vite 6 + Svelte 5 + Tailwind 4 + Tauri 2 (27 vitest) |
| `app/src/widgets/` | drop-in widgets: StatsCards, ActivityChart (SVG), QuoteCard (30 curated Qur'an/Sunnah/Aslaf quotes; weakly-sourced ones marked "attributed") |
| `app/brands/` | two example brands: `freshorama` (dark SaaS), `minimal-light` |
| `app/src-tauri/` | Rust side, keyring-backed secret storage, generated placeholder icons |
| `demo-backend/` | DRF + drf-spectacular rig exercising every field type (FK, enum, decimal, date, bool, readonly datetime) |
| `flake.nix`, `guix.scm`, `frontend-dist/` | Nix + Guix packaging — rationale in the file headers |
| `.github/workflows/build-demo.yml.disabled` | demo-CI, parked (see *CI* below) |
| `AI-REVIEW.org` | human review queue (P0 security first) + the Svelte debugging war story — read it before touching reactivity |
| `docs/` | E2E screenshots |

## Commands

```bash
# demo backend (schema: http://localhost:8000/api/schema/)
cd demo-backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt -e ../plugin
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo
.venv/bin/python manage.py runserver

# thin client — browser mode is feature-identical to Tauri mode
cd app && npm install && npm run dev        # http://localhost:5173

# tests
cd app && npm test                          # 27 vitest
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 29 pytest

# mock OpenAI-compatible SSE provider (for chat E2E)
node scripts/mock_openai.js                 # listens on :11435

# rebrand the whole client in one command
cd demo-backend && .venv/bin/python manage.py build_admin --brand ../app/brands/minimal-light/brand.json --app ../app
```

## Hard-won contracts (don't relearn these)

- The schema normalizer (`app/src/lib/openapi.ts`) is built against the
  real fixture `app/src/lib/__tests__/fixtures/openapi.json` (captured from
  the demo backend's `/api/schema/`), never against guessed shapes:
  - FKs arrive as bare `type: integer` — detected by name-matching against
    model ids/singulars.
  - Decimals arrive as `type: string, format: decimal` — coerced to number.
  - Enum choices are hoisted to `$ref` components;
    `COMPONENT_SPLIT_REQUEST` yields `<Model>Request` schemas for forms.
- Dual web/Tauri mode: feature-detect `window.__TAURI_INTERNALS__`. Web
  mode falls back to localStorage for token + AI key (accepted P2 — see
  AI-REVIEW.org).
- Cross-module state uses `svelte/store` writables, not exported runes from
  `.svelte.ts` modules (compiler limitation hit during E2E).
- `DataTable`: never reuse an outer keyed-each key variable in a nested
  each — the `each_key_duplicate` throw aborts the whole render queue
  silently and looks like dead reactivity.
- `RecordForm.buildPayload` omits empty non-nullable fields; sending `null`
  there earns a DRF 400.
- Widgets render from a schema-reactive `$effect`, not `onMount` (the
  schema arrives after mount).
- Vite: `optimizeDeps.include` covers all svelte entrypoints (prevents two
  svelte-internals instances); the dev server sends
  `Cache-Control: no-store`.

## CI — parked

`build-demo.yml` is renamed to `build-demo.yml.disabled` (Actions only
reads `*.yml`/`*.yaml` in that directory, so the file is fully inert) to
stop burning credits on this private repo — three dispatched runs failed
during bring-up (web/windows/linux jobs were green; android/nix/guix were
never verified). The artifacts were demo/test-only: binaries a user
launches, registers their own DRF API URL + credentials against on the
login screen, and plays. No releases, nothing bundled, nothing calls home.

To re-enable: `git mv .github/workflows/build-demo.yml.disabled
.github/workflows/build-demo.yml`, then dispatch (Actions → *Demo builds* →
Run workflow) or push a `v*` tag. Never add plain-push triggers; put
`[skip ci]` on pushes that don't need artifacts. `app/src-tauri/Cargo.lock`
is committed — regenerate it whenever `Cargo.toml` changes (the nix
`cargoLock` and guix vendor builds depend on it).

## State as of 2026-10

- Shipped on `ai/main` (default branch): plugin, thin client, demo
  backend, Nix + Guix packaging, README, AI-REVIEW. `ai/mvp-build`
  (demo-CI fixes + pinned Cargo.lock) is merged in and can be pruned.
- Open, roughly by priority: AI-REVIEW.org P0 security review; CSP is
  `null` in `tauri.conf.json`; placeholder icons; demo-CI
  android/nix/guix jobs never went green; web-mode secrets in
  localStorage; `plugin/src/admincraft.egg-info/` is tracked
  build output that should be untracked and ignored.
