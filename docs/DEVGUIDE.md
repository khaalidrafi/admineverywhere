# admincraft dev guide

(Moved from the repo-root AGENTS.md on 2026-10-21 per Owner order —
a project-specific AGENTS.md must not be made. Content unchanged.)

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
for tests plus a live backend for browser E2E (login `admin` / `admin123`,
or `auditor` / `audit123` to see FR-R007 role gating actually hide something).

Product constraints — do not relax:

- AI chat is OpenAI-compatible only (OpenAI / Groq / Ollama / LM Studio /
  Mistral — one code path). No Anthropic. No tool calling, no provider
  abstraction, no history persistence (all v2 material).
- All visual identity comes from a single `brand.json` (colors, radius,
  font, logo). Components carry zero hard-coded colors: Tailwind 4
  `@theme inline` maps `--color-*` utilities onto the runtime `--brand-*`
  variables. **Release builds never carry a product name**: the shipped
  default brand is neutral (`app/brands/default/` = "Admincraft"), and
  every user's identity rides on top — either baked in via `build_admin`
  (launcher + bundled assets) or live via the runtime branding API
  (everything in-app: name, colors, font, logos, titles).
- Branding has TWO layers, never blur them: **runtime** (in-app editor
  `#/branding`, `GET/PUT /admincraft/branding/` — applies instantly, no
  rebuild) vs **build-time** (`tauri.conf.json` productName + platform
  icons — set by `build_admin` / `npx tauri icon` before packaging). The
  Android launcher label is build-time; the desktop window title is
  runtime (Tauri setTitle follows the live brand).
- New dashboard widget = drop one `.svelte` file in `app/src/widgets/`
  exporting `const meta = { title, size, data? }` — auto-discovered via
  `import.meta.glob`. No registry to edit. The optional FR-R008 `data` block
  (`{endpoint, field, aggregate, pollInterval, days, rowCap}`) is a
  schema-resolved feed contract, not a URL: `endpoint` is a model id looked
  up in `schema.byId` and fetched through its discovered `listPath` — never
  concatenated onto `apiUrl`; an unresolvable source renders a friendly
  empty with a nameable reason; `pollInterval` is floor-clamped to 5s and
  the `$effect` cleanup kills the timer. Contract + checklist:
  `docs/widget-data.md`.
- RBAC (FR-R007) is claims-driven and degrades silently: `normalizeOpenAPI`
  binds `schema.mePath` ONLY when the document carries `GET …/me/` and no
  POST (exportPath law again — never a guessed `/api/me/`), the client
  fetches claims with the schema and a failed/absent read leaves
  `claims = null` = NO filtering anywhere (plain DRF keeps the full menu).
  Optional `roles: [str]` on page meta and action meta gates the sidebar
  entry / buttons via `roleAllows()` (`app/src/lib/rbac.ts`, pure); a bad
  roles declaration is refused like any other page problem. Hiding is UX,
  never security — the server re-validates everything, and the demo
  `/api/me/` (`core/views.py`) emits Django Group names as roles. Because a
  superuser short-circuits `roleAllows()`, `seed_demo` also creates a
  non-superuser holding exactly one Group (`auditor` / `audit123`) — a rig
  of superusers can prove acceptance but never a hidden button. The
  activity screen (`app/src/pages/Activity.svelte`) is just an R-006
  drop-in reading the R-003 audit model through its schema-discovered
  `listPath` (`findAuditModel`), never a hand-written `/api/audit/` — and the
  same refusal binds the record sub-view: `fetchAudit()` takes the discovered
  path as its ONLY source of the URL and throws (zero requests) when the
  document has no audit model, so `ModelPage.showHistory()` skips the log half
  instead of probing a guess and tolerating the 404; a guessed
  `/api/audit/` could answer another app's endpoint and be rendered as this
  record's trail, silently. Wire-pinned by
  `app/src/lib/__tests__/lifecycleMount.test.ts`.
  Contract + copy checklist: `docs/rbac.md`.
- New page (non-CRUD module) = drop one `.svelte` file in `app/src/pages/`
  exporting `meta{title,path,nav,icon,order,standalone}` from `<script module>`
  — the same glob contract, applied to routes: `app/src/lib/pages/index.ts`
  validates it, injects the router's route table and the sidebar entry. Router,
  shell and sidebar carry no page-specific line.
