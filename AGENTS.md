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

## Product spec (from MVP brief)

Acceptance criteria the brief pins down beyond the constraints above.

- **AI chat panel** — one floating panel, opened by Ctrl+K or a button.
  Settings are *exactly* three inputs — base URL, API key, model name —
  under the hint "Works with OpenAI, Groq, Ollama & more". Streaming is
  non-negotiable; the system prompt embeds a schema summary so answers
  track the live API, and the key lives in the Tauri keyring. The panel
  stays fully functional when unconfigured: a friendly setup prompt, not
  an error. The v2 exclusions above (no tool calling / history / provider
  abstraction) still apply.
- **CRUD spec** — `RecordForm` renders text, number, bool, date,
  enum-select and FK-dropdown fields; schema-driven, graceful when the
  schema omits constraints. `DataTable` = pagination + search + delete.
  Login is token auth against `config.apiUrl` with a settings field.
- **Scope rationale & demo flow** — the out-of-scope line above plus
  multi-provider abstraction, tool calling and history are all *v2*; the
  nav is built so ⌘K drops in later. Definition of done (demo flow):
  login `admin` / `admin123` → dashboard widgets → Product table → New
  Order → Ctrl+K streams (via `scripts/mock_openai.js` on `:11435`) →
  rebrand with `build_admin`.

## Layout

| path | role |
| --- | --- |
| `plugin/` | pip package `admincraft` — `branding.py`, `build_admin`, `dump_schema` (53 pytest, written first) |
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
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 53 pytest

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
- Demo-rig token route is `POST /api/auth/token/` (`core/urls.py:10`), **not**
  Django's default `/api-token-auth/` — that 404s here. `plugin/tests/test_demo_boot.py`
  boots the real `core.settings` in a subprocess, runs Django's system checks and
  resolves that path plus the `include("shop.urls")` routes, so a deleted or
  broken URLConf fails the suite instead of surfacing on the first live request.
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

## State as of 2026-10-17

- Shipped on `ai/main` (default branch): plugin, thin client, demo
  backend, Nix + Guix packaging, README, AI-REVIEW. `ai/mvp-build`
  (demo-CI fixes + pinned Cargo.lock) is merged in and can be pruned.
- Fixed & merged on `ai/main` (P0→P1; `pytest` 48/48): `brand.json` closed
  schema + realpath/commonpath jail on all writes; demo-backend dev-only
  DEBUG/CORS startup warning (`DEMO_DEV=1` ack); `api.ts` secret redaction +
  credentials stripped from URLs; `chat.ts` SSE oversized-line cap (1 MB,
  skip+warn); `secrets.ts` one-time web-localStorage SECURITY warning;
  `tauri.conf.json` CSP `null` → working dev policy (localhost/ws + inline
  styles, no wildcards); `RecordForm.buildPayload` omits empty non-nullable
  fields; `DataTable` nested `{#each}` keyed on `col.name`; widgets
  auto-imported via `import.meta.glob` (`meta{title,size}`).
- Open, by priority: AI-REVIEW.org human P0 sign-off; web-mode secrets still
  in localStorage (accepted P2 — now warned, not eliminated); placeholder
  icons; demo-CI android/nix/guix jobs never went green.
