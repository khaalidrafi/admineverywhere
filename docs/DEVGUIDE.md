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
python3 scripts/csv_twin_diff.py            # 0 = identical, 1 = divergence, 2 = rig not runnable

# brand CSS twin byte diff — render_css() ↔ brandToCss() ↔ the shipped bundle
# (needs app/node_modules; the plugin is read from plugin/src, no venv required)
python3 scripts/brand_twin_diff.py          # 0 = identical, 1 = divergence, 2 = rig not runnable

# FR-R005 SHARED-TABLE diff — FLOAT_PARITY + the golden literal, pytest side vs vitest side
# (parses both files; needs `node`, but NOT node_modules and NOT the rig venv)
python3 scripts/parity_table_diff.py        # 0 = identical, 1 = divergence, 2 = cannot run

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
  `Promise<Page>` while `types.ts:92` declares `Page<T>` with no default, so
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
  from the **property name**, not the model (`hooks.py:67-95`), so two
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
  Both declaration-driven grids comply now: `Shell.svelte:53` (pages, FR-R006)
  and `Dashboard.svelte:22` (widgets, FR-R008). The widget grid had no DOM test
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
  every consumer test only ever *mocked* them (`RecordForm.test.ts:9-10`), so the
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
  the key field was empty, while `ChatPanel.svelte:33` hydrates that field from
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
  harnesses (`scripts/csv_twin_diff.py:109` `run()`,
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
  1. **Filter the matrix through the validator, then read the refusals.** "Both
     writers agree" only means something over the domain where both are
     contracted to run, so the script generates 350 brands and keeps the 300
     `validate_brand()` accepts. The refused 50 are counted, not dropped in
     silence. Surprises here are real: `"\tTabbed Font\t"` is ACCEPTED (the
     server matches `SAFE_FONT_RE` against `font.strip()`, `branding.py:190`) and
     the client strips the same tabs via `sanitizeFont()` — so a brand that looks
     invalid in the accepted column is not a divergence, and the only way to know
     was to run it.
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
     `bundle == render_css == brandToCss` for the shipped brand.
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
(vitest 58 + pytest 175, plus a CSP-hygiene check on the shipped
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
exactly (reference implementation: `scripts/cut_v010_release.sh`, which
cut v0.1.0 by hand from green run 39000890302). Only the `release` job
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