- The three drop-in registries (widgets, pages, actions) are ONE contract with THREE
  glob dirs, and the failure mode is a test that grades a module nobody imports:
  `python3 scripts/registry_roster_diff.py` pins which files glob, refuses one dir
  claimed twice, requires each pinned dir to still hold its declared `meta` files and
  each registry to have a non-test product importer. It is the fifth FE twin leg of
  `landing_gate.py --fe` (see *Commands*); the class and its controls: *THIRTEENTH harness law* below.
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
  abstraction) still apply. The prompt the panel ACTUALLY sends is
  `systemPrompt(brand.appName, buildSchemaPrompt(schema))`
  (`app/src/ai/ChatPanel.svelte:69`) and `app/src/lib/__tests__/chatMount.test.ts`
  pins it by asserting the captured request body of a mounted panel —
  unit tests over `buildSchemaPrompt`/`systemPrompt` alone once kept a
  disconnected builder and a stripped legend green, so keep the wire-level
  assertion wired to the real normalized fixture.
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
| `plugin/` | pip package `admincraft` — `branding.py`, `brandstore.py` (runtime store), `views.py`/`urls.py` (branding API), `build_admin`, `dump_schema` (299 pytest, written first) |
| `app/` | thin client — Vite 6 + Svelte 5 + Tailwind 4 + Tauri 2 (416 vitest) |
| `app/src/pages/` | drop-in pages (FR-R006): Dashboard, Modules, ModelPage, Branding, Login, Activity — one `.svelte` each exporting `meta{title,path,nav,icon,order,standalone}` from `<script module>`; registry `app/src/lib/pages/index.ts` globs them and injects the router's route table |
| `app/src/widgets/` | drop-in widgets: StatsCards, ActivityChart (SVG line), QuoteCard (30 curated Qur'an/Sunnah/Aslaf quotes; weakly-sourced ones marked "attributed") + FR-R008 `meta.data`-fed charts: TrendArea, StatusDonut, LeaderBars, HeatStrip, DeltaChip (engine: `app/src/lib/widgets/feed.ts`) |
| `app/src/actions/` | drop-in custom actions (FR-R003): flag.ts (record), bulk_flag.ts (bulk) — one `.ts` each exporting `meta{label,scope,model?,confirm?,input?,handler}`; registry `app/src/lib/actions/index.ts` |
| `app/brands/` | `default/` = the neutral shipped brand ("Admincraft", generated grid-mark icons) + two examples: `freshorama` (dark SaaS), `minimal-light` |
| `skills/` | the two agent skills: `admincraft-onboard` (wire an existing repo onto admincraft) + `admincraft-craft` (guided or source-derived branding) — shared stdlib engine scripts, ask/auto modes |
| `app/src-tauri/` | Rust side, keyring-backed secret storage, generated placeholder icons |
`app/src-tauri/signing/` | committed stable debug keystore for the android apk — why it exists + rotation notes in its README |
| `demo-backend/` | DRF + drf-spectacular rig exercising every field type (FK, enum, decimal, float, date, bool, readonly datetime) |
| `flake.nix`, `guix.scm`, `frontend-dist/` | Nix + Guix packaging — rationale in the file headers |
| `.github/workflows/build-all.yml` | live E2 CI: test-gate + web/windows/linux/android/nix/guix + tag-triggered release (see *CI*, *Releases*) |
| `.github/workflows/build-demo.yml.disabled` | old demo-CI, parked, superseded by build-all |
| `AI-REVIEW.org` | human review queue (P0 security first) + the Svelte debugging war story — read it before touching reactivity |
| `docs/` | E2E screenshots + `order-lifecycle.md` (FR-R001 server contract & client-project convention) + `custom-actions.md` (FR-R003 custom actions + audit reference) + `independent-enums.md` (FR-R002 separated-status-fields convention, schema enum-component naming, guardrails) + `csv-export.md` (FR-R005 two export layers + the shared byte-format contract) + `page-registration.md` (FR-R006 page glob contract + the component-test enabler) + `widget-data.md` (FR-R008 meta.data feed contract) + `rbac.md` (FR-R007 role-claims contract + activity screen) |

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
cd app && npm test                          # 416 vitest
cd app && npx tsc --noEmit                  # clean — 0 errors is the standing bar
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 299 pytest

# mock OpenAI-compatible SSE provider (for chat E2E)
node scripts/mock_openai.js                 # listens on :11435

# FR-R005 cross-twin CSV byte diff (needs app/node_modules; layer 2 probes
# demo-backend/.venv/bin/python then the running interpreter — no venv required)
python3 scripts/csv_twin_diff.py            # 0 = identical, 1 = divergence or coverage lost, 2 = cannot run

# brand CSS twin byte diff — render_css() ↔ brandToCss() ↔ the shipped bundle
# (needs app/node_modules; the plugin is read from plugin/src, no venv required)
python3 scripts/brand_twin_diff.py          # 0 = identical, 1 = divergence, 2 = rig not runnable

# FR-R005 SHARED-TABLE diff — FLOAT_PARITY + the golden literal, pytest side vs vitest side
# (parses both files; needs `node`, but NOT node_modules and NOT the rig venv)
python3 scripts/parity_table_diff.py        # 0 = identical, 1 = divergence or coverage lost, 2 = cannot run

# THE MACHINE GATE vs THE SEAT GATE — .github/scripts/gate.sh (what finalize replays on
# every merge, Lead-owned and read-only here) diffed command by command against
# scripts/landing_gate.py's MERGE_COMMANDS: same legs, same order, same argv, each with
# its `|| FAIL=1` capture still in place. Neither file can see this drift from inside
# itself (see ELEVENTH harness law — the roster of the OTHER gate).
python3 scripts/gate_roster_diff.py         # 0 = identical, 1 = divergence, 2 = cannot run

# the LANDING GATE as one command — pytest + manage.py check + makemigrations --check,
# behind a dep preflight (see EIGHTH harness law: a swallowed boot install must not
# impersonate a red tree). --fe adds vitest AND the five twin harnesses — the
# byte-identity claims, the machine-gate roster and the drop-in registry roster that
# NO single suite can see, since every writer is green against its own fixture;
# --python <exe> forces one interpreter.
python3 scripts/landing_gate.py             # 0 = green, 1 = a leg is red, 2 = cannot run

# the RELEASE story as one command — the four carriers + the Cargo.lock entry vs a
# HEAD tag (or --expect), doc path citations that must exist AND every cited line
# that must land inside its file, the suite counts these docs publish as instructions
# graded against the landing gate's own pins, release inputs present,
# and no PEP 604 annotation in any harness (see NINTH + TENTH + ELEVENTH harness laws)
python3 scripts/release_readiness.py        # 0 = coherent, 1 = a leg is red, 2 = cannot run

# the DROP-IN REGISTRIES as one command — which files glob a contract dir, whether ONE
# dir is globbed TWICE (the dead-twin shape: a test can stay green over a registry the
# app never imports), whether each pinned dir still holds its declared `meta` files, and
# whether any product file consumes the registry the contract test asserts. The
# `*_diff.py` NAME is the wiring: landing_gate's EXPECTED_TWINS cross-check refuses a
# harness on disk its roster does not run, and a roster naming a harness that is gone.
python3 scripts/registry_roster_diff.py     # 0 = ok, 1 = a claim is false, 2 = cannot run
python3 scripts/registry_roster_diff.py --src /tmp/copy   # controls run on copies

# rebrand the whole client in one command (build-time layer)
cd demo-backend && .venv/bin/python manage.py build_admin --brand ../app/brands/default/brand.json --app ../app

# regenerate launcher icons from a 1024px source (in app/)
npx tauri icon ../app/brands/default/assets/icon-1024.png

# derive a brand from any repo's own source (no logo needed)
python skills/admincraft-craft/scripts/derive_brand.py --root <repo> --out <repo>/brand
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
- The client typechecks CLEAN: `cd app && npx tsc --noEmit` exits 0 (it was 7
  errors until 2026-10-21 — one in shipped code, `listRecords` returned
  `Promise<Page>` while `app/src/lib/types.ts:92` declares `Page<T>` with no default, so
  every `build`/`vitest` run silently stripped an unmet type). `vite build`
  uses esbuild and does NOT typecheck, so nothing gated it; keep the command
  green by hand. Edge-case tests that pass values the contract forbids but the
  runtime tolerates (`sanitizeFont` takes `string | undefined`) ride one
  explicit `as unknown as Brand` cast rather than a widened type.
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
- Independent enums (FR-R002, "separated status fields") are per-field
  contracts: drf-spectacular hoists a choices field into a component named
  from the **property name**, not the model (`drf_spectacular/hooks.py:67-95`), so two
  unrelated `status` fields sharing a value set collapse into one shared
  `StatusEnum` and only genuinely different sets stay separate
  (`OrderStatusEnum` + `ShipmentStatusEnum`). Convention: one nested
  `Choices` class per semantic field, never shared across models; declare
  `ENUM_NAME_OVERRIDES` instead of living with the collision warnings; never
  derive one enum from another in client code, and never key lifecycle
  governance on a field *name* — `app/src/lib/statusTransitions.ts` is keyed
  by model id. Full convention + guardrails in `docs/independent-enums.md`.
- Custom actions (FR-R003) follow the widget drop-in contract: one `.ts` in
  `app/src/actions/` exporting `meta{label,scope,model?,confirm?,input?,handler}`
  — the registry globs it, nothing to edit. Endpoint URLs come from
  `actionPath(model, slug, recordId?)`, i.e. the schema-discovered
  `model.listPath`, NEVER from `apiUrl + model.id` (`apiUrl` is only the base
  origin; concatenating a bare segment produced `http://hostapi…` and silently
  broke the R-001 transition/history calls).
- Lifecycle (FR-R001) is a TWO-SIDED proof, never a client-side assertion: the
  registry (`statusTransitions.ts`, keyed by model id) declares the machine,
  `normalizeOpenAPI` binds `model.transitionPath` only from a documented
  `POST …/transition/` and `model.historyPath` only from a `get && !post`
  `…/history/` — the same evidence law as `exportPath`/`mePath`. A machine the
  server does not document is **refused**: `lifecycleProblem()` names the
  reason, `lifecycleAvailable()` gates the DataTable buttons, `showHistory()`
  reads only a discovered path, and `transitionRecord`/`fetchHistory` throw
  rather than re-guess a URL that 404s. Proof is wire-level —
  `app/src/lib/__tests__/lifecycleMount.test.ts` mounts the real page against
  `fixtures/openapi.json` (recaptured from the running rig's `/api/schema/`, so
  it carries the endpoints the renderer calls) and asserts the POST body, the
  URL the client believed in and a 409 `reason` surfacing verbatim. Recapture
  that fixture whenever the rig gains an endpoint. Contract + checklist:
  `docs/order-lifecycle.md`.
- Kanban (FR-R004) groups a model by a **declared** axis in
  `app/src/lib/kanban.ts` (`kanbanAxes`, keyed by model id like
  `statusTransitions`), never by "the field named status" or "the first enum
  field" — `docs/independent-enums.md` §6 forbids the guess, so a model with no
  entry shows no toggle. An axis that contradicts the machine (a `transition`
  axis with no R-001 entry, or a `patch` axis on a lifecycle field, or a
  non-enum field) is **refused** — no board, with `axisProblem()` naming the
  reason — rather than rendered optimistically. A drop on a lifecycle axis
  fires `POST <model.transitionPath>` only for a state the registry allows;
  a drop on a free enum is `patchRecord` with a **one-key body** (never a
  whole-row PUT). Drag-and-drop is mouse-only by nature, so every column a drop
  would accept is also offered by a per-card "Move to" `<select>` — keyboard and
  screen-reader users get the identical move set, illegal targets are disabled.
  Proof is mounted, not inferred: `app/src/lib/__tests__/kanbanMount.test.ts`
  renders ModelPage plus the real board against `fixtures/openapi.json` and
  pins the board-sized `page_size=100` on the DISCOVERED listPath, the exact
  `{"transition":"<target>"}` body and URL from BOTH the select and a
  drag/drop pair, the disabled-option set for an illegal target, the read-only
  Unassigned bucket, and the no-`transitionPath` refusal (no toggle, no probe).
  The board ALSO mounts alone with a spy `onmove`: through the page an illegal
  drop is refused twice (board guard + `planMove`), so only the isolated mount
  pins `KanbanBoard.drop()`'s own `!allowed` guard — a mutant that removed it
  survived every page-level assertion.
- CSV export (FR-R005) keeps its two layers uncollapsed: DataTable "Export
  table" = visible columns of the CURRENT page, client-side, no server call;
  "Full export" = `GET <listPath>export/` line-level (child rows repeat parent
  ids, pk order, search honoured, `pagination_class=None`) and its button is
  bound **only when the schema documents it** — `normalizeOpenAPI` sets
  `model.exportPath` on `get && !post` at that path, and `fetchCsv` calls
  base + the discovered path, never `apiUrl + "export"`. The writer twins
  (`app/src/lib/csv.ts` ↔ `demo-backend/shop/csv_export.py`) are
  byte-identical for the same rows — RFC 4180/CRLF/QUOTE_MINIMAL, null→empty,
  lowercase booleans, decimals never re-flowed, formula guard on text keyed by
  NUMERIC *shape* (DRF sends decimals as strings), BOM added once
  (`csvBlobParts` is BOM-idempotent) — keep them in sync like
  `brandToCss`/`render_css`; same commit, both sides, on pain of the two
  layers disagreeing on every negative price. The twins are held to one byte
  spec by a SHARED table: `FLOAT_PARITY` (a Python `float` renders with
  ECMAScript's `String()` form — `js_number_text()` — because layer 1 sees the
  JSON-parsed number, and the formula guard is keyed on
  `isinstance(value, str)`, never on the rendered text) appears with the same
  values and expectations in `plugin/tests/test_csv_export.py` and
  `app/src/lib/__tests__/csv.test.ts`, and the golden document carries a float
  column on both sides. The golden document ALSO doubles its datetime column
  (one row an aware `datetime`, one row the same instant as text) because a
  text-only cell cannot test the server's rendering rule at all — that blind
  spot hid divergence #2: DRF writes UTC as `…Z` while `isoformat()` writes
  `…+00:00`, so every datetime column of a live export differed. The server now
  mirrors DRF step for step in `drf_datetime_text()` (naive → project-local,
  aware → project timezone, `+00:00` → `Z`) and reads the offset from
  `django.utils.timezone`, never a hard-coded UTC — a project with another
  `TIME_ZONE` gets `+06:00` in its JSON and must write the same. Any test that
  asserts literal bytes therefore pins the timezone (`utc_project_timezone`),
  since `plugin/tests/conftest.py` sets no `TIME_ZONE` and Django's default is
  `America/Chicago` while the rig declares `UTC`. The rig is now the fixture for
  all of it: `Order.weight` is a real `FloatField` (the field type the rig was
  missing), seeded with `2.0`/`1e-7`/`1e17`/`-0.00042`/`NULL` and carried as a
  column of the line-level header, so the two writers can be diffed over live
  HTTP rows — measured 60 rows × 10 parent columns, zero mismatches
  (`docs/csv-export.md` §6). Server: the `@action` needs a
  `text/csv` renderer in `renderer_classes` or the client's own Accept 406s
  before the view runs; `csv_export.py` stays DRF-free because `@extend_schema`
  captures `DEFAULT_SCHEMA_CLASS` at decoration time. Contract in
  `docs/csv-export.md`.
- Dynamic components take the runes form `{@const Widget = w.component}` then
  `<Widget />`, never `<svelte:component this={…}>` — deprecated in runes mode.
  Both declaration-driven grids comply now: `app/src/components/Shell.svelte:53` (pages, FR-R006)
  and `app/src/pages/Dashboard.svelte:22` (widgets, FR-R008). The widget grid had no DOM test
  until `app/src/lib/__tests__/dashboardMount.test.ts`, which is registry-driven
  like the shell tests — a drop-in that fails to render is a red test, not an
  empty card.
- The last four components with zero test references are pinned by
  `app/src/lib/__tests__/gapMount.test.ts`: `ErrorBanner` (renders only while
  `backendDown`, names the **override** URL before the stored config, Dismiss
  clears the store flag not just the DOM), `Modules` (its own registry stubbed,
  so the refusal list and the parameterised-row rule are provable without
  dropping a deliberately broken page into `src/pages/`; the header's two
  counters are asserted with DIFFERENT numbers so a variable swap is visible),
  `StatsCards` (exactly one request per model, `base + discovered listPath +
  ?page=1&page_size=1` with the token header, the server `count` not a row
  length, zero requests until the schema lands, one sweep per load, card click
  routes by model id) and `QuoteCard` (brand name painted from the live store,
  the flip holds its text mid-animation and swaps at 225 ms, `randomQuote`'s
  exclusion re-roll counted from `Math.random`, a second click swallowed).
  Two harness traps this file exists to record: a **constant** `Math.random`
  stub sends `randomQuote`'s re-roll loop (`while (i === excludeIndex)`) spinning
  until the test process OOMs — script the draws as a finite sequence; and
  `vi.useFakeTimers()` must not meet a `vi.waitFor()` poll, so components that
  paint from stores alone mount synchronously.
- A component's cell text is only proven when it is rendered through the REAL
  helper. `DataTable.test.ts` carried `vi.mock("../lib/utils", …)` stubbing
  `formatCell` to `String(v ?? "")` while its own tests judged each-keys in
  plain code — the mock never ran, the real display rules never ran, and the
  pair stayed green together (`app/src/lib/__tests__/utils.test.ts` now pins
  formatCell/toISOOrNull/debounce on the shipped module;
  `app/src/lib/__tests__/tableDisplay.test.ts` mounts DataTable unmocked and
  asserts the DOM: em dash, FK `#`, enum pill, the 57+… ellipsis at exactly 60
  chars, a decimal never re-flowed, and the json column refused — with json
  placed MID-list so the six-column slice cannot mask a dropped filter).
  If a mount test needs a module stub, pin the same values through the real
  one somewhere. Same sweep deleted two dead exports: `fromDateOrNull()`
  (`RecordForm.buildPayload` already inlines the rule) and an unused
  `DataTable` import in `actions.test.ts`.
- The same mock-hides-the-real-code trap bites a **pure logic module**, not just
  components. `app/src/lib/stores.ts` carries the app-wide error policy
  (`handleApiError`) and the config override merge (`effectiveConfig`) — and
  every consumer test only ever *mocked* them (`app/src/lib/__tests__/RecordForm.test.ts:9-10`), so the
  three shipped branches (network→banner flag, 401→logout+toast, 400→toast with
  `: detail`) never executed and sat at 64% stmts / 52% branch.
  `app/src/lib/__tests__/stores.test.ts` now drives the REAL functions and
  asserts the EFFECT on the live `app`/`claims`/`toasts` stores and
  localStorage (no mounting, no mocking of this module). Its `toast` case is the
  module-owned-timer sibling of `QuoteCard`'s 225 ms flip: it advances fake time
  to 3999 ms (still present, proving the cap is 4000 not smaller) then +1 ms
  (gone), and a second test proves the timer dismisses ONLY the expired toast —
  a per-id filter mutation would wrongly sweep the sibling. Five mutants
  (override precedence, `401→403`, dropped `logout()`, removed `: detail` join,
  `4000→5000` timer) each fail a named test; stores.ts is 71% stmts / 71% branch
  after. The still-uncovered lines are the fetch/Tauri paths (`loadSchema`,
  `saveAiSettings`, native window title) — network behaviour, not decision logic.
- The 17:05Z note's "still-uncovered fetch/Tauri paths" are now closed for the
  login half: the whole demo flow starts at `app/src/pages/Login.svelte`, and its
  `submit()` (the auth POST, the token persist, the schema + claims fetches, the
  three error branches) had ZERO proof — every consumer test mocked `../stores`.
  `app/src/lib/__tests__/loginMount.test.ts` mounts the REAL page with the REAL
  stores/api/secrets and stubs only `fetch`, so every assertion is a URL or a
  byte: the POST goes to the config's `authPath` (never a guessed
  `/api-token-auth/`) with no `Authorization` header, the token that comes back
  is what the schema GET carries, the claims read travels the `mePath` the
  DOCUMENT names, `normalizeOpenAPI` ran (only the normalized shape has
  `byId`/`listPath`), and a failed login keeps no token. Login.svelte is 100%
  stmts/branch after (was 55/50). Two notes for the next seat: assert a
  navigation through `location.hash` + a dispatched `hashchange` (happy-dom
  assigns the hash but never fires the event, so the router store would read
  stale), and reach for a sentinel password — the shipped hint text literally
  prints `admin / admin123` (Login.svelte:95), so a "no secret in the DOM"
  assertion written with that value can never fail.
- `app/src/lib/secrets.ts` Tauri branches were the third mock-hides victim
  (64% stmts): the web-localStorage fallback covered three of four paths and the
  keyring commands ran zero tests, on both suites' green word. They are a
  BOUNDARY contract — `src-tauri/src/lib.rs:10` keeps `DEFAULT_SERVICE:
  "admincraft"` and the commands take `(service, key, value)`; a renamed or
  dropped argument lands the key under a different keychain bucket or fails the
  Rust signature, invisibly in web mode. `secrets.test.ts` now pins each
  `invoke()` tuple with `vi.resetModules()` + `vi.doMock("@tauri-apps/api/core")`
  per case (the dynamic `import()` inside the functions must resolve to a fresh
  mock and a fresh `webWarned`), asserts `NoEntry`/unavailable keychain both
  degrade to `null` rather than killing `loadAiSettings`, and proves the
  security warning fires exactly once across all three ops. secrets.ts 100/100.
  Mutant caveat worth remembering: dropping `.trim()` from the stored
  `apiUrlOverride` SURVIVED — an `<input type="url">` already strips surrounding
  whitespace per spec (verified against happy-dom's readback), so that trim is
  redundant defensive code, not a live bug. Record an equivalent mutant as
  equivalent; do not bend a test to "kill" it.
- `app/src/lib/stores.ts` had a FOURTH mock-hides gap and one genuinely
  USER-VISIBLE defect behind it. `saveAiSettings` skipped the secret write when
  the key field was empty, while `app/src/ai/ChatPanel.svelte:33` hydrates that field from
  the store — so clearing the API key saved nothing and the old key came back on
  next boot. Now an empty field means "forget it": `deleteSecret("ai.apiKey")`,
  proven by a save-then-clear-then-reload round trip (`storesTauri.test.ts`),
  both under the mocked keyring and in web fallback. Two harness laws learned
  here, both worth copying:
  1. **Proving a negative needs a macrotask, not microtasks.** The fire-and-
     forget `void setNativeWindowTitle()` chain (`await import()` + `await
     setTitle()`) survives an `expect(setTitle).not.toHaveBeenCalled()` that
     waits only `await Promise.resolve()` twice — the guard under test looked
     proven while a deleted guard still passed the whole file. A `setTimeout`
     boundary drains the dynamic-import chain; the positive test in the same
     file proves that budget is enough. Any "never called" assertion must be
     re-run against a mutant that DOES call it.
  2. **Tauri mode is a marker on the real happy-dom window**
     (`window.__TAURI_INTERNALS__ = {}`), never a replacement — `document`,
     `localStorage` and the CSS injection target must stay live while the
     `@tauri-apps/api/{core,window}` entry points are mocked per case with
     `vi.resetModules()` + `vi.doMock` + a dynamic `import("../stores")`.
  3. **…but `vi.resetModules()` is forbidden once a COMPONENT is mounted.** The
     dynamic import rebuilds `svelte` itself, so the freshly imported component
     belongs to a SECOND client runtime whose effect queue the test file's
     statically imported `flushSync()` never drains. The symptom is a silent
     false negative: the click reaches the button (prove it with a capture
     counter), `showSettings` flips, and the DOM simply never re-renders — which
     reads as "the gear is broken". For a component-under-test, mock the leaf at
     FILE level (`vi.mock("@tauri-apps/api/core", () => ({ invoke }))`, a hoisted
     spy the marker switches at call time — `secrets.ts` imports `invoke`
     lazily, so web cases never resolve it) and keep ONE module graph per file.
     `resetModules` stays correct for pure modules like `stores.ts`/`secrets.ts`.
  stores.ts is 100% stmts / 93.3% branch; the surviving branches are the
  `typeof localStorage/window === "undefined"` guards (unreachable under
  happy-dom — equivalent, recorded as such). `loadSchema`'s in-flight guard and
  its no-token read are pinned too: a second `loadSchema()` while one is pending
  fires ZERO extra requests, and the anonymous read carries no Authorization
  header, and the claims degradation (documented `mePath` vs none) is asserted
  by the exact URL list, so a guessed `/api/me/` probe fails the file.
  `ChatPanel.svelte` is now 97.8% stmts / 93.4% branch / 100% funcs
  (`chatPanelMount.test.ts`, 14 cases): the settings form is driven by clicking
  Save provider / Cancel / the gear / the Ctrl+K launcher, the key-clearing fix
  is re-proven through the FORM rather than only the store, `Stop` aborts a real
  in-flight stream ("… — stopped."), a 429 surfaces verbatim with the empty
  assistant bubble popped (asserted by bubble COUNT, not by the absence of an
  ellipsis — the placeholder only renders while streaming, so a text scan cannot
  see the ghost), and the keyring path is pinned with a sentinel scan proving no
  key byte reaches `localStorage` in Tauri mode. The one uncovered line — the
  `if (!configured)` guard inside `send()` — is UNREACHABLE through the UI: the
  composer renders only in the `{:else}` branch of `{#if showSettings}{:else if
  !configured}`, so it is recorded as dead-defensive, not bent into a test.
- **FOURTH harness law — a props re-spread re-fires prop-reading `$effect`s
  even when every value is identical.** Svelte 5 (probed 2026-10-21 against
  `fixtures/ScratchPage` semantics, reproduced in `recordFormMount.test.ts`'s
  "identical values" case): a parent that re-renders `<Child {...$writable}/>`
  bumps the child's prop signals as ONE unit, so an effect reading only
  `modelId` re-runs when an unrelated `recordId` — or nothing at all — arrives
  in a new object. Consequences, both pinned by mutants:
  1. `ModelPage`'s "model-switch" reset `$effect` actually fires on EVERY route
     params change, which is why it must close the editor (`formOpen=false;
     editing=null`) — a deep link to another record can only ever REMOUNT
     `RecordForm`, never move its props through the page.
  2. So a test that drives `ModelPage` props cannot exercise `RecordForm`'s own
     re-hydration `$effect` — it passes with the effect deleted (surviving
     mutant, caught only by mutation, not by reading). Contract-level code gets
     a parent of its OWN (`fixtures/RecordFormHarness.svelte` +
     `recordFormHarnessProps`): move `record`/`model` on the mounted instance,
     assert the fields re-hydrate, the FK lists re-fetch, and the PUT lands on
     the NEW row's path — then keep the identity-gate case (an equal re-spread
     must fire ZERO refetches), which is the mutant-killer for the `seen`
     comparison the effect opens with.
- **FIFTH harness law — a byte-twin diff must compare the WHOLE writer, in
  bytes.** `scripts/csv_twin_diff.py` now runs the FR-R005 cross-twin diff
  (`docs/csv-export.md` §6) on one command, because that proof had been made
  by hand twice and then lost with the segment that wrote it. Two false
  `DIVERGENT` readings were paid for it (2026-10-21, 3082 + 870-cell runs, both
  clean):
  1. **Comparing the wrong pipeline stage.** Layer 2's `csv_cell()` applies the
     formula guard and returns bare text; the QUOTING happens later inside
     `csv_text()`'s `csv.writer`. Layer 1's `csvCell()` does BOTH at once.
     Diffing `csv_cell` output against `csvCell` output reports the server as
     "not quoting commas" and "not guarding formulas" — phantom divergences in
     the unsafe direction. The only honest comparison is document vs document:
     `csv_text(header + [[csv_cell(v) …]])` against
     `buildCsv(header, rawValues)`.
  2. **Reading the artifacts in text mode.** Python translates `\r\n` to `\n`
     on read, so a CRLF document splits into one "line" and two byte-identical
     files look divergent (`cmp` said 86952 B = 86952 B while the text-mode
     compare printed `DIVERGENT`). Compare `read_bytes()`.
  The harness proves itself before it is trusted: with the server guard
  switched off (`if False and is_text and is_formula_text(text)`), it names
  every apostrophe difference (`line 10: client=b"8,'=SUM(A1:A9)"
  server=b'8,=SUM(A1:A9)'`); restored, it prints `BYTE-IDENTICAL`. Exit 0 =
  equal, 1 = divergence, 2 = the rig could not run (no `node`/`node_modules`, or
  no interpreter that can import the rig's deps) — it is a re-verifier, not a
  suite member, so it never lands in pytest/vitest where node would be assumed.
  Third control, found while writing the brand harness: the exit-code contract
  itself was leaky. With `npx` absent from PATH the launcher raised
  `FileNotFoundError` and the script died with a traceback and **exit 1** — the
  code that means "the writers disagree". A CI seat reading only the number
  would have filed a divergence that never happened (measured:
  `PATH=/nonexistent python3 scripts/csv_twin_diff.py` → traceback, 1). Now a
  launch failure is caught into a synthetic 127 and reported as exit 2, in both
  harnesses (`scripts/csv_twin_diff.py:248` `run()`,
  `scripts/brand_twin_diff.py` `run_client_probe()`); a harness with three
  documented exit codes has to prove each of them, not just the green one.
  Fourth control, same trap from the OTHER side: a false BLOCKED. An exit 2 is
  only honest if the thing genuinely cannot run, and `csv_twin_diff.py` was
  demanding `demo-backend/.venv/bin/python` BY PATH — so on a box whose system
  python satisfies every rig dependency it printed "cannot run" in 0 s and the
  FR-R005 live claim stayed un-re-runnable (measured here: the same interpreter
  ran the server probe perfectly, and `scripts/brand_twin_diff.py` had always
  worked without a venv). Worse, the CI landing gate pip-installs the plugin into
  its OWN environment and never builds a rig venv, so the gate could not have
  re-run the very harness its docs cite. Layer 2 now resolves an interpreter by
  PROBE (venv first, then the running one; `import django, rest_framework,
  drf_spectacular, admincraft`) and prints `layer 2 interpreter: …`, because a
  pass must say which environment proved it; `--python <exe>` is honoured
  exclusively — when a seat names an interpreter, that interpreter's failure is
  the answer, not a licence to fall back and report someone else's green.
  Controls measured: nonexistent exe → 2 `cannot launch`; a real dep-free venv
  → 2 naming `No module named 'django'`; a dep-free `.venv` sitting at the
  preferred path → falls back and says so, still 0; the bool branch mutated
  server-side (`true/false` → `1/0`) → 1 naming `line 101: client=b'98,false'
  server=b'98,0'`. Third-party finding, caught while writing this paragraph: a
  `str | None` annotation in the new resolver was the only PEP 604 syntax in
  all of `scripts/` — on a Python < 3.10 box it raises at IMPORT time, i.e. a
  launcher crash with rc 1, the same false `DIVERGENT` as the 127 above, from a
  whole different cause (interpreter version, not missing tool). Removed; a
  re-verifier's own syntax is part of its exit-code contract.
  The lesson generalises: **a harness must fail to run for a
  reason it can name, and succeed with the environment it can show.** Both
  halves are exit-code contracts; only the first one was written down.
- **SIXTH harness law — when the two artifacts are SUPPOSED to differ, normalize
  the difference deliberately and prove the diff bites on the rest.** The brand
  twins (`plugin/src/admincraft/branding.py:196` `render_css()` ↔
  `app/src/lib/branding.ts:37` `brandToCss()`, AGENTS.md *Runtime branding flow*)
  carry banners that differ on purpose — a generated file says "do not edit by
  hand", a runtime `<style>` says "injected" — so a raw byte compare of the two
  documents prints a guaranteed false `DIVERGENT`. `scripts/brand_twin_diff.py`
  therefore compares from the first `@import` to the end, trailing whitespace
  stripped, and PRINTS both banners instead of hiding them: the normalization is
  justified by a documented intent difference, not chosen to make the diff pass.
  What the segment found, all measured rather than reasoned about:
  1. **Filter the matrix through the validator, then PIN each refusal.** "Both
     writers agree" only means something over the domain where both are
     contracted to run, so the script generates 350 brands and keeps the ones
     `validate_brand()` accepts. Counting the refused half is not enough — see
     ELEVENTH law below, where a loosened radius rule moved 3 brands across that
     line and the harness still said `BYTE-IDENTICAL`. Each sentinel now carries
     the verdict the server owes it and the leg checks it row by row. Surprises
     here are real: `"\tTabbed Font\t"` is ACCEPTED (the
     server matches `SAFE_FONT_RE` against `font.strip()`, `plugin/src/admincraft/branding.py:190`) and
     the client strips the same tabs via `sanitizeFont()` — so a brand that looks
     invalid in the accepted column is not a divergence, and the only way to know
     was to run it. It now sits in `VALID_FONTS`, where the finding actually puts
     it, and keeps its twin coverage.
  2. **A sentinel must vary one axis at a time, and the font axis earns its
     keep.** `render_css()` writes `font.replace(" ", "+")`; `brandToCss()` runs
     `encodeURIComponent()` and turns `%20` back into `+`. Those agree for every
     name the schema allows, so one `Inter` row proves nothing: mutating the
     server to write `%20` diverged on 146 of 300 accepted brands — exactly the
     multi-word ones — and a single-word matrix would have called that refactor
     safe. `Space  Grotesk` (double space), a 60-char name, digits and
     space-padded names are what killed it.
  3. **The third check is not a writer, it is the artifact.** `app/public/brand.css`
     + `brand.json` are first paint; `applyBrand()` re-injects at boot. If the
     bundle is stale (`build_admin` not re-run) or the runtime inject differs
     from it, the user sees the UI re-theme under them — the FOUC the static
     bundle exists to prevent, and no unit test on either writer can see it,
     because each is green against its own fixture. The script asserts
     `bundle == render_css == brandToCss` for the shipped brand — and locates
     that brand BY IDENTITY in the accepted set, never by position (ELEVENTH law:
     a positional `runtime_css[-1]` once compared the shipped brand's build-time
     CSS against an unrelated random brand and called the difference a re-theme
     flicker).
  Negative control, before the green meant anything: dropping one `@import`
  weight from the client → `TWIN DIVERGENCE — 300 of 300`, line 0 quoted per
  side; the `%20` server mutant above → 146; editing the shipped
  `--brand-radius` → `BUNDLE STALE … line 8`. All three product files restored
  byte-identical (`git status` clean on those paths). Like the CSV harness this is
  a re-verifier, not a suite member — it needs `app/node_modules` and exits 2 when
  the rig cannot run, so the landing gate never grows a toolchain dependency.
- **SEVENTH harness law — a SHARED TEST TABLE is a twin too, and it must be
  diffed by value identity, not by either language's rendering.** The FIFTH and
  SIXTH laws both protect the *writers*; the FR-R005 proof has a third pair of
  copies nobody could re-check: `FLOAT_PARITY` and the golden document literal
  exist once in `plugin/tests/test_csv_export.py` and once in
  `app/src/lib/__tests__/csv.test.ts`, and AGENTS.md calls them "a SHARED table".
  Each side's suite is green against ITS OWN copy, so editing one copy — a value
  added, an expectation retyped, a golden re-wrapped — leaves 299 pytest + 416
  vitest green while the shared adjective silently dies, and the twin proof stops
  covering the case the table was written for.
  `python3 scripts/parity_table_diff.py` is the re-verifier: exit 0 identical /
  1 divergence / 2 could not run. Three things it had to get right, all measured:
  1. **Key a float by its bytes, not by its text.** `str(1e17)` is `"1e+17"` and
     `String(1e17)` is `"100000000000000000"` — disagreeing *by design*, which is
     the very claim under test. So the harness compares the IEEE-754 big-endian
     bytes (`struct.pack(">d")` ↔ `Float64Array`+`Uint32Array`) alongside the
     expectation string. `0.0` and `-0.0` stay distinct rows that way, as they
     must (both expect `"0"`).
  2. **Normalize only what is documented to differ — here, the ROWS, not the
     document.** The Python golden passes `Decimal("19.99")` and an aware
     `datetime`; the JS one passes the text and JSON number DRF actually sends
     (both docstrings say so). The comparable artifact is the asserted BYTE STRING
     both writers must produce, so that is what gets diffed and the row spellings
     are deliberately not compared.
  3. **Anchoring on a *substring* of a subject name is a false green.** Naming
     `const FLOAT_PARITY` and searching for it as text still read BYTE-IDENTICAL
     after the declaration was renamed `FLOAT_PARITY_RENAMED` — the prefix hit
     pulled in the renamed array, i.e. the harness had silently changed subject.
     The JS declaration is now matched with a word-boundary regex and the Python
     golden must be the UNIQUE `csv_text(... csv_cell( ...) == <one literal>`
     assert: the small unit asserts also call `csv_text`, and the first one
     matched made the harness compare a 19-byte toy against the 226-byte golden
     and confidently print `DIVERGENT`. An ambiguous subject now stops with exit 2
     instead of guessing.
  Exit codes are all proven, including the ones nobody had exercised on a
  *launcher* before: node absent from PATH → 2 (not the 1 that means divergence);
  subject renamed → 2; golden RHS no longer one literal → 2; a second
  golden-shaped assert → 2 "subject is ambiguous"; an uncaught internal crash →
  2 (the first run died on an `ast` attribute error and returned 1 — a false
  DIVERGENT from a check that never completed, the same leak `csv_twin_diff.py`
  lost last segment, so the script now wraps its own entry point). Divergence
  controls that bit: JS expectation `-1e-9`→`-1e-8` names the python-only /
  js-only pair; deleting one Python row reports 24 vs 25 and names the js-only
  row; a golden byte `19.99`→`19.98` prints the two lines side by side. Both test
  files came back byte-identical (`git status` clean). Still a re-verifier, not a
  suite member — it needs `node` but NOT `node_modules` or the venv, because it
  parses the two files instead of importing them.
- **EIGHTH harness law — a GATE that lives as prose is a check nobody can re-run,
  and an exit code is only a verdict if the check could start.** The landing gate
  (AGENTS.md *LANDING GATE*: `pytest plugin/tests -p no:cacheprovider -q` +
  `manage.py check` + `makemigrations --check`) is the one command every seat runs
  before pushing, and it existed only as three lines of prose retyped by hand.
  Two failure modes, both measured this segment, not reasoned about:
  1. **A launcher bug impersonates a red tree.** The boot install
     (`pip install -e /workspace/plugin --no-deps -q 2>/dev/null || true`,
     `.turn-inside.sh:16`) hides its own failure — a standing escalation
     (19:59Z/20:09Z reports) in a Lead-owned file — so on this box the pytest leg
     died with INTERNALERROR `No module named 'admincraft'`, and pytest's exit
     code for that is **2**: the same number the harnesses use for "cannot run"
     and a seat reads as "my work is red". The gate is fixable seat-side even
     though the runner is not: `scripts/landing_gate.py` probes
     `import django, rest_framework, drf_spectacular, admincraft` first and, on
     failure, exits 2 printing the interpreter, the missing module and the exact
     install command.
  2. **`rc 0` is not the claim.** `manage.py check` answers 0 without proving the
     rig booted, so that leg asserts the phrase `System check identified no
     issues` in its own output; the pytest leg parses `N passed` out of the `-q`
     summary and refuses a green rc that carries no pass count or names a
     failure; `makemigrations --check` must print `No changes detected`. A leg
     that exits 0 while its summary contradicts it is RED, not green — that is
     the same false-green class as the renamed `FLOAT_PARITY` that still printed
     BYTE-IDENTICAL (SEVENTH law, trap 3), arriving from the exit-code side.
  Controls measured, each restoring the tree (`git status` clean on every touched
  path): dep-free interpreter → 2 naming `ModuleNotFoundError: No module named
  'django'` + the fix; nonexistent `--python` → 2 `cannot launch` (the FIFTH
  law's 127-trap — a launch failure is never reported as divergence);
  `app/node_modules` absent → 2 naming `npm ci`; one deliberately failing test →
  1 naming pytest, reported as `1 failed, 299 passed`, while the other legs stayed
  green and printed (legs run INDEPENDENTLY on purpose, so a seat sees the whole
  picture instead of the first failure hiding the rest); a temporary model field
  with no migration → 1 naming the migrations leg AND 78 pytest errors, which is
  the bonus finding: the gate's prose implies three independent checks, and the
  rig's fixtures couple leg 1 to the schema, so a schema change must be run
  through all three, never "just" the migrations check. The verdict prints the
  interpreter it used — `NAME THE ENVIRONMENT THAT PROVED IT` (20:09Z note), now
  applied to my own tool rather than only asked of peers.
  EXTENDED the same segment: `--fe` now runs the three twin harnesses as gate legs,
  because the gate was missing exactly the class of red that no per-side suite can
  see (every writer here is green against its OWN fixture while the claim lives
  *between* them). Merging someone else's harness needs the same two refusals, not
  a trust bump: the leg maps the harness's documented `1 = divergence` to RED,
  `2 = cannot run` to CANNOT RUN, **any other code** to CANNOT RUN ("exited 3,
  outside its documented 0/1/2 contract") — an undeclared code is not a verdict —
  and it still requires `BYTE-IDENTICAL` in the output, because a harness that
  exits 0 without ever printing its own success phrase has compared nothing.
  The merge-gate default stays three legs: the twins answer CANNOT RUN wherever
  `app/node_modules` is absent, and a tooling gap must not stall every merge.
  Five controls, tree restored after each: tampered `app/public/brand.css` → RED
  naming brand-twin + `the twins DIVERGE`; `app/node_modules` renamed → CANNOT RUN
  quoting the harness's own `npm install` line; rc 0 with no output → RED
  `exit 0 alone never proved the compare happened`; rc 3 → CANNOT RUN naming the
  contract break; both twins clean → green. `--fe` rc 0 measures 299 pytest /
  416 vitest / csv 3070 cells 56287 B / brand 302 accepted brands over a pinned
  population of 350 / parity 226 B
  golden, on `/usr/local/bin/python3` with django 5.2.18.
- **NINTH harness law — a RELEASE procedure is a set of facts about files, and
  files rot silently.** AGENTS.md *Releases* promises "bump the version in ALL
  FOUR carriers first … the tag should match them" and points at a reference
  implementation. Nothing re-ran either claim, so building the check found the
  second one false immediately: `scripts/cut_v010_release.sh` is cited in
  AGENTS.md, docs/DEVGUIDE.md and three comments in
  `.github/workflows/build-all.yml` (Lead-owned, so cited not edited) as the
  script that cut v0.1.0 — and exists in ZERO git objects (`git rev-list --all
  --objects | grep -i cut_v010`: empty). The prose is corrected to name the real
  reference, the `release` job's own assemble step
  (`.github/workflows/build-all.yml:417-443`). `scripts/release_readiness.py`
  (exit 0 / 1 red / 2 cannot run, per the FIFTH law) now holds the whole story
  re-runnable: five version reads — `plugin/pyproject.toml`, `app/package.json`,
  `tauri.conf.json`, `Cargo.toml`, and the `admincraft` entry inside `Cargo.lock`
  (the pair the nix `cargoLock` and guix vendor builds depend on, so a lock that
  drifted from its manifest is a packaging break, not a typo) — a `vX.Y.Z` tag on
  HEAD or `--expect X.Y.Z`, the release inputs (`debug.keystore`, `flake.nix`,
  `guix.scm`), the citation scan, and the 1ce3045 rule machine-enforced: a
  `ast.walk` over annotation nodes for `BinOp(BitOr)` finds a PEP 604 `X | None`
  in a harness, because `ast.parse` alone CANNOT — the syntax is valid, it dies
  at def time on a < 3.10 box, and it dies with rc 1, which in this family means
  "the writers DIVERGE". A dead-path allowlist carries the reasons (the two
  deliberate "the old X is gone" / example citations) and the leg goes RED if an
  allowlisted path reappears, so the exemption rots in both directions. Controls
  measured, each restoring the tree: one carrier bumped → 1 naming all five
  values on two legs; `--expect 0.2.0` → 1 naming `plugin/pyproject.toml:7`; the
  dead file created → 1 `allowlist is stale`; a fresh bad citation appended → 1
  naming `docs/widget-data.md:127`; a PEP 604 temp script → 1 naming the line;
  `plugin/pyproject.toml` moved aside → **2** not 1 (a missing input is not a
  verdict).
- **TENTH harness law — a `file:line` citation is HALF a claim, and the half a
  path check sees is the half that cannot fail.** `release_readiness.py` now
  bounds-checks every cited line (`leg_citation_lines`): a doc pointing at
  openapi.ts line 9999 resolves perfectly and stays green under the
  path leg while sending the next reader into unrelated code — the same failure
  direction as NINTH, arriving one level deeper (NINTH was a dead PATH, this is a
  live path with a dead NUMBER, invisible to an existence test by construction).
  Illustrative numbers like that one are deliberately written WITHOUT backticks:
  the leg scans backticked tokens, so a hypothetical in backticks is
  indistinguishable from a claim and correctly goes red — which is how this
  paragraph was caught on its own first run.
  Resolution is deliberately CONSERVATIVE, because a resolver that guesses files
  a confident verdict about the wrong file: verified only when the target is an
  exact repo path, a directory suffix matching exactly ONE repo file, or a
  site-packages path the running interpreter can import. `docs/independent-enums.md`
  used to cite settings.py:120 bare, meaning **drf_spectacular's**, while this
  repo's only
  `demo-backend/core/settings.py` has 110 lines — so a bare
  citation is reported as `bare-name not verified` and the leg stays silent, and
  the writer rule is **cite the directory**. External citations are checked
  against the installed package and the log PRINTS THE VERSION it checked them
  against (`drf_spectacular 0.30.0` here) — a line number is only true of one
  release, so an upgrade turning these red is the correct verdict, not noise: the
  doc's "measured on 0.30" claim would be stale. Measured payoff: qualifying 24
  bare citations (16 in `docs/independent-enums.md`, 7 in DEVGUIDE, 1 in
  AGENTS.md) took verified lines **26 → 50** and guesses **24 → 0**; the tree now
  measures **54 bounds-checked (35 repo + 19 site-packages), 0 guesses**, all 19
  drf-spectacular line claims land in range, and the 7 sampled by eye hit their
  exact code (`ENUM_NAME_OVERRIDES: {}` at `drf_spectacular/settings.py:118`,
  `ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE: True` at
  `drf_spectacular/settings.py:120`, `x-spec-enum-id` hashing at
  `drf_spectacular/hooks.py:50-58`, property-name keying at
  `drf_spectacular/hooks.py:67-76`). The leg caught two bare citations IN THIS
  PARAGRAPH on its own first run, which is the rule applying to its author.
  Controls, each
  restoring the tree byte-identical: two past-EOF citations → 1 naming both with
  the real lengths (229, 251); a past-EOF site-packages citation → 1; the same
  citation re-bare'd → **0** with `1 bare-name not verified` (the false-red
  control — the leg must refuse, not guess); an unknown external path → 0 with
  `2 unresolvable` (no verdict about a file it cannot read); `docs/widget-data.md`
  grown to 127 lines → 1 `line allowlist is stale`, because the one exempted
  citation quotes THIS harness's own reject message rather than naming a
  location, and an exemption may not outlive its reason.
  THIRD DOOR, MEASURED ON THIS DOCUMENT: **in range is not on target.** Until this
  pass DEVGUIDE cited `scripts/csv_twin_diff.py:109` for `run()`, while line 109 of
  that commit was the closing `"""` of `CLIENT_SPEC` and `run()` started at 126 (248
  now, after the population pins landed). A bounds check cannot see this class at all —
  the number is inside the file, so the leg is green while the citation sends the reader
  to unrelated code, and every edit that MOVES code silently ages the number. Writer
  rule: cite a SYMBOL a reader can grep, or re-measure the number in the same commit
  that moves the code.
  THE CANDIDATE IS NOW BUILT: `release_readiness.py` `leg_citation_targets` checks the
  cited range against the symbol its own doc line spells. It stays a CHECK (it is not
  one of the three landing-gate legs) and the claim class is deliberately NARROW — a
  `name()` spelling on the same line as the citation — and that narrowness is a
  measurement, not a hunch: broadening it to any identifier word on the line scanned
  **576 claims and fired on 425 of them** (re-measured on the delivered tree — these two
  numbers move with every doc edit, which is exactly why control 6 re-measures them
  instead of trusting this sentence), all FALSE (`AGENTS.md:190` cites
  `core/urls.py:10` for
  `Demo()`, `core()`, `not()`, `rig()`, `route()` — prose words, not code claims), and
  a middle ground of backticked-identifier-only claims scanned 13 and fired on 3, still
  false in every one of the three: `drf_spectacular/hooks.py:89-91` is cited for
  `StatusEnum`, which is data that code *produces* at line 91 and never spells, and
  `demo-backend/shop/models.py:87` is cited for `Order` by **lexical containment** —
  line 87 is a field inside `class Order`, so the citation is correct without the word
  appearing on it. A leg that fires on a correct citation is worse than no leg: it
  trains the reader to ignore the verdict. Same-line-only is the other half of the
  scope: prose that names the symbol on the *next wrapped line* would cross-attribute
  claims between the two citations sharing that line.
  Three pins, so the leg cannot be quietly vacuous (ELEVENTH law applied to itself):
  the population (literal `EXPECTED_CLAIMS` against the claims scanned — mismatch is
  **exit 2**, a regex that silently matched nothing would otherwise report a GREEN over
  zero work; it fired on THIS paragraph's own author the day it shipped, when adding the
  matching AGENTS.md *Releases* sentence moved the honest scan 7 → 8 and the literal had
  to follow, so a deliberate change is a two-place edit and an accidental one is a RED),
  a WITNESS (`REQUIRED_CLAIMS`: the `csv_twin_diff.py` + `run()` claim must
  still be scanned, keyed by path + symbol and never by the line number, because the
  number is the thing under test — control 1 proved why: keyed WITH the number, the
  leg reported "lost witness" on every wrong-target mutation and never reported the
  wrong target), and an exemption with a reverse bite at BOTH ends
  (the historical quote at `scripts/csv_twin_diff.py:109`, which THIS document and
  AGENTS.md *Releases* both cite as a PAST state, is exempt from the hits test — and
  RED if that token stops being scanned OR if the range starts carrying the symbol;
  the exemption is keyed by the citation TOKEN, not the file, because one file carries
  both the historical `:109` and the live `:248` claim, and exempting the path would
  exempt the witness too).
  Controls, eight, each restoring the tree byte-identical: a live `:248` drifted to
  `:110` → 1 naming the citation, the symbol and where the name really appears; the
  `run()` spelling deleted → **2** `7 symbol claim(s) … against a pinned population of
  8` (one claim fewer than the literal — the pin fires on a coverage loss, not on a
  correctness claim); the witness symbol swapped for one that IS in range (`cmd()`) →
  1 `lost its
  witness`; the historical quote rewritten to a live number in **both** documents that
  quote it → 1 `match no scanned
  claim` (rewriting only one of the two is correctly NOT that verdict — the other doc
  still uses the exemption, which is the second lesson of control 4: an exemption is
  per citation token, not per paragraph); the exemption re-keyed onto the live citation →
  1 `target exemption is stale` (and it named both historical citations as wrong-target
  in the SAME verdict, which is what the aggregated findings are for);
  the claim class broadened → **2** first (population) and 1 with 392 false reds once
  the pin was satisfied; a past-EOF citation → 1 from the BOUNDS leg, proving the shared
  resolver refactor did not blunt it.
  Four of those eight controls FAILED on the first version of this leg, and three of
  them were holes in the leg rather than in the test: the witness keyed WITH the line
  number reported "lost witness" instead of the wrong-target verdict it existed to
  report (control 1); an exemption that matched nothing stayed silent — rc 0 — because
  only the hits-side reverse bite was written (control 4); and an exempted historical
  claim counted as PROOF that the live witness claim was still present, so deleting the
  live pointer while a quote of the old number survived read GREEN (control 3, rc 0).
  The fourth failure was in the RIG, not the leg: control 5's mutation string went stale
  when the exemption's reason text was reworded, so the control silently ran against an
  unmutated tree and reported rc 0 — which is why every mutation in that driver now
  asserts its own target text before replacing it. All four also showed that raising on
  the first finding hides the rest, so the leg collects every finding into one
  verdict — a leg you have to run twice to read is a leg that lies about the second
  finding.

- **ELEVENTH harness law — a printed COUNT is not an EXPECTATION, and an artifact
  found by POSITION is not that artifact.** The brand twin went into the landing
  gate last segment, and the gap reported then ("count the POPULATION in the
  output, not just the success word") was attributed to the wrong cause, so this
  segment measured the harness instead of repeating the story. It never reads
  `app/brands/` at all — only `app/public/brand.css` and `app/public/brand.json`,
  which is why hiding `app/brands/default/brand.json` changed nothing: that verdict
  was honest about the inputs it actually had. The blind spots are real, but they
  were three other doors, each measured on this tree and each restored
  byte-identical:
  1. **A shrunken matrix still passed.** Deleting 7 of the 11 legal font sentinels
     answered `BYTE-IDENTICAL — 296 accepted brands`, rc 0. The deleted rows
     included the double-space case THIS document names as the one that caught a
     real divergence (SIXTH law: the percent-20 mutant diverged on 146 brands,
     exactly the multi-word ones). Coverage for a known past bug vanished and the
     harness called it green, because nothing pinned what the matrix owes.
  2. **A softened schema is invisible on any axis both writers render passively.**
     Loosening `RADIUS_RE` (`plugin/src/admincraft/branding.py:32`) to take unitless
     values and `12 pt` moved 3 brands from refused to accepted and answered
     `BYTE-IDENTICAL — 303 accepted brands`, rc 0. The font axis looked protected
     only by accident: `brandToCss()` sanitizes an exclamation mark away while
     `render_css()` does not, so that mutant tripped a true twin divergence rather
     than any schema leg. The refusal count moved 50 → 47 and nobody questioned it.
  3. **Position is not identity.** The shipped brand was read as the LAST item of
     the accepted set, which is only true while the server accepts it. Make
     `app/public/brand.json` illegal, match its bundle to it, and leg 4 passes while
     leg 5 compares the shipped brand's CSS against an unrelated random brand and
     prints `HANDOFF DIVERGENCE — … a visible re-theme flicker`: a confident verdict
     about a pair that was never the same brand. That is TENTH law's "a resolver
     that GUESSES files a confident verdict about the wrong file", arriving at my own
     harness from the identity side.
  THE FIX: every sentinel carries the verdict the server OWES it; the sentinel
  population is pinned twice — a literal AND the sum of the `VALID_*`/`BAD_*`
  lists, which must agree — so silent truncation is impossible and a deliberate
  change is a two-place edit; the shipped brand is found by equality against the
  accepted set or the leg refuses. A population mismatch is exit 2 (the harness
  does not understand its own matrix, so there is no verdict to report); a flipped
  pinned verdict is exit 1 RED naming the row, because a closed schema that stopped
  biting is a product regression, not a tooling gap.
  CONTROLS: 2 legal fonts deleted → rc 2 `the matrix disagrees with itself: 49
  sentinels in the literal, 47 derived`; 1 row dropped from the builder alone → rc 2
  `MATRIX TRUNCATED: 48 sentinels built against a literal of 49`; the radius
  mutant → rc 1 naming all three rows; an illegal shipped brand with a matched
  bundle → rc 1 `LEGAL BRAND REFUSED — SHIPPED app/public/brand.json` plus the
  server's own error string, and the invented flicker verdict is gone. The green run
  measures 350 candidates, 49/49 sentinels, 50/50 pinned verdicts matched, 302
  accepted / 48 refused — and the accepted count moved 300 → 302 purely because a
  legal font entered the random draw pool: `random.choice()` rejection depends on
  sequence length and re-consumes bits, so a whole seeded sample shifts. A count
  that can change for a reason like that is exactly why an expectation must be
  pinned per row and never by a number in the output.
  SEAT RULE for a merged harness: mapping its exit codes is not enough. Ask what it
  prints when half its matrix is gone AND what it prints when the promise it checks
  is weakened. If either answer is a success word, that leg proves nothing.
  A TWO-COPY COMPARE IS THE WEAKEST POPULATION PIN OF ALL. The same segment measured
  the two sibling twins, and both had the door the brand twin's story had described
  (wrongly): `csv_twin_diff.py` builds ONE matrix and feeds it to BOTH writers, so a
  truncated `SENTINELS` list cannot make them disagree — it only makes them agree over
  less. Deleting 5 sentinels (both line-breakers, `cr\rhere`, and the `=SUM`/`+cmd`/`-`
  guard leads — the cells `docs/csv-export.md` §2 credits with divergence #1 and #2)
  answered `BYTE-IDENTICAL — 3065 cells`, rc 0, against an honest 3070.
  `parity_table_diff.py` compares two COPIES of `FLOAT_PARITY`, so a row deleted from
  both still compares identical: dropping the `1e-7` row from both files answered
  `FLOAT_PARITY: 24 rows, identical values AND expectations`, rc 0, against an honest 25.
  Neither verdict was wrong about what it ran; both were silent about what stopped
  existing. THE FIX, in both: the population is pinned twice — a literal
  (`scripts/csv_twin_diff.py:103`, `scripts/parity_table_diff.py:86`) AND the lists /
  parsed rows it describes, which must agree — and the rows carrying a RECORDED
  divergence are pinned individually by identity. Floats are keyed by their IEEE-754
  bytes, never by equality or a dict, because `0.0 == -0.0` in Python would collapse
  negative zero into plain zero — the exact pair the table exists to distinguish; and
  one renderer (`scripts/csv_twin_diff.py:190` `cell_text()`) is shared by the builder
  and the check, so the check cannot re-implement the builder's spelling and then
  report its own drift as a truncation.
  A LINE COUNT IS NOT A ROW COUNT: the first attempt pinned `cells + 1 == CRLF lines`
  and went RED on the honest run — 3070 cells ride 3097 lines, because a quoted cell
  may contain CRLF. The coverage pin is therefore IDENTITY (column 0 is the row index
  the probe was handed, so the matrix's last index must appear as its own record), not
  arithmetic on the delimiter.
  CONTROLS, each restored byte-identical: 5 sentinels deleted → rc 2 `the matrix
  disagrees with itself: 43 sentinels in the literal, 38 built`; one NON-required
  sentinel deleted → rc 2 at 42-vs-43 (only the literal can see that one);
  `build_matrix` dropping a float while both lists stayed honest → rc 2 `MATRIX
  TRUNCATED: 3069 cells built against 3070 expected`; the `1e-7` row deleted from both
  copies → rc 2 (population first); `1e-7` SWAPPED for `1e-8` on both sides, 25 rows
  intact, coverage moved → rc 1 `COVERAGE LOST … python copy lost 1e-07 (…)` naming both
  copies — the case only a per-row identity catches; the formula guard dropped from both
  golden literals → rc 1 naming `'=HYPERLINK` in each.
  THE SAME VERDICT SPLIT AS THE BRAND TWIN: a coverage row that vanished is RED (the
  twins still agree, over less than the proof claims — a proof regression, not a tooling
  gap), while a matrix that no longer matches its own pin is `CANNOT RUN` (the harness
  does not understand its own input, so it has no verdict to give).
  THE LAW'S AUTHOR WAS THE LAST UNPINNED LEG, AND THIS SEGMENT MEASURED IT: the three
  twins gained population pins, but the PARENT gate that every merge replays —
  `scripts/landing_gate.py` — still graded its count legs on "a count was printed",
  while its own docstring promised each leg asserts "the count it is supposed to
  produce". Measured on the delivered tree, each control restored byte-identical:
  one 39-line pytest file removed (2 tests) answered `pytest 297 passed` and GATE
  GREEN, rc 0; one vitest file removed answered 411 tests over 30 files, rc 0. The
  merge gate was green over vanished coverage — the exact sentence this law exists to
  forbid, hidden in the file that enforces it, because a law written about harnesses
  is not automatically a law about the law's own file.
  THE FIX: `EXPECTED_PYTEST` / `EXPECTED_VITEST` / `EXPECTED_VITEST_FILES`
  (`scripts/landing_gate.py:67`) are literals, one shared grader
  (`scripts/landing_gate.py:158` `population()`), and a mismatch is RED that names the
  direction: SHRANK = coverage lost (restore the tests, or bump the literal in the
  same commit as a deliberate deletion); GREW = the pin is stale (bump it in the same
  commit as the added tests). Unlike the twins there is no CANNOT RUN tier here: the
  count is parsed from the runner's own summary, so any disagreement is a claim the
  tree is not making about itself, which is a verdict, not a launch failure.
  CONTROLS: honest run rc 0 at 299/416/31; deleted pytest file → rc 1 `SHRANK —
  coverage lost: printed 297, owes 299 (delta 2)`; a 1-test file ADDED → rc 1 `GREW —
  the pin is stale: printed 300, owes 299 (delta 1)`; deleted vitest file → rc 1
  `vitest tests: SHRANK … printed 411, owes 416`. The grew-direction control matters
  as much as the shrank one: a pin that only fires downward is a floor, and a floor
  still lets the cited counts in AGENTS.md and the CI header drift upward unmarked.
  THE SAME DOOR, ONE LEVEL UP — WHICH LEGS RUN. The counts are pinned; nothing pinned
  the ROSTER, so the file enforcing this law could pass a merge while silently not
  running one of the three checks AGENTS.md defines. Measured on the delivered tree
  before the fix, four mutations, each restored byte-identical, every one rc 0 / GATE
  GREEN: the `migrations` leg deleted from the roster (the gate ran two verdict legs);
  `parity-twin` deleted from TWINS (`--fe` compared two of the three pairs); a fourth
  `*_diff.py` harness written and never wired into the roster (silently not run); and
  the dep preflight moved BEHIND pytest — the leg whose only job is to stop a swallowed
  install from wearing pytest's exit 2 as a red tree. In all four the closing line still
  read "every leg above asserted its own output": true of the legs that ran, blind to
  the one that did not. Distrust that sentence in any harness whose population is a
  LIST rather than a number — a vanished leg never prints a count to argue with.
  THE FIX: the roster is pinned by ORDERED LABELS and checked before a single leg
  launches, so a drift REFUSES rather than running the survivors and printing green
  lines for a gate that is no longer the gate finalize replays. Identity, population
  AND order in one compare:
  graded by `pin_roster()` (`scripts/landing_gate.py:176`) against MERGE_ROSTER +
  FE_ROSTER (`scripts/landing_gate.py:86`). Two copies of one intent are the weakest
  pin there is — measured twice above — so the twin roster is ALSO cross-checked against
  a source that is not a copy, the `scripts/*_diff.py` files on disk, by
  `pin_twins()` (`scripts/landing_gate.py:213`) against the EXPECTED_TWINS literal
  (`scripts/landing_gate.py:92`).
  THE VERDICT SPLIT IS THE POINT, and it reverses the ruling two lines above on
  purpose: a COUNT mismatch is RED (the tree is not making the claim its own runner
  summary prints — a verdict about the work), a ROSTER mismatch is `CANNOT RUN` (this
  file is no longer the harness, so it has no opinion about the diff in front of it —
  a launch failure). Both answer the same question: who is lying, the tree or the tool?
  The refusal prints as the gate's own verdict, `CANNOT RUN [roster]`, never as
  "harness failure" — measured on the first cut of the fix, an uncaught pin exception
  reached `__main__`'s crash handler and a deliberate decision appeared as a broken
  rig, which invites a re-run of something that will not change (TWELFTH law).
  CONTROLS: honest run rc 0 (4 legs default, 8 under `--fe`, roster printed); each of
  the four mutations above → rc 2 naming MISSING migrations / TWINS lists 2, pins 3 /
  roster-vs-disk / ORDER changed, every time BEFORE a leg launched.
  THE LAST UNPINNED ROSTER WAS THE OTHER GATE'S. Both files above pin THEMSELVES. Neither
  ever asked whether the gate the MACHINE replays on every merge is the gate the SEAT
  runs, while AGENTS.md states they "run the same" — and the file that decides merges,
  `.github/scripts/gate.sh`, is three bare commands with no count pin and no roster pin.
  Measured with that file opened read-only: one 24-test file moved aside and it answered
  `275 passed` and `GATE: GREEN`, rc 0. A pin inside the seat's own file structurally
  cannot see that, because it pins the seat's own file; the roster the two gates share
  was prose on both sides.
  THE FIX: `scripts/gate_roster_diff.py` — the FOURTH twin, wired into FE_ROSTER as
  `gate-twin` — parses the commands gate.sh ACTUALLY EXECUTES and diffs them, in order,
  against `MERGE_COMMANDS` (`scripts/landing_gate.py:103`), which is no longer a
  description of the gate but its source: `leg_pytest()` at `scripts/landing_gate.py:233`
  and `leg_django()` at `scripts/landing_gate.py:256` read it, so
  seat behaviour, seat expectation and machine behaviour are ONE object instead of three
  claims that can each drift. Four doors, one verdict word `ROSTER-DIVERGENCE`: MISSING
  (a leg the seat advertises is not run by the merge gate), UNDECLARED (the merge gate
  runs a command no seat is told about — which includes a silently NARROWED one, because
  an argv change makes the command unrecognisable rather than quietly partial), ORDER
  changed, and FAILURE NOT CAPTURED (the leg still runs, but `|| FAIL=1` is gone, so its
  red can print and the gate still exit 0 — the same class as TWELFTH law's transport
  verdict, arriving from the shell side). The verdict split holds: a drift BETWEEN the two
  gates is RED (a real change in what work gets gated on), while a gate that parses to
  zero commands is `CANNOT RUN` (the parser lost the shape, so there is no verdict to
  report, and a harness that reads nothing must never report identity).
  THE CONTROL THAT CHANGED THE CODE: the first cut defaulted `captured = True`, so the
  version written to close door 4 could not see door 4 — deleting `|| FAIL=1` from the
  check leg answered `ROSTER-IDENTICAL — 3/3`, rc 0. The mutation was run BEFORE the
  claim, caught it, and the default flipped to False with a comment naming the reason.
  LEAD-OWNED BOUNDARY HELD: gate.sh was opened read-only for every single run; all six
  mutations went to COPIES under /tmp through the harness's own `--gate` flag, and the
  shipped file's md5 was verified unchanged (and `git status` clean) before and after.
  CONTROLS: honest run rc 0 (3/3 verdict legs, same order, each captured); the
  makemigrations command deleted → rc 1 `MISSING migrations`; `|| FAIL=1` dropped from
  check → rc 1 `FAILURE NOT CAPTURED … python manage.py check`; `-p no:cacheprovider`
  dropped → rc 1 naming MISSING pytest AND UNDECLARED (both doors at once, both
  reported — a leg that reports one door hides the rest); `plugin/tests` →
  `plugin/tests/unit` → the same pair; check and migrations swapped → rc 1 `ORDER
  changed`; an added `python -m ruff check plugin` → rc 1 `UNDECLARED 1`; an echo-only
  script → rc 2 `parsed to ZERO commands`. Parent gate, three self-checks: FE_ROSTER
  truncated → rc 2 `UNDECLARED gate-twin`; TWINS truncated → rc 2 `TWINS lists 3
  harness(es), EXPECTED_TWINS pins 4`; MERGE_COMMANDS missing `check` → rc 2 `internally
  inconsistent`. `--fe` now runs 9 legs.
  SEAT RULE, one file wider: a population pin only ever covers the file that holds it.
  When TWO files implement ONE contract, the pin that matters is the DIFF between them —
  and the side you do not own is exactly the side nobody measures.
  SEAT RULE, extending the law to its author: when you write a population law for a
  harness family, the next file to measure is the one that runs the family — and the
  population to pin there is BOTH the numbers its legs print and the roster of legs
  that prints them.
  THE LAST LINK WAS THE COPY A READER FOLLOWS — WHAT THE DOCS *SAY* THE SUITES HOLD.
  `population()` grades the runner's summary against a literal, and that literal's own
  comment says the numbers "are also quoted in AGENTS.md and the CI header". Nothing
  compared the quotes to the literals. Measured on this tree before the fix: the
  Commands line a reader copies was retyped to a different count and `release_readiness`
  answered GREEN, rc 0 — the pin, the runner and every narrative record stayed
  consistent with each other while the INSTRUCTION had moved. That is the failure this
  whole law is about, arriving from the doc side: a seat that adds tests and bumps the
  pin leaves a repo telling the next reader a suite size no gate owes, and a seat that
  edits the doc without the pin has re-numbered every report written from it.
  THE FIX: `leg_doc_counts()` (`scripts/release_readiness.py:686`) grades the docs' LIVE
  count claims against the pins, read from the gate's own source rather than re-spelled
  here — `gate_pins()` (`scripts/release_readiness.py:650`) parses each literal AND imports
  the module, and the two views must agree, because a pin that has become a computed
  value is a number a doc cannot honestly quote. Six doors, in two verdict words:
  a doc that states a different count than the pin is RED naming doc:line, the number,
  the number owed and the direction (doc stale / doc ahead); a live row whose number was
  DELETED is RED (the claim left the compare, which is coverage lost, exactly as in the
  twins); a count claim inside a graded section that the table does not read is RED
  (an instruction nobody grades is the drift this leg exists for); and an anchor that
  matches two lines, a section header that is duplicated, a table shorter than
  `EXPECTED_DOC_CLAIMS` (`scripts/release_readiness.py:173`), a kind that stopped being
  covered or a pin whose two views disagree is `CANNOT RUN` — the harness no longer
  knows what it is reading, so it has no verdict about the tree.
  WHY A CLOSED TABLE AND NOT A SCAN: "is this number a live instruction or a historical
  record?" cannot be answered by regex. The two docs hold a dozen honest past-tense
  counts (a state log's `75 pytest / 58 vitest`, a control record's `printed 297, owes
  299`, the dated `as measured` lines) and a heuristic that tried to sort them would
  fire on all of them — the TENTH law's ruling applies: a leg that fires on a correct
  sentence is worse than no leg. So the domain is STRUCTURAL, not semantic: everything
  inside `## Layout` and `## Commands` is an instruction and must be in the table
  (`DOC_LIVE_SECTIONS`, `scripts/release_readiness.py:177`), everything outside them is a
  record and is out of domain. That is also why the Lead-owned CI header is NOT here —
  `.github/workflows/build-all.yml:4` still advertises the pre-gate counts and is
  cited, not edited.
  CONTROLS, 12, each file restored byte-identical (md5 verified): honest run rc 0 over 8
  claims; doc retyped low → RED `says 300 vitest, the gate owes 416`; doc retyped high →
  RED `the doc is ahead`; the number deleted but the sentence kept → RED `states no
  vitest count`; a new `# 500 vitest` line added inside `## Commands` → RED naming the
  ungraded claim; the Layout row duplicated → CANNOT RUN `matched 2 line(s)`; a row
  deleted from the table → CANNOT RUN `lists 7 live claim(s), pins 8`; the pin rewritten
  as `250 + 49` → CANNOT RUN `does not assign EXPECTED_PYTEST as a plain integer
  literal`; a second assignment added below the literal → CANNOT RUN `reads 416 from the
  source text but 417 from the imported module`; the pin bumped alone → RED on the four
  doc rows, which is the proof the harness reads the LIVE pin and not a copy of it; both
  `vitest` rows retyped to `pytest` → CANNOT RUN `grades pytest but not vitest`; a second
  `## Commands` header → CANNOT RUN.
  SEAT RULE, one doc wider: a pin is not the end of the chain. Ask who else QUOTES the
  pinned number — the file a reader copies from is part of the contract, and the cheap
  way to keep it honest is a closed table of its live claims plus a domain defined by
  section, not by guessing which sentences are history.

- **TWELFTH harness law — a verdict leg that reads the TRANSPORT, not the VERDICT, is
  the EIGHTH law running backwards.** EIGHTH says `exit 0` alone never proved anything;
  this is the mirror hole, and it is what let a segment whose work landed green be
  reported as `result: BLOCKED (qoder+zai+minimax lanes all failed — check the harness)`.
  The lane dispatch at
  `.github/workflows/agent-team.yml:521` decides with a shell `if`, so it asks exactly
  one question — did the process exit 0? — and collapses three different outcomes into
  one: the agent finished, the agent was CUT OFF at its own turn cap mid-work, and the
  CLI never started (bad argv, missing token, no network). A capped run is a REAL result
  carried in the JSON the leg already produces and never parses: `subtype` and
  `is_error`. Measured on this box, five controls, zero product-code changes:
  1. `--max-turns 2` against a task needing four tool calls → **exit 1** with
     `subtype: error_max_turns`, `is_error: true`, `num_turns: 2`,
     `stop_reason: tool_use`. So the shell `if` calls it a lane FAILURE and falls
     THROUGH — control 3 is what "through" means here.
  2. The lane's exact argv (`--output-format json`, `--permission-mode bypassPermissions`,
     `--max-turns 100`) on a one-turn task → **exit 0**, valid JSON. This is the control
     that matters: it kills the tempting diagnosis. The CLI accepts camelCase
     `bypassPermissions` and tolerates `--max-turns` even though neither appears in
     `qoder --help`, so **the argv is not the bug** and an operator who greps `--help`,
     sees no `--max-turns`, and "fixes" it changes nothing.
  3. THE FALL-THROUGH IS NOT A FREE RETRY. `ZAI_API_KEY` and `OPENROUTER_API_KEY` are
     both non-empty in this seat's container (tested with `[ -z ]` — NAMES + has-it only,
     per SECRET LAW, values never read or echoed), so a false lane failure spends a SECOND
     run of the same brief against the SAME workspace on a DIFFERENT model, and then a
     third. Two bodies editing one tree in one segment is a corruption path, not a
     resilience path — and the verdict can still land on "all lanes failed". Anything that
     reads as a fallback must be proven to be one before it is trusted.
  4. The architecture hid the outcome from every consumer: the work committed, the chat
     report and board note for that segment say DONE, the landing gate is green, and the
     mirrored control-file result still reads BLOCKED with `stall=1`. A verdict that
     disagrees with all of its own evidence is a verdict nobody can act on — and a false
     BLOCKED is worse than a true one, because it sends the next rotation to debug a
     machine that is not broken while the real signal (the seat ran out of turns) is
     discarded.
  5. Same class, second victim: `/sessions-restore` mounted EMPTY this boot, although
     SESSION LAW says it carries the seat's previous session. Under the pinned HOME only
     the CURRENT session file exists — the prior segment's transcript never arrived — so
     "resume with context instead of starting cold" has not happened for this seat, and
     the boot install was swallowed again (`.github/workflows/agent-team.yml:509`), the
     NINTH consecutive cold boot reported here. The restore leg prints its own verdict
     (`.github/workflows/agent-team.yml:349`) and `exit 0`s on cold start, so the step is
     green whether or not context arrived — EIGHTH law's "assert your own output phrase"
     is missing exactly where a silent success is indistinguishable from a silent nothing.
  FIX, one line class (LEAD-owned, so reported not edited): the lane parses its own
  JSON — exit 0 with `is_error: false` → OK; exit 1 with `subtype: error_max_turns` → a
  DISTINCT verdict (`PARTIAL: seat ran out of turns; work may still be on the branch`)
  that must NOT fall through to another body; anything else → lane failure.
  Then either raise `--max-turns` or drop it, since the cap is what converted a long
  segment into a red verdict.
  RE-RUN IT (no product code, one cheap call, ~2 turns):
  `qoder -p "Call the Bash tool four separate times: echo one; echo two; echo three;
  echo four." --output-format json --permission-mode bypassPermissions --max-turns 2`
  → exit 1 and `{"subtype":"error_max_turns","is_error":true,"num_turns":2}`.
  WRITER RULE for every seat: **the exit code tells you the process ended; the payload
  tells you what happened.** A leg that collects a verdict must parse the verdict body,
  never the transport status — otherwise a run that was cut off and a run that never
  started are the same word in the log, and the next reader debugs the wrong machine.

- **THIRTEENTH harness law — a contract test is only coverage of the module the app
  IMPORTS, and nothing measured which module that was.** The shape (found 2026-10-22
  00:22Z, then fixed): a second `index.ts` under `app/src/lib/widgets/` re-implemented the
  FR-R008 widget contract — same glob dir, its own record shape, its own `widgetUnits` —
  and exactly one file imported it: the contract test. `Dashboard.svelte` imported
  `app/src/widgets/index.ts`.
  Mutating the SHIPPED registry to silently drop one built-in answered `8 passed`, rc 0,
  because the suite was grading the dead copy; and `dashboardMount.test.ts` could not see
  it either, since it compares the rendered grid against the same registry, so a lost
  widget shrinks the expectation and the DOM agrees with itself. That class is now a
  machine check: `python3 scripts/registry_roster_diff.py` pins WHICH files glob a
  contract dir (roster drift = CANNOT RUN — the harness no longer describes the tree),
  refuses one dir claimed by TWO registries (the twin door), requires each pinned dir to
  still hold its declared `meta` files (population), requires each registry to be imported
  by a product file outside `__tests__` AND outside its own drop-in dir (a file in
  `actions/` importing the actions registry for its type is self-reference, not a
  consumer), and requires a test to still glob a pinned dir — the declaration-level
  reference read that grades a registry against its inputs rather than against itself.
  CONTROLS, each one mutation on a copy under `/tmp` via `--src`, shipped tree read-only:
  honest rc 0 over 3 registries / 16 drop-ins; the dead twin restored → CANNOT RUN
  `UNDECLARED=['lib/widgets/index.ts']`; one pinned registry globbing ANOTHER pinned dir →
  RED `TWIN REGISTRY`; the only product importer repointed → RED `TEST-ONLY-MODULE
  widgets`; a widget file deleted → RED `POPULATION widgets … pinned floor is 8`; a 4th
  undeclared registry → CANNOT RUN; a pinned registry deleted → CANNOT RUN `MISSING`;
  `import.meta.glob` renamed away in the test → RED `REFERENCE GONE`; a registry glob
  retargeted off its pinned dir → CANNOT RUN `globs ['lib/__tests__'], not the pinned dir`;
  `EXPECTED_REGISTRIES` bumped alone → CANNOT RUN `disk=3 pins=4`; an empty `--src` →
  CANNOT RUN naming all three MISSING.
  WHAT IT DELIBERATELY DOES NOT COVER, so the next reader does not over-read it: the
  registry's runtime FILTER. A filesystem scan cannot see `widgets/index.ts` dropping a
  file that exists on disk — that is exactly what `widgets.test.ts`'s declaration-level
  check is for, which is why the REFERENCE door guards it from the other side. And a
  first control attempt answered rc 0 on a mutation that had NOT applied (a `sed` pattern
  whose `*` is a quantifier, not a literal): a control whose mutation is a no-op is a
  false green wearing a number. Every control above asserts the file actually changed
  before it is scored — same rule as EIGHTH law, aimed at the harness author.
  WIRED, 2026-10-22 01:10Z, and the wiring is the NAME: the harness shipped as
  `registry_roster_check.py` because the boot that wrote it had no `app/node_modules`,
  so its author could not measure an `--fe` leg. `landing_gate.py` cross-checks its
  twin roster against the `scripts/*_diff.py` glob, so renaming it to
  `registry_roster_diff.py` + `FE_ROSTER += registry-twin` + `EXPECTED_TWINS 4 → 5` +
  `TWINS += ("registry-twin", …, "REGISTRY ROSTER OK")` is what makes it a leg.
  CONTROLS — the delivered tree plus six mutations, each on a copy (a `/tmp` ROOT for
  the roster doors, `leg_twin()` called directly for the leg doors, so no shipped file
  was ever mutated): a ROSTER door answers CANNOT RUN rc 2 and fires before a single leg
  launches; a LEG door answers RED rc 1.
    * delivered tree: `--fe` = 10 legs, `registry-twin REGISTRY ROSTER OK — 3
      registries, 16 declared drop-ins`, GATE GREEN rc 0.
    * harness restored under its old (non-`_diff`) name → CANNOT RUN `the TWINS roster
      (…) is not the set of twin harnesses on disk` — a roster naming a leg that
      cannot be launched.
    * an extra `*_diff.py` dropped beside it, never added to the roster → CANNOT RUN
      the same line, disk side now longer: an unwired harness is a comparison nobody
      runs. THE SAME MESSAGE IN BOTH DIRECTIONS IS THE POINT — the roster and the
      filesystem are two independent views of one intent.
    * `EXPECTED_TWINS` back to 4 alone → CANNOT RUN `TWINS lists 5 harness(es),
      EXPECTED_TWINS pins 4`.
    * `TWINS` label renamed away from `FE_ROSTER` → CANNOT RUN (the label door fires
      too, not only the script-name door).
    * the leg's probe repointed at a phrase the harness never prints → RED `registry-twin
      rc 0 but printed no REGISTRY ROSTER-OK verdict line — exit 0 alone never proved
      the compare happened`, with the real verdict quoted back.
    * a drop-in deleted in a COPY of `app/src` → RED `registry-twin
      (registry_roster_diff.py) rc 1 — the twins DIVERGE: RED — POPULATION widgets:
      …pinned floor is 8`, i.e. a real contract break reaches the gate as a named
      missing file, not as a shrunk suite count.
  It stays OUT of the MERGE roster on purpose: gate.sh is Lead-owned and
  `gate_roster_diff.py` grades it leg-by-leg, so a fourth merge leg here would only
  register as machine-gate drift.
  SEAT RULE: for every module your suite names, `grep` its importers and count the
  NON-test ones. Zero means your contract test is a memo about a file nobody runs; two
  modules claiming one directory means one of them is a second fixture.
- Pages (FR-R006) follow the widget drop-in law: one `.svelte` in
  `app/src/pages/` exporting `meta{title,path,nav,icon,order,standalone}` from
  `<script module>` (runes are unavailable there — the export must be static).
  `app/src/lib/pages/index.ts` globs eagerly, validates, and hands
  `lib/router.ts` its route table via `setPages()` — the router owns NO table,
  the shell imports NO page, the sidebar types NO entry, so adding a module
  touches one file. A declaration that cannot be honoured is **refused** into
  `refusedPages` with a nameable reason (bad pattern, nav entry on a
  param-carrying path, overlapping path, no default export) and the Modules
  page renders the refusal list, so a broken drop-in is visible rather than
  silent; a file with no `meta` at all is merely ignored. Matching prefers
  **fewest captures** (a static `/legacy` beats a sibling `/:id`) and an
  unanswered hash resolves to `kind: "none"` — the router never guesses a page
  from a prefix, same law as `actionPath()` and `resolveAxis()`. Captured
  segments arrive as **props**, so pattern parameter names are the component's
  prop names (`ModelPage` takes `modelId`/`recordId`, not `id`). Contract +
  the copy checklist in `docs/page-registration.md`.
- Vite: `optimizeDeps.include` covers all svelte entrypoints (prevents two
  svelte-internals instances); the dev server sends
  `Cache-Control: no-store`. Vitest additionally needs `resolve.conditions:
  ["browser"]` + `test.server.deps.inline: [/svelte/]`: without the browser
  condition Vitest resolves svelte's SSR build, where `mount()` throws
  `lifecycle_function_unavailable` — that one condition, not a Svelte 5 limit,
  was the "component tests are impossible" finding, and `shell.test.ts` is the
  proof. Under happy-dom a test must dispatch `hashchange` itself inside
  `flushSync()` (it assigns `location.hash` but never fires the event) and
  tear down with `unmount(instance)`, or a stale `<main>` reads as a routing bug.
- Runtime branding flow: the client boots with the bundled static brand
  (`public/brand.{css,json}` — first paint, no FOUC), then `initApp()`
  tries `GET <api>/admincraft/branding/`; a server brand replaces the
  static one, and `applyBrand()` fans it out (store + `document.title` +
  favicon + `injectBrandCss()` writing a `<style id="brand-runtime">`
  with the same `--brand-*` variables + Tauri `setTitle`). `brandToCss()`
  mirrors `branding.render_css()` output — keep them in sync. Plain DRF
  backends without the plugin degrade silently to the static brand.
  The editor page itself is pinned at the wire, not by unit-testing its
  builders: `app/src/lib/__tests__/brandingMount.test.ts` mounts
  `pages/Branding.svelte` and asserts the PUT actually goes to
  `<apiUrl>/admincraft/branding/` with the staff token and a trimmed body,
  that a 400 `detail.errors` list renders verbatim while the live theme stays
  untouched, that an already-uploaded asset travels as its stored RELATIVE
  path (no re-fetch, no re-encode; `assets/logo.svg` keeps its directory)
  while a bundled `/logo.svg` is re-uploaded as a data
  URL so the shipped logo survives the first save, and that an empty app name
  is refused with zero requests. Typing re-themes live and unmount reverts —
  the DOM half of the "visual verification of live preview" line on
  COOL-PREVIEW. Four mutants (client guard, defaults fill-in, verbatim errors,
  filename branch) each failed one named test.
- Brand assets keep their RELATIVE path across all three layers — one twin
  contract, like `brandToCss`/`render_css`. Every shipped `brand.json`
  (`app/brands/*/`) stores `"logo": "assets/logo.svg"`; `build_admin` flattens
  it into `public/`, so the runtime store must not: `brandstore._public()`
  feeds the WHOLE relative path to `_asset_url()`, and the route is
  `branding/asset/<path:name>` (NOT `<str:name>`, which cannot match a "/" —
  `reverse()` then raised `NoReverseMatch`, `_asset_url`'s broad
  `except Exception` swallowed it, the fallback URL 404'd at the router and
  the editor round-tripped to a bare basename that failed the NEXT save with
  "file not found in brand dir"). Silent broken logo, then a 400 on a brand
  the user never touched. `pages/Branding.svelte` mirrors the prefix as
  `ASSET_PATH_PREFIX` — change the mount and you change both. On the refusal
  side the two layers are pinned SEPARATELY on purpose (a status-code-only
  assertion cannot tell which one fired): `views.brand_asset`'s shape guard
  answers `bad asset name` for `.`/`..`/empty-segment/absolute/backslash
  names, while `brandstore.asset_path()`'s jail (realpath + commonpath) is
  the authority for a well-shaped name that resolves out — a symlinked asset,
  and the embedded-NUL `ValueError` that the view must convert instead of
  500ing. Mutants m1–m6 (flatten, `<str:name>`, `except KeyError`, basename
  slice, weakened guard, un-jailed path) each died on its own named test; the
  guard-rotation mutant survives every status assertion, which is why the
  message is pinned too.
- Brand writes are staff-only (DRF token auth) and validated server-side
  by the SAME closed schema as `build_admin` (`brandstore.save_brand`);
  uploads must be data URLs (png/jpeg/svg, magic-byte checked, 1 MB cap).
  `rev` (mtime+1) advances on every save so clients can poll for remote
  rebrands.

## CI — build-all, live

`.github/workflows/build-all.yml` is the E2 pipeline: the `test-gate` job
(vitest 416 + pytest 299 as measured 2026-10-21 — the workflow header comment
at `.github/workflows/build-all.yml:4` still quotes 58/114 and is Lead-owned, so
it is cited rather than edited; plus a CSP-hygiene check on the shipped
tauri.conf.json) runs FIRST and every build leg `needs:` it, so a
red tree spends zero build minutes. Legs: web / windows (.exe) / linux
(.AppImage) / android (.apk — universal `arm64-v8a`+`armeabi-v7a`, built
with `--target aarch64 --target armv7` (repeated flags, NOT a comma
list), signed by the committed
`app/src-tauri/signing/debug.keystore` so every run's apk signature is
identical and new builds install over old ones) / nix / guix, each uploading test-only
artifacts a user launches and registers their own DRF API against on the
login screen — nothing bundled, nothing calls home. Triggers: push +
pull_request on `ai/main`, `workflow_dispatch` from any branch, and `v*`
tag pushes (which additionally run the `release` job — see *Releases*).
Per the GitHub docs, `branches:` + `tags:` under one `push:` filter is
OR semantics, so plain ai/main pushes are unaffected. Paid minutes on
this private repo — use sparing, and put `[skip ci]` on doc-only pushes
to ai/main that don't need artifacts. The old `build-demo.yml.disabled`
stays parked (its legs were reused for build-all).
`app/src-tauri/Cargo.lock` is committed — regenerate it whenever
`Cargo.toml` changes (the nix `cargoLock` and guix vendor builds depend
on it).

## Releases

Push an annotated `vX.Y.Z` tag on `ai/main` (bump the version in ALL FOUR
carriers first — `plugin/pyproject.toml`, `app/package.json`,
`app/src-tauri/tauri.conf.json` (drives the apk `versionCode`), and
`app/src-tauri/Cargo.toml` + its lock entry in `Cargo.lock` — the tag
should match them). The pipeline runs on the tag and the `release` job cuts the
GitHub Release from that run's artifacts plus the plugin wheel/sdist,
with a `SHA256SUMS.txt`. Asset names and assembly rules mirror v0.1.0
exactly. The assembly rules live ONLY in the workflow's `release` job
(`.github/workflows/build-all.yml:417-443`); the hand-cut script v0.1.0 was
assembled with (`scripts/cut_v010_release.sh`, still cited in that job's comments)
was never committed — measured with `git rev-list --all --objects`, so the
workflow is the reference, not a script beside it. Re-runnable check: `python3
scripts/release_readiness.py` diffs the four carriers + the Cargo.lock entry,
compares them against a `vX.Y.Z` tag pointing at HEAD (or `--expect X.Y.Z`),
and refuses any doc citation of a path that does not exist AND any `file:line`
citation whose number is past the end of that file — a path check cannot see the
second half of the claim. It also grades the suite counts these docs publish as
INSTRUCTIONS: everything inside `## Layout` and `## Commands` must equal the pin
`scripts/landing_gate.py` enforces, read from that file's source and its imported value,
while counts elsewhere in the docs stay out of domain — they are records of a measured
moment, not promises to a reader (ELEVENTH law, the last link). A bare hooks.py:50 citation is never guessed at, so
write the directory or the citation stays unverifiable (only the Lead-owned
workflow still
carries that stale citation, so it is cited, not edited).
Only the `release` job
holds `contents:write`, and it uses the built-in `GITHUB_TOKEN` — no
PATs in CI. If a tag push ever fails to trigger, the manual fallback:
dispatch a run on the tag's commit, download its artifacts, and re-run
the assembly steps from the release job. Release assets are permanent;
run artifacts expire after 14 days.

## Android apk — install rules (learned from v0.1.0)

v0.1.0's apk failed to install on phones with "App not installed": it
was `arm64-v8a`-only (32-bit phones reject it) and every CI run minted
a fresh ephemeral debug keystore (Android refuses to update an app
whose signature changed). Since v0.1.1 the apk is universal
(`aarch64,armv7` targets) and signed with the committed stable debug
key. Sideload rules: Android 7.0+ (minSdk 24), 64- or 32-bit, install
from the **release** asset (run-page artifacts download as a zip —
extract first), and devices that had the v0.1.0 apk must uninstall it
once (one-time signature change from the stable key).

## State as of 2026-10-17 (after the branding-flexibility pass)

- **Neutral default brand landed**: `app/brands/default/` ("Admincraft",
  neutral grid-mark logo + regenerated full icon set via `npx tauri icon`).
  `tauri.conf.json` productName/window title no longer say "Freshorama
  Admin" — release builds ship generic, users brand on top. freshorama +
  minimal-light remain as examples only.
- **Runtime branding API + in-app editor landed** (75 pytest / 58 vitest,
  both suites extended test-first): `plugin` gained
  `brandstore.py`/`views.py`/`urls.py` (GET public, PUT staff-token,
  closed schema, magic-byte-checked data-URL uploads ≤ 1 MB, jailed
  writes, `rev` counter); demo-backend mounts `/admincraft/` and points
  `ADMINCRAFT_BRAND_DIR` at a gitignored runtime dir. Client: brand store
  fetch on boot with silent fallback, `applyBrand()` live re-theme
  (CSS vars + titles + favicon + Tauri window title via the new
  `core:window:allow-set-title` capability), and the `#/branding` editor
  page with live preview + server-error rendering.
- **CSP widened deliberately** (was dev-only localhost policy): the
  product's promise is "point the client at ANY DRF API", so
  `connect-src`/`img-src` now allow any http/https origin and
  `style-src`/`font-src` allow Google Fonts for branded fonts;
  `script-src 'self'` unchanged. Documented tradeoff: script execution
  stays locked down, network egress does not. (Superseded on `ai/csp-1`: the
  shipped conf now carries the *production* policy — see the csp-1 bullet —
  so the any-origin egress survives only in web/dev mode.)
- **`skills/` shipped**: `admincraft-onboard` + `admincraft-craft`
  (duplicated stdlib engine scripts by design — `inspect_project.py`,
  `derive_brand.py` — ask/auto modes, references, evals). Verified live
  against demo-backend and a scratch client dir.
- v0.1.2 released 2026-10-17: first release carrying the neutral
  identity (see *Releases* for the version-bump checklist — all four
  carriers were bumped before tagging).
- Shipped on `ai/main` (default branch): plugin, thin client, demo backend,
  Nix + Guix packaging, README, AI-REVIEW. Every topic branch — `be-1`, `be-2`,
  `be-3`, `be-6`, `fe-1`…`fe-5`, `mvp-build` — is merged in and safe to prune;
  checked with `git merge-base --is-ancestor <tip> ai/main`, not assumed.
- Suites, both green at this HEAD: `pytest` 75/75, `vitest` 58/58. On this
  4 GB box run vitest capped:
  `NODE_OPTIONS=--max-old-space-size=1024 npx vitest run --maxWorkers=1`.
- Fixed & merged, P0→P1: `brand.json` closed schema + realpath/commonpath jail
  on all writes; demo-backend dev-only DEBUG/CORS startup warning (`DEMO_DEV=1`
  ack); `api.ts` secret redaction + credentials stripped from URLs; `chat.ts`
  SSE oversized-line cap (1 MB, skip+warn); `secrets.ts` one-time
  web-localStorage SECURITY warning; `RecordForm.buildPayload` omits empty
  non-nullable fields; `DataTable` nested `{#each}` keyed on `col.name`;
  widgets auto-imported via `import.meta.glob` (`meta{title,size}`).
- Fixed & merged, later the same day: `tauri.conf.json` CSP `null` → working
  **dev** policy (localhost/ws + inline styles, no wildcards; production policy
  still open). The widget registry lives at `app/src/widgets/index.ts` — the
  old `app/src/lib/widgets.ts` is gone. Vitest runs in `happy-dom` so
  `localStorage`/`location` exist in tests. The widgets test asserts the
  drop-in *contract* (valid meta, `widgetUnits`, built-ins by contains) instead
  of a pinned count or id list, so dropping in a 4th widget cannot break it.
- Demo-backend regression, fixed & merged: `demo-backend/shop/urls.py` was
  silently deleted by the `381bed3` package rename (rig died on the first
  request; 48/48 stayed green because nothing booted Django). Restored
  byte-identical, and `plugin/tests/test_demo_boot.py` is now the gate — it
  boots the real `core.settings` in a subprocess, runs Django's system checks,
  and resolves `api/auth/token/`, the `shop.urls` router routes and
  `/api/schema/`. Needs no database.
- Fixed & pushed to `ai/csp-1` (rebased on `ai/main`, not yet merged): the
  **production CSP policy** item is closed. `tauri.conf.json` ships
  self-only script/media/worker + connect-src 'self' https://API_HOST — a
  placeholder, no localhost, no wildcards. After BRE Finding 2 it also
  carries `img-src 'self' data: https:`, `font-src 'self'
  https://fonts.googleapis.com https://fonts.gstatic.com` and
  `https://fonts.googleapis.com` under `style-src`: a brand.json webfont
  (@import is gated by style-src, the .woff2 files by font-src) and a
  hosted logo URL are product promises a self-only policy breaks silently,
  with no error. `build_admin --api-host <origin>` substitutes the deployed
  origin at deploy build time via `branding.normalize_api_host` (https only,
  dotted DNS, optional port; localhost/loopback, wildcards, paths, userinfo
  fail loudly; CSP drift fails loudly; same-origin re-runs are idempotent
  no-ops). pytest 114 / vitest 58, green; the CSP + API_HOST tests moved to
  `plugin/tests/test_branding_api.py`. CI test-gate gained a CSP-hygiene
  step that fails if localhost/http/ws/wildcards ever reappear in the shipped
  conf.
- **BLOCKED-ON-FOLLOW-UP on csp-1** (queued as `prod-CSP follow-through` in
  TODOS.org): a placeholder CSP also breaks the flow this file
  and the README advertise — a downloaded CI artifact (.exe/.AppImage/.apk)
  pointed at the user's own DRF API on the login screen cannot connect,
  because `connect-src` is 'self' + `https://API_HOST` until a build passes
  `--api-host`. Web mode is unaffected (no Tauri CSP). Needs either a
  runtime-set connect-src (same mechanism as live branding) or the artifact
  story changed, before this merges. SAME ROOT CAUSE, SECOND VICTIM: the
  committed CSP no longer carries the `http://localhost:*` + `ws://localhost:*`
  allowances `4a89fba` added, so `tauri dev` HMR is expected to break again
  (browser `npm run dev` is fine) — UNVERIFIED, proving it needs a Tauri
  build, which this box must not run. A dev-override config is the likely fix.
- v0.1.0 released 2026-10-17: tag on `f1678cd`, assets from green run
  39000890302 (wheel + sdist, NSIS exe, AppImage, aarch64 debug apk, web
  bundle, nix/guix store tarballs, SHA256SUMS). All six build legs are
  proven green in CI — the old "android/nix/guix unverified" caveat is
  closed.
- v0.1.1 released 2026-10-17, same day: the apk became universal
  (aarch64 + armv7) and stable-signed (committed debug keystore) after
  v0.1.0's apk hit "app not installed" on phones (aarch64-only ABI +
  ephemeral per-run signing key). First live fire of the automated
  `release` job (v0.1.0 was cut by hand).
- FR-R001 (ROADLOG R-001), on `ai/fr-r001-be`: demo-backend Order gained the
  reference lifecycle state machine — ordered Status enum + STATUS_ORDER +
  TRANSITIONS table (pending→paid→shipped, refunds from paid/shipped,
  refunded terminal), apply_transition() with typed IllegalTransition(reason),
  reserve/release stock shipped as # TODO(client) no-ops inside the
  transactional side-effect seam (_apply_side_effects), append-only
  OrderHistory (actor FK, creation entry via perform_create, seed_demo rows),
  and two router @actions: POST /api/orders/<id>/transition/ (guard failures
  = 409 + {reason}; unknown/missing target = 400 + {reason}) and
  GET /api/orders/<id>/history/ (oldest-first, deliberately not paginated —
  pagination_class=None so the OpenAPI schema matches the runtime shape).
  Additive only: status stays PATCH-writable (pre-existing MVP behavior).
  Client projects copy the pattern — contract + checklist in
  docs/order-lifecycle.md. +37 pytest (114 → 151) in
  plugin/tests/test_order_lifecycle.py: machine matrix, 409/400 shapes,
  trail order/actor, creation entry, seam invocation + rollback-on-failure,
  schema exposure. conftest now mounts the demo rig apps in-memory so the
  contract tests run in-process — still zero new deps (no pytest-django; the
  test DB comes from Django's own DiscoverRunner utilities).
- FR-R003 (ROADLOG R-003), on `ai/fr-r003-be` (stacked on `ai/fr-r001-be`):
  the custom-actions + audit reference — append-only `AuditEntry` (loose
  object_type/object_id targeting, no GFK; actor always server-derived,
  client-supplied actor ignored) whose append-only guarantee is structural:
  the ViewSet has List+Create mixins only, so list mutations answer 405 and
  the router never generates a detail route. Audit reads newest-first
  (triage) while R-001 history stays oldest-first (replay) — the ordering
  ruling recorded in the model and docs. Optional `?object_type=` /
  `?object_id=` filters back the record sub-view and the R-007 activity
  screen. Two audit-wired reference actions on Order: record-scope POST
  `/api/orders/<id>/flag/` and bulk-scope POST `/api/orders/bulk_flag/`
  (guard errors keep the R-001 400+{reason} shape; bulk writes one entry per
  order with provenance in data). Registry contract (FE meta + handler
  pairing) + copy-this-pattern checklist in docs/custom-actions.md.
  +24 pytest (151 → 175) in plugin/tests/test_audit_actions.py.
- Open, by priority: AI-REVIEW.org human P0 sign-off; web-mode secrets still in
  localStorage (accepted P2 — warned, not eliminated); icons are neutral
  generated grid marks — real product art still welcome; full skill eval
  loop (subagent runs + benchmark viewer) not yet executed — the scripts
  are functionally verified, the prompts in `evals/` are unrun. (Closed
  2026-10-17 on `ai/csp-1`: production CSP policy + build-time API_HOST
  substitution; the per-instance-CSP idea remains open.)

---
