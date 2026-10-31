# AGENTS.md — admineverywhere

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
`auditor` / `audit123` to see FR-R007 role gating actually hide something,
`manager` / `manager123` to see the same gate open on a real claim).

Product constraints — do not relax:

- AI chat is OpenAI-compatible only (OpenAI / Groq / Ollama / LM Studio /
  Mistral — one code path). No Anthropic. No tool calling, no provider
  abstraction, no history persistence (all v2 material).
- All visual identity comes from a single `brand.json` (colors, radius,
  font, logo). Components carry zero hard-coded colors: Tailwind 4
  `@theme inline` maps `--color-*` utilities onto the runtime `--brand-*`
  variables. **Release builds never carry a product name**: the shipped
  default brand is neutral (`app/brands/default/` = "Admineverywhere"), and
  every user's identity rides on top — either baked in via `build_admin`
  (launcher + bundled assets) or live via the runtime branding API
  (everything in-app: name, colors, font, logos, titles).
- Branding has TWO layers, never blur them: **runtime** (in-app editor
  `#/branding`, `GET/PUT /admineverywhere/branding/` — applies instantly, no
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
  `docs/widget-data.md` — and those six names are the fourth pinned contract of `doc_field_roster_diff.py`.
- Widgets are also USER DATA now (Owner order 2026-10-31): the Widget studio
  (`app/src/pages/WidgetStudio.svelte`, drop-in page contract) composes
  INSTANCES — a type from the discovered registry, custom title/size, a
  brand-ROLE accent (the card re-maps `--brand-primary` onto another brand
  var; no hard-coded colors), an optional FR-R008 `data` override validated
  by the feed engine's own `validateWidgetData` and rendered through the same
  schema-resolved feed, and an optional threshold rule (`above`/`below`/
  `change`) evaluated per tick with crossing dedup. Contract, persistence
  keys and notify semantics: `docs/widget-builder.md`. The eight fed built-ins
  accept an optional `data` prop (default = their own `meta.data`). The
  notification center (`app/src/lib/notifications.ts`; Notifications page +
  sidebar bell) is the ONE store every alert reads — capped at 50, persisted
  in `dad.notifications.v1`; OS toasts ride tauri-plugin-notification
  (best-effort, permission asked at runtime, browser mode = in-app only). The rendered half is graded too: `feedGridMount.test.ts` mounts the Dashboard grid against a live schema taking its widgets off the glob (not by import), so every fed widget must paint, a schema arriving after mount must wake it, and a feed nothing can serve must render its reason with no chart and no guessed URL.
- RBAC (FR-R007) is claims-driven and degrades silently: `normalizeOpenAPI`
  binds `schema.mePath` ONLY when the document carries `GET …/me/` and no
  POST (exportPath law again — never a guessed `/api/me/`), the client
  fetches claims with the schema and a failed/absent read leaves
  `claims = null` = NO filtering anywhere (plain DRF keeps the full menu).
  Optional `roles: [str]` on page meta and action meta gates the sidebar entry,
  the buttons and Modules' Open click via `roleAllows()` (`app/src/lib/rbac.ts`, pure);
  a bad roles declaration is refused like any other page problem; the hidden entry is
  wire-pinned by `rbacNavMount.test.ts` (stubbed registry) and by `rbac.test.ts` over the
  SHIPPED glob (which also pins that each nav group has a live gated page to lose). Hiding is UX,
  never security — the server re-validates everything, and the demo
  `/api/me/` (`core/views.py`) emits Django Group names as roles. Because a
  superuser short-circuits `roleAllows()`, `seed_demo` also creates TWO
  non-superusers each holding exactly one Group (`auditor` / `audit123`,
  who loses the managers-gated surfaces, and `manager` / `manager123`, who
  keeps them because of the claim, not the bypass) — a rig of superusers can
  prove acceptance only by bypass and never a hidden button. The
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
  exporting `meta{title,path,nav,icon,order,standalone,roles?}` from `<script module>`
  — the same glob contract, applied to routes: `app/src/lib/pages/index.ts`
  validates it, injects the router's route table and the sidebar entry. Router,
  shell and sidebar carry no page-specific line — and that half is now graded, not
  asserted: `app/src/lib/__tests__/navMount.test.ts` pins the rendered nav to the
  declared nav EXACTLY (a hand-typed button is as red as a missing one), routes
  every nav click through `pageHref()`, sends Sign out to the href of the page the
  registry marks standalone (`authPage`/`authHref()` in the registry — the login
  route was hand-typed in the sidebar until this harness fired on it), and scans
  every raw `.svelte`/`.ts` under `app/src/` for a hand-typed `#<declared path>`
  or a direct page import, with its own file/route pair count pinned so a
  collapsed domain cannot answer "no violations".
- The three drop-in registries (widgets, pages, actions) are ONE contract with THREE
  glob dirs, and the failure mode is a test that grades a module nobody imports:
  `python3 scripts/registry_roster_diff.py` pins which files glob, refuses one dir
  claimed twice, requires each pinned dir to still hold its declared `meta` files and
  each registry to have a non-test product importer. The FIELD NAMES it reads are the
  next claim up, graded by `doc_field_roster_diff.py`: the fifth and sixth FE twin legs of
  `landing_gate.py --fe` (see *Commands*); classes and controls: DEVGUIDE *THIRTEENTH + FOURTEENTH harness law*.
- Deliberately out of scope: virtual scrolling, command palette. (Notifications and user-built widgets LEFT this list on Owner order 2026-10-31 — see the instances bullet above.)

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
| `plugin/` | pip package `admineverywhere` — `branding.py`, `brandstore.py` (runtime store), `views.py`/`urls.py` (branding API), `build_admin`, `dump_schema` (334 pytest, written first) |
| `app/` | thin client — Vite 6 + Svelte 5 + Tailwind 4 + Tauri 2 (549 vitest) |
| `app/src/pages/` | drop-in pages (FR-R006): Dashboard, Modules, ModelPage, Branding, Login, Activity — one `.svelte` each exporting `meta{title,path,nav,icon,order,standalone,roles?}` from `<script module>`; registry `app/src/lib/pages/index.ts` globs them and injects the router's route table |
| `app/src/widgets/` | drop-in widgets: StatsCards, ActivityChart (SVG line), QuoteCard (30 curated Qur'an/Sunnah/Aslaf quotes; weakly-sourced ones marked "attributed") + FR-R008 `meta.data`-fed charts and tiles: TrendArea, StatusDonut, LeaderBars, HeatStrip, DeltaChip, LiveOrders (count, 15s engine poll), TodayRevenue (latest day-bucket over its window), CompletionGauge (leading choice's fraction) (engine: `app/src/lib/widgets/feed.ts`) |
| `app/src/actions/` | drop-in custom actions (FR-R003): flag.ts (record), bulk_flag.ts (bulk) — one `.ts` each exporting `meta{label,scope,model?,confirm?,input?,roles?,handler}`; registry `app/src/lib/actions/index.ts` |
| `app/brands/` | `default/` = the neutral shipped brand ("Admineverywhere", generated grid-mark icons) + two examples: `freshorama` (dark SaaS), `minimal-light` |
| `skills/` | the two agent skills: `admineverywhere-onboard` (wire an existing repo onto admineverywhere) + `admineverywhere-build` (guided or source-derived branding) — shared stdlib engine scripts, ask/auto modes |
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
cd app && npm test                          # 549 vitest
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 334 pytest

# FR-R005 cross-twin CSV byte diff (the two writers, one matrix, raw bytes)
python3 scripts/csv_twin_diff.py            # 0 identical / 1 divergence or coverage lost / 2 cannot run
                                            # no venv needed: layer 2 probes .venv/bin/python
                                            # then this interpreter; --python <exe> forces one

# brand CSS twin byte diff: render_css() ↔ brandToCss() ↔ shipped app/public/brand.css
python3 scripts/brand_twin_diff.py          # 0 identical / 1 divergence / 2 rig not runnable

# CSV shared-table diff: FLOAT_PARITY + the golden document literal, pytest side vs vitest side
python3 scripts/parity_table_diff.py        # 0 identical / 1 divergence or coverage lost / 2 cannot run

# MACHINE GATE vs SEAT GATE: .github/scripts/gate.sh (what finalize replays, Lead-owned
# and opened read-only here) diffed command-by-command against landing_gate's
# MERGE_COMMANDS — same legs, same order, same argv, each `|| FAIL=1` capture intact
python3 scripts/gate_roster_diff.py         # 0 identical / 1 divergence / 2 cannot run
python3 scripts/gate_roster_diff.py --gate /tmp/copy.sh   # controls run on copies

# the LANDING GATE itself (pytest + manage.py check + makemigrations --check),
# with a dep preflight so a swallowed boot-install failure is exit 2 not a false red
python3 scripts/landing_gate.py             # 0 green / 1 a leg is red / 2 cannot run
python3 scripts/landing_gate.py --fe        # plus vitest AND the six twin harnesses
                                            # (csv/brand/parity/gate-roster/registry-roster/
                                            # doc-roster — the first three need app/node_modules)

# the RELEASE story as a check (four version carriers + Cargo.lock entry vs a tag,
# doc-citation rot AND every cited line landing inside its file, the suite counts AND
# the control-roster counts the docs publish as instructions graded against the pins
# the harnesses themselves enforce, release inputs,
# no PEP 604 in any harness) — DEVGUIDE NINTH + TENTH + ELEVENTH laws
python3 scripts/release_readiness.py        # 0 coherent / 1 a leg is red / 2 cannot run
python3 scripts/release_readiness.py --expect 0.1.3   # what the NEXT tag must say

# the DROP-IN REGISTRIES as a check: which files glob a contract dir at all, whether ONE
# dir is globbed TWICE (the dead-twin shape — a second registry a test can keep green
# while the app imports the other), whether each pinned dir still holds its declared
# `meta` files, and whether any product file imports the registry the test asserts.
# Named `*_diff.py` because that glob IS the wiring: landing_gate's EXPECTED_TWINS
# cross-check refuses any harness on disk that its roster does not run, and vice versa.
python3 scripts/registry_roster_diff.py     # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/registry_roster_diff.py --src /tmp/copy   # controls run on copies

# THE DROP-IN CONTRACT FIELD LISTS as a check: every `meta{...}` field the two mirror
# docs promise against the fields the registries read (`PageMeta`, `ActionMeta`, the
# widget registry's own `mod.meta` reads) AND the nested FR-R008 feed block against
# `WidgetDataSpec` — plus coverage (a code field no doc list mentions), one-directional
# optionality (a doc `x?` the interface requires) and the AGENTS↔DEVGUIDE mirror.
python3 scripts/doc_field_roster_diff.py    # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/doc_field_roster_diff.py --root /tmp/copy   # controls run on copies

# the TEST-CHAIN objective's landed evidence, re-runnable in ONE command: the three
# scripted turns each landed as a commit on the main ref, the chat carries the FROM in
# every headline and a complete :PROPERTIES: drawer AND no drawer line floats free of a
# headline (a merge that folds two concurrent EOF appends eats the second entry's
# header and CHAT-FORMAT cannot see the orphaned tail), and — PER ENTRY, because a
# whole-file byte-prefix read fires on every union-merged concurrent append while
# nothing was touched — no entry inside the objective's window was edited, dropped or
# reordered (a landed entry whose bytes changed is red unless the repair is pinned in
# ACCEPTED_REPAIRS beside the chat line recording the ruling; a pinned repair matching
# nothing is CANNOT RUN), while over the whole history no entry vanishes or moves; the
# run log holds one well-formed line per turn (every run id resolving to a real commit)
# AND every run-shaped line in that log is one the harness actually reads (parse_log
# grades only a section named exactly `runs`; a record that fell outside it is
# LOG-COVERAGE red, never a silently lower count — the log re-opened that region twice
# and nothing measured the claim), and every parked board item is still a headline —
# an order cannot be restored over a deleted item.
python3 scripts/chain_test_check.py            # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/chain_test_check.py --selftest # 18 controls: every leg proved able to fail

# the chain's SESSION collect->restore loop (Owner order 2026-10-21 18:27Z) as a
# check, read-only against the Lead-owned turn script WHEREVER IT LIVES — the workflow
# inline, or the .github/scripts/turn_segment.sh the workflow runs since eaf34bd
# extracted the over-long block: every store the collect tar takes is restored to its
# OWN path, no lane opts out with --no-session, the goose session store is covered, the
# restore dir is mounted, and a script the chain does not run (or a second one competing
# with the first) is refused instead of silently graded — AND the duty reviewer's verdict
# really reaches the merger: the arm's write path and the extractor's read path name ONE
# file, the container mounts the host workspace under that path, and the extractor's own
# pattern is replayed against every verdict literal the reviewer brief demands (three
# review-missing runs 2026-10-24 recorded verdict=none while a reviewer lane was named)
# — AND the loop's workspace scratch is invisible to its own commit: the host commits
# with a bare `git add -A`, so every dot-path the carriers write into $PWD is derived
# from them, pinned by roster, and asked of git (ignored via `check-ignore --no-index`,
# untracked via `ls-files`). `.turn-sessions.tgz` is why this is not housekeeping — it
# holds the session stores BEFORE the host scrub step, and the guard's grep cannot read
# inside a gzip stream. Measured leaks of this same shape: `.turn-review.txt` (1a87144,
# 7a4623d) and `demo-backend/.coverage` (d819f6e, still TRACKED until 2026-10-25)
python3 scripts/chain_session_check.py        # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/chain_session_check.py --selftest # 19 controls: every leg proved able to fail

# the chat send-back's FIVE specced checks as ONE command — governance
# (CHARTER.md's MEMBER IDS reversal + its two rule headings), the color sweep of
# the three files the send-back touched, one panel / one importer / one mount,
# the LIVE prompt path (the panel really calls buildSchemaPrompt, the
# legend is still bound in chat.ts, and the wire-level proof that asserts the
# captured request body is still on disk) AND one prompt builder (exactly one
# product file writes the `name(fk->model)` prompt line and it is chat.ts — the
# legend-less clone in openapi.ts is what a future edit re-imports, so its
# existence is refused, not just its use). The item's verdict was prose-only;
# this makes it re-runnable, so a later edit cannot silently un-wire the panel
python3 scripts/chat_feature_check.py         # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/chat_feature_check.py --selftest # 12 controls: every leg proved able to fail

# IS THE QUEUED BRANCH REVIEWABLE, or is the next review lane about to grade state its
# author never wrote? On 2026-10-24 the chain spent NINE lanes on ai/turn-20261024-1632;
# the Lead's triage sorted them as 2 checker false-reds, 2 INHERITED folds, 1 lost
# transcript and 4 real authored defects. The inherited class is the one a seat can see for
# free: the branch's base predated the chat fold repair, so the branch TREE carried orphan
# drawer lines main had already fixed, and the duty brief grades "CHAT.org entries legal
# format" against that tree. This harness asks the same question of the WHOLE queue before a
# lane is paid: the register's pending branch is live, unmerged and at the parked sha
# (slot-live); main moved inside a region the branch also edited (stale-base); orphan drawer
# lines are attributed AUTHORED (the branch's own fold — rework) or INHERITED (main's stale
# state — rebase, precedent 950f71e); no harness-leak file in the tree and no Lead-owned
# file in the branch's delta (the standing reject classes); `git merge-tree` against main is
# conflict-free, because a conflict turns an APPROVED verdict into a manual Lead union-merge
# (the 0607 class) — AND, when it is conflict-free, the MERGED chat blob is scanned with
# chain_test_check's own `scan_orphan_drawers`, because `.gitattributes` gives the chat the
# `merge=union` driver and two appends that open with the same five header lines are read as
# common context and welded onto ONE headline. That fold lives in no tree either side
# carries: measured on ai/turn-20261024-1956 — merge base, branch tip and main all hold 0
# orphan drawer lines, the merge result holds 2 (`:WHEN:`/`:END:` at :9066-:9067, the
# `* MSG` headline and drawer header eaten) and `git merge-tree` answered rc 0, CONFLICT-FREE,
# which is why every branch-local check passed it and the Lead's finalize guard f3e0f63 only
# catches it AFTER the lane is spent. The merged read is tagged `MERGE-ONLY FOLD` and
# dispositioned INHERITED — rebase, never rework, because both entries are legal on their own
# bases. Read-only over git; it issues no verdict, writes nothing, and reads the Lead-owned
# register as data. Not `*_diff.py`: that glob IS the landing gate's twin roster, and this
# grades a branch against main, not an artifact against its twin
python3 scripts/review_preflight_check.py            # 0 queue reviewable / 1 a branch is not / 2 cannot run
python3 scripts/review_preflight_check.py --since 20261025  # one day's queue only
python3 scripts/review_preflight_check.py --selftest # 18 controls on real fixture repos: every leg proved able to fail

# the SEGREGATION-LAW pending slot as ONE command, read-only against the Lead-owned
# merger. The whole delivery loop hangs on one line of agent-team/CONTROL.org,
# and four separate times it was the reason nothing could land: an EMPTY slot could
# never bootstrap (the park keyed on approved, which needs a pending to exist), the
# merger compared a SEAT KEY against member ids, a timed-out segment step handed it an
# empty parse and it believed "no-pending", and a slot the Lead had just re-queued was
# blanked 20 seconds later by a write computed BEFORE its own `git reset --hard`. FOUR
# LEGS grade those promises (merger-reread, park-bootstrap, verdict-retain,
# blank-guard) and the merger's VERDICT ROSTER is closed before them: every literal
# `OUTCOME="<x>"` the workflow writes must be a verdict a leg knows — 4 park-excluded
# retain outcomes, `rejected` (retained by its own clause), 3 resolved. A verdict no
# leg has heard of is CANNOT RUN, never a quieter green: `lane-dead` arrived as exactly
# that ungraded fourth exclusion while the harness still pinned three
python3 scripts/chain_slot_check.py           # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/chain_slot_check.py --selftest # 11 controls: every leg proved able to fail
# the FR-R007-LIVE board row as ONE command (the proof that used to be a seat's
# hand-started rig described in prose): boot the real demo rig on a THROWAWAY db,
# discover the claims path from the LIVE document under the client's own GET-and-not-POST
# evidence law, authenticate both seeded logins plus the anonymous 401, assert their exact
# claim bodies, then feed those live bytes through the GLOBBED action registry and
# `roleAllows()` and grade the DIFFERENCE (the gated label survives for the caller who
# holds the role, vanishes for the one who does not, `claims = null` filters nothing),
# prove the audit actor is server-derived and that a re-seed does not drift the claims.
# What it cannot do is sit in a browser, so the pixel row stays a human pass.
python3 scripts/rbac_live_check.py            # 0 as published / 1 a claim is false / 2 cannot run (no rig, no app/node_modules)
python3 scripts/rbac_live_check.py --selftest # 11 controls: every leg proved able to fail

# THE SLOT READERS AS COMMANDS, NOT TEXT: chain_slot_check reads the merger's guard
# prose, so a guard that MENTIONS the key still passes while the grep IT RUNS cannot
# see the register line at all. This probe replays each shipped command — merger-reread,
# guard-curslot, guard-sed — against the live `#+PENDING-REVIEW:` line in THIS
# interpreter (GNU grep's ERE treats the escape `\#+` as "one-or-more hashes", which
# the single-hash register line never matches: agent-team.yml:1091 read always-empty and
# licensed the exact 27748d9 clobber the ed378d4 guard exists to refuse — carried as
# the handover docs/slot-dialect-fix.patch, one character, proven by this probe 2/3 ->
# 3/3 on a patched copy)
python3 scripts/slot_reader_probe.py          # 0 all readers find the slot / 1 a reader is blind / 2 cannot run

# THE THREE SLOT READERS OF ONE LINE, executed — the third door chain_slot_check
# cannot open. Its text legs MATCH patterns in .github/workflows/agent-team.yml; they
# cannot tell whether grep 3.11 treats `\#` as a literal `#` or as an escaped `#`. The
# merger's re-read and the guard's sed write shipped as two DIFFERENT dialects of the
# same pattern, and only the `^#\+` form finds the live `#+PENDING-REVIEW:` line — so
# CURSLOT is permanently empty, `[ -z "$CURSLOT" ]` admits every empty write, and the
# non-clobber guard that exists to protect a Lead advance silently hands the slot back
# (the 27748d9 and 10-bb clobbers). This harness runs each shipped reader against the
# shipped control file: today it answers RED, 2 of 3 readers matching, with the
# one-character repair named — the fix is Lead-owned machinery, the measurement is a
# command any seat can re-run.
python3 scripts/slot_reader_probe.py          # 0 all readers agree / 1 an inert reader / 2 cannot run

# THE HANDOVER PATCHES in docs/ as ONE command. A seat cannot edit the chain's own
# files, so a chain defect travels as `docs/<name>-fix.patch` plus the instruction to
# run it — and BOTH instructions in the tree had gone dead when this was measured: the
# session patch was cut against the workflow inline (the segment step moved to
# .github/scripts/turn_segment.sh, so `git apply --check` fails at its recorded offset
# while the header above it still says to apply it), and the slot patch proposes a
# guard the Lead has ALREADY landed, in reworded form. STATUS is therefore a contract,
# not a comment: a PROPOSAL must carry the APPLY line and must pass `git apply --check`
# against a target that still exists — and when it does not apply, the verdict names
# the other carrier that NOW holds the line the hunk removes ("the block moved"), which
# is the sentence that would have saved this repo two review cycles; a RETIRED must name
# `GRADED BY: <harness>`, must NOT keep an APPLY line, and is retired only while that
# harness exists and EXITS 0 — the landed law is measured by the harness that owns the
# file, never re-matched against the patch's own text, because the Lead rewords what it
# lands and firing on a re-wording that keeps the law is the false red this whole family
# exists to avoid.
python3 scripts/chain_patch_check.py        # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/chain_patch_check.py --selftest # every leg proved able to fail
# every `:WHEN:` timestamp the chain writes, as ONE command — over BOTH files that carry
# the drawer (CHAT.org and REVIEW-LOG.org): each `:PROPERTIES:` record owns EXACTLY
# ONE column-0 stamp, the stamp is the FORMAT LAW's inactive-timestamp shape
# `[YYYY-MM-DD Eee HH:MM UTC]`, its date is real, its clock is 00-23/00-59 and its day
# NAME is the weekday that date falls on. The weekday is read from a pinned English table,
# never `strftime("%a")`, because `%a` is locale-dependent. Baseline: 362 records, 362
# legal, rc 0 — and the leg fires on the defect that rejected ai/turn-20261024-1632 SEVEN
# times (four stamps reading `2026-10-24 Fri` on a Saturday, hand-found in a Lead sandbox
# every round because nothing in the family printed it)
python3 scripts/chat_when_check.py            # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/chat_when_check.py --selftest # 11 controls: every leg proved able to fail
# IS THE QUEUED BRANCH REVIEWABLE, or is the next lane about to grade state its author
# never wrote? On 2026-10-24 the chain spent NINE review lanes on ai/turn-20261024-1632;
# the Lead's triage sorted them as 2 checker false-reds, 2 INHERITED folds, 1 lost
# transcript and 4 real authored defects. The inherited class is the one a seat can see
# for free: the branch's base predated the chat fold repair, so the branch TREE carried
# the orphan drawer lines main had already fixed, and the duty brief grades "CHAT.org
# entries legal format" against that tree. This harness asks the same question of the
# whole queue BEFORE a lane is paid: the register's pending branch is live, unmerged and
# at the parked sha (slot-live); that same branch is not already SWALLOWED by a landing
# record on main (landed-echo — a squash landing keeps the branch's commits out of main's
# ancestry on purpose, so "unmerged" cannot see the 10-dp write-cross: run 40231536995
# re-registered 1946@93e0f45 seconds after the Lead landed that very sha and a review
# lane was dispatched over a CLOSED branch. The leg reads the repo's own convention — a
# commit whose SUBJECT opens with the landing verb and names the branch as its object —
# and orders the record against the branch tip, because a tip NEWER than the record is a
# post-landing re-delivery and stays queued, not flagged); main moved inside a region the
# branch also edited (stale-base); orphan drawer lines are attributed AUTHORED (the
# branch's own fold — rework) or INHERITED (main's stale state — rebase, precedent
# 950f71e); no harness-leak file in the tree and no Lead-owned file in the branch's delta
# (the standing reject classes); and `git merge-tree` against main is conflict-free,
# because a conflict turns an APPROVED verdict into a manual Lead union-merge (the 0607
# class). Measured on 2026-10-24 21:3xZ over the OBJECTIVE's 11 queued branches: 7 carry
# INHERITED chat-structure reds (2/2/4/4/4/4/6 orphans), 2 of those also conflict at merge
# — including the one pinned in #+PENDING-REVIEW — and 4 based after the repair are
# REVIEW-READY. Measured 2026-10-25 21:4xZ over the landed tree: the current slot
# (0320@edc827cc) carries NO landing record — genuinely queued — while two live refs are
# swallowed by one (0056, 1946), which the harness prints as retained evidence refs and
# never as queue work, because the Lead keeps those refs up BY RULING. Read-only over
# git; it issues no verdict, writes nothing, and reads the Lead-owned register as data.
# Not `*_diff.py`: that glob IS the landing gate's twin
# roster, and this grades a branch against main, not an artifact against its twin
python3 scripts/review_preflight_check.py            # 0 queue reviewable / 1 a branch is not / 2 cannot run
python3 scripts/review_preflight_check.py --since 20261024   # one day's queue only
python3 scripts/review_preflight_check.py --selftest  # 18 controls on real fixture repos: every leg able to fail
# THE REVIEW LANE ITSELF as a check, read-only against the Lead-owned chain: the
# verdict a branch lives or dies by is ONE token, spelled in three places nothing
# compared — the duty reviewer's BRIEF (which must instruct it as the last line of
# the answer), the host's EXTRACTOR (which must grep the same token from the same
# file the lanes redirect into, last match wins, host-side, because $GITHUB_OUTPUT
# never reaches the container) and the two carriers' reviewer MEMBER IDs (which must
# agree, or a real duty verdict is graded refused-wrong-reviewer forever). Measured
# cost of not having this: ai/turn-20261024-0659 got a full clean review from the QA
# lane and lost the token, so the merger wrote review-missing and the stall grew —
# and the lane accepted it because the CLI had silently substituted the pinned
# reviewer model, which no review-lane guard notices while every SEAT lane greps a
# dead-lane marker before calling itself OK
python3 scripts/review_verdict_check.py        # 0 ok / 1 a claim is false / 2 cannot run
python3 scripts/review_verdict_check.py --selftest # 15 controls: every leg proved able to fail

# THE CHECK FAMILY ITSELF, as a check. Every grader in scripts/ is run BY INSTRUCTION —
# measured: zero of them are invoked anywhere under .github/, so a seat or the Lead runs
# the one a mirror doc told them to run. The `*_diff.py` twins are population-pinned by
# landing_gate's EXPECTED_TWINS cross-check; the `*_check.py`/`*_probe.py` family was in
# NOBODY's domain until this harness, and the first run named two live holes: the slot
# reader probe landed with the 1552 merge cited by neither mirror doc (a RED finding
# invisible to anyone who did not already know the command existed) and the chat feature
# check was published in DEVGUIDE only as prose OUTSIDE its command table. Four legs: the
# grader roster on disk must equal a pinned roster by name AND count (a vanished harness
# is CANNOT RUN, never a smaller green); each must have a row inside `## Commands` of
# AGENTS.md AND docs/DEVGUIDE.md (the region is the domain — prose elsewhere does not
# tell a reader what to run); every `scripts/x.py --flag` a doc prints must be a flag that
# harness declares (the inverse hazard: a doc promising a mode that does not exist gets
# run and reported as tooling rot); and a doc instruction naming an absent file is
# CANNOT RUN, not a finding about a file.
python3 scripts/harness_roster_check.py      # 0 roster published / 1 an unpublished grader / 2 cannot run
python3 scripts/harness_roster_check.py --selftest # controls: every leg proved able to fail

# THE MERGE ITSELF, PREVIEWED BEFORE IT IS SPENT. review_preflight asks whether a LANE is
# worth paying; nothing asked what the MERGER produces once the verdict is APPROVED — and the
# answer is not "what was authored". `.gitattributes:1` declares `agent-team/CHAT.org
# merge=union` so concurrent EOF appends merge instead of stopping the chain, and the union
# driver writes a line ONCE when both sides add it identically, while the FORMAT LAW makes the
# first five lines of a same-seat report byte-identical (`* MSG <seat> -> @lead :report:`,
# `:PROPERTIES:`, `:FROM:`, `:TO:`, `:KIND:`). So the header folds, the body lands under another
# message's headline and merge-tree answers 0: the fold is SILENT in exactly the branches the
# merger accepts. Measured 2026-10-25 over the 27 unmerged refs: 20 lose at least one entry
# header in the predicted merge and 6 of those merge CLEAN (1736 / 2326 / 0320 / 0440 / 0607 /
# 0652) — a merger reading only merge-tree commits them blind. This harness prints the REPAIR
# instead of leaving it to be discovered mid-union: for every folded entry, the merged-file line
# to splice above (found by matching the surviving `:WHEN:` back to the branch's own entry) plus
# the verbatim header block; the conflicted paths, each classified append-only / code / doc /
# Lead-owned; and the pin arithmetic, because two sides bumping one `EXPECTED_*` literal is
# ADDITIVE — on the registered pending branch it prints EXPECTED_CONTROL_CLAIMS base 5 / main 10
# / branch 6 -> UNION 11, the same number the Lead's own merge note had derived by hand.
# THE FOLD HAS A SECOND SHAPE, and the 35th landing paid for it: the same dedup rule that
# eats the five header lines also eats ANY block both sides add identically — and every
# seat's report ends on the same SECRET LAW / SEGREGATION tail, so a concurrent append welds
# one landed entry's body to a neighbour's while BOTH headlines survive and the headline
# count and orphan-drawer scan stay clean (union 54d0d0c moved three bodies; Lead repair
# 570fb3e re-spliced them; the 19:16 ruling named the missing pre-merge read). The fifth leg
# grades it: every entry either side MOVED out of the merge base must appear in the merged
# tree with the same body bytes, with the splice/repair lines printed — exact by construction,
# because the chat blob this harness computes for 187eefb + 0f50d95 is byte-identical to the
# landed 54d0d0c (13,814 lines, `diff` empty), and replayed on those two parents it names the
# same three entries the ruling lists (83 -> 70, 20 -> 28, 111 -> 112 body lines). An entry
# with no `:WHEN:`, a refused headline, or one routing+timestamp carried TWICE steps out of
# the compare and is counted in the note, never graded against a guess.
# Read-only over git (merge-tree writes objects, not refs), issues no verdict, and imports
# chain_test_check's drawer grammar and review_preflight_check's queue/register reading rather
# than re-spelling either. Not `*_diff.py`: that glob IS the landing gate's twin roster, and
# this compares a branch's predicted merge against main, not an artifact against its twin
python3 scripts/chain_merge_check.py                    # 0 every target merges as authored / 1 a finding, with the repair printed / 2 cannot run
python3 scripts/chain_merge_check.py --all              # the whole unmerged queue, not just the register slot
python3 scripts/chain_merge_check.py --branch ai/turn-20261024-2244   # one target (ref name or commit sha)
python3 scripts/chain_merge_check.py --selftest          # 16 controls on real fixture repos: every leg able to fail
# THE TURN-REF POPULATION as a prune list, read-only over git. Every chain turn leaves a
# ref behind and origin/ carries 48 of them; the Lead prunes them by hand, one beat at a
# time, and the class a hand-read cannot see is a SQUASH landing — a ref whose payload
# shipped as main's bytes while its tip is NOT an ancestor of main. That is why
# ai/turn-20261025-1946 has been reviewed EIGHT times (seven
# 'approved+gate-conflict-branch-kept' verdicts and one ':rejected:') over content that
# has sat on main since ce4a67f. review_preflight_check asks whether a LANE is worth
# paying and drops every already-merged ref by design; its landed-echo leg reads the
# register's single slot only. Nothing asked the merge-adjacent question of the WHOLE
# population — does this ref hold anything main lacks? — so this harness dispositions all
# of them (MERGED / RECORD / CONTENT / KEEP), reusing the shipped landing-verb grammar and
# the shipped register reader by IMPORT rather than re-spelling them, and its coverage door
# refuses when its own ancestry split and the shipped queue split stop partitioning one
# set: a prune read over a silently smaller list is CANNOT RUN, never a shorter list
# (DEVGUIDE *ELEVENTH harness law*, arriving at the ref population). Three conservative
# refusals keep it honest — the ref the workspace's HEAD stands on is never named prunable
# (a freshly cut turn branch IS an ancestor of main, so the guard is the difference between
# a prune list and a self-delete command), and a removal, a file main does not carry or a
# binary delta lands as KEEP, because line-set containment cannot confirm what it cannot
# read. It names candidates and removes nothing: deletion is the Lead's prune law.
python3 scripts/ref_prune_check.py        # 0 no slot hazard / 1 the register parks a prunable ref / 2 cannot run
python3 scripts/ref_prune_check.py --since 20261026  # one day's refs only
python3 scripts/ref_prune_check.py --selftest # 16 controls on real fixture repos: every leg able to fail
# THE LANES' PROVIDER BUDGET as ONE command, read-only against the Lead-owned lane
# script: a lane is a command line, and nobody asked whether the brain it names can
# RECEIVE the request the repo itself builds. goose sends the repo's own AGENTS.md
# inside every call — measured 68878 bytes as 22895 tokens, and 22892 in the live
# workspace lane — while the rotated duty reviewer sits on a free tier whose input
# budget is 7000 and whose output budget (1000, against the 1932 goose's own
# compaction asked for) is also below one session. So that arm's FIRST call can never
# be answered here, never: the review-missing beats it produced were arithmetic, not
# load, and a branch with no verdict cannot land. The check derives the estimate from
# the bytes in front of it (trim the carrier and the verdict moves), grades the lane
# EACH ARM TRUSTS FIRST against the pinned budget table, refuses an ungradeable lane
# (no host, no model, no key NAME) as CANNOT RUN, pins the goose population by host so
# a deleted lane cannot shrink the compare, and refuses a review file that nothing reads
# for the provider's OWN rejection markers — because a session that dies mid-flight
# leaves its error text as the whole answer and the extractor only greps for a verdict
# token. `--probe` re-measures the receipts with one refused request per pinned host
# (nothing is billed: the provider rejects before it runs).
python3 scripts/lane_budget_check.py           # 0 every trusted lane fits / 1 a lane can never answer / 2 cannot run
python3 scripts/lane_budget_check.py --selftest # 6 controls: every leg proved able to fail
python3 scripts/lane_budget_check.py --root /tmp/copy   # controls run on copies

# THE HARNESS IMAGE RECIPE, PREVIEWED BEFORE A BUILD IS PAID. The image IS the turn
# lane: no image means no turn, no reviewer, no verdict, so review-missing and the stall
# grows. Between 13:51Z and 15:00Z on 2026-10-26 the chain paid FIVE build attempts (runs
# 40334271125, 40335134249, 40336007896, 40339371283, 40342641149) for two defects a text
# read answers before a single layer is built: `apt-get satisfy` was handed a HAND-LISTED
# dep set (run 40339371283 died exit 127 on `libdbus-1.so.3` — one of nineteen NEEDED
# libraries had been listed), and an `ENV` block sat BELOW the RUN it serves, which a
# Dockerfile never applies inside that RUN (run 40342641149: the in-RUN verify could not
# find its own character maps). Both are landed by Lead 10-fp — 85a1989 derives the deps
# from the pinned deb's own Depends, f039fdd hoists the ENV above the RUN — and the
# recipe is machinery a seat does not rewrite behind a running repair, so what the seat
# keeps is the measurement, read-only, that any seat can re-run (docker is not even
# installed in the container this runs in, so no leg can execute a layer). Six legs: the
# exec-time ENV reaches the RUN that verifies, the dep set is DERIVED and every relocated
# deb is excluded from it, each hand-written `/usr/local/bin` wrapper is chmod-ed AND
# exec'd inside its own step, nothing credential-shaped carries a literal VALUE (SECRET
# LAW: names travel, values do not), all seven agent bodies are still baked
# (lane_budget_check grades the LANE script; nothing graded the IMAGE), and every UNPINNED
# body install is ruled `strict` or `degrades` — the 10-ba BUILD LAW, measured on run
# 40117823054 where one flaky npm install of a DORMANT body bricked the image and killed
# the whole chain. Each leg prints how many inputs it read, and a leg that read zero is
# RED naming its own vacuity: coverage a harness does not have is never a quieter green
# (DEVGUIDE *ELEVENTH harness law*, arriving at the build).
python3 scripts/harness_image_check.py         # 0 recipe coherent / 1 a build would pay for it / 2 cannot run
python3 scripts/harness_image_check.py --selftest # 11 controls: every leg proved able to fail
python3 scripts/harness_image_check.py --root /tmp/copy   # controls run on copies

# mock OpenAI-compatible SSE provider (for chat E2E)
node scripts/mock_openai.js                 # listens on :11435

# rebrand the whole client in one command (build-time layer)
cd demo-backend && .venv/bin/python manage.py build_admin --brand ../app/brands/default/brand.json --app ../app

# regenerate launcher icons from a 1024px source (in app/)
npx tauri icon ../app/brands/default/assets/icon-1024.png

# derive a brand from any repo's own source (no logo needed)
python skills/admineverywhere-build/scripts/derive_brand.py --root <repo> --out <repo>/brand
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
  - A `blank=True`/`null=True` choices field arrives as a `oneOf` union of its
    enum component and `BlankEnum`/`NullEnum` (drf-spectacular
    `ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE`). The normalizer reads through
    oneOf/anyOf/allOf and treats the sentinels as the optional signal — never a
    choice — so such a field is a select, not free text. The rig ships the shape
    (`Product.packaging`) and `docs/independent-enums.md` §4 is the contract.
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
  `app/src/actions/` exporting `meta{label,scope,model?,confirm?,input?,roles?,handler}`
  — the registry globs it, nothing to edit. Endpoint URLs come from
  `actionPath(model, slug, recordId?)`, i.e. the schema-discovered
  `model.listPath`, NEVER from `apiUrl + model.id` (`apiUrl` is only the base
  origin; concatenating a bare segment produced `http://hostapi…` and silently
  broke the R-001 transition/history calls).
  The RENDERED half is wire-pinned too:
  `app/src/lib/__tests__/actionMount.test.ts` mounts the real page with the real
  globbed registry and asserts the dialog blocks an empty `meta.input`, the POST
  lands on the discovered `<listPath><id>/<slug>/`, a bulk selection posts the
  selected **ids**, a 400 guard `reason` surfaces verbatim, the table re-reads
  after a write (witnessed by a row the first page never carried), `meta.model`
  scopes the button away from other models and `meta.roles` hides the batch one.
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
  BOTH kinds of axis are declared in the reference app: `orders` through the
  machine, `products` on the rig's free enum `Product.packaging` `via: "patch"` —
  because `kanbanMount.test.ts` grades that half on the WIRE (the literal
  `{"packaging":"crate"}` body from both the select and a drag pair, the
  DISCOVERED detail path, zero `/transition/` probes, and no board at all when a
  customer schema does not carry the declared field). `kanban.test.ts` pins the
  registry's own population and grades EVERY declaration against the captured
  document, so an axis that rots or a model that vanishes is red rather than
  quietly untested.
- CSV export (FR-R005) keeps its two layers uncollapsed: DataTable "Export
  table" = visible columns of the CURRENT page, client-side, no server call;
  "Full export" = `GET <listPath>export/` line-level (child rows repeat parent
  ids, pk order, search honoured, `pagination_class=None`) and its button is
  bound **only when the schema documents it** — `normalizeOpenAPI` sets
  `model.exportPath` on `get && !post` at that path, and `fetchCsv` calls
  base + the discovered path, never `apiUrl + "export"`. Both layers are now
  **mounted**, not only unit-tested:
  `app/src/lib/__tests__/exportMount.test.ts` renders the real ModelPage against
  the captured fixture and grades the bytes of the intercepted download — layer 1's
  header is 1:1 with the table's own rendered `<th>` set (a field outside the
  visible slice cannot sneak in; an empty page downloads nothing but posts an info
  toast), the click fires ZERO requests, a document without the endpoint gets no
  "Full export" button and no probe of a guessed path, and the server's bytes are
  saved untouched (one BOM, never two) under a slugified Content-Disposition name.
  The wire-pin half is graded in the same battery by
  `app/src/lib/__tests__/csvMount.test.ts` — it mounts the real page, captures the
  download at `URL.createObjectURL` and proves both buttons exist only where the
  document proves them, that layer 1 sends ZERO requests over the table's own
  rendered columns, and that a renamed export endpoint moves the click with it
  (a hard-coded `apiUrl + "export"` fails that test by design).
  The writer twins
  (`app/src/lib/csv.ts` ↔ `demo-backend/shop/csv_export.py`) are
  byte-identical for the same rows — RFC 4180/CRLF/QUOTE_MINIMAL, null→empty,
  lowercase booleans, decimals never re-flowed, formula guard on text keyed by
  NUMERIC *shape* (DRF sends decimals as strings), BOM added once
  (`csvBlobParts` is BOM-idempotent) — keep them in sync like
  `brandToCss`/`render_css` (that pair gained its own one-command harness the
  same way: `scripts/brand_twin_diff.py`, DEVGUIDE *SIXTH harness law*); same
  commit, both sides, on pain of the two
  layers disagreeing on every negative price. The twins are held to one byte
  spec by a SHARED table: `FLOAT_PARITY` (a Python `float` renders with
  ECMAScript's `String()` form — `js_number_text()` — because layer 1 sees the
  JSON-parsed number, and the formula guard is keyed on
  `isinstance(value, str)`, never on the rendered text) appears with the same
  values and expectations in `plugin/tests/test_csv_export.py` and
  `app/src/lib/__tests__/csv.test.ts`, and the golden document carries a float
  column on both sides. That "same table" claim is itself now re-runnable, not
  prose: `python3 scripts/parity_table_diff.py` parses both files and diffs
  `FLOAT_PARITY` plus the golden byte string — floats keyed by their IEEE-754
  bytes, since the two languages' *renderings* are the thing under test and
  disagree on purpose (DEVGUIDE *SEVENTH harness law*). BOTH CSV harnesses also pin
  their own POPULATION, because a comparison cannot see its own coverage: the matrix
  feeds both writers, so a truncated `SENTINELS` list only makes them agree over less
  (measured pre-fix: 5 sentinels deleted, including both line-breakers and the `=SUM`
  guard lead, answered `BYTE-IDENTICAL — 3065 cells` rc 0), and a row deleted from BOTH
  `FLOAT_PARITY` copies still compares equal (measured pre-fix: the `1e-7` row gone from
  both answered `24 rows, identical` rc 0). So each harness carries a literal row/sentinel
  count that must agree with the lists/parsed rows it describes (mismatch = `CANNOT RUN`,
  the harness does not understand its input) AND the rows holding a recorded divergence
  pinned individually by identity (vanished = RED naming the row and the promise it
  carried) — floats by IEEE-754 bytes, never by equality, since `0.0 == -0.0` in Python
  cannot tell a matrix that kept negative zero from one that lost it. The golden
  document is pinned the same way, by required substrings (`…T21:00:00Z`, `'=HYPERLINK`,
  the quoted comma, the un-refloed `-5.00`) rather than by length, which any re-wrap
  legitimately moves. DEVGUIDE *ELEVENTH harness law*. The golden document ALSO doubles its datetime column
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
- Pages (FR-R006) follow the widget drop-in law: one `.svelte` in
  `app/src/pages/` exporting `meta{title,path,nav,icon,order,standalone,roles?}` from
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
  prop names (`ModelPage` takes `modelId`/`recordId`, not `id`). The auth gate is
  a rendered proof too: `app/src/lib/__tests__/authGateMount.test.ts` stubs the
  pages module so the discovered `standalonePages[0]` is a non-Login probe, mounts
  the real `App` and asserts that component paints (a hard `import Login` re-fork
  stays green — measured 451/35 — so the promise was graded by a comment, not the
  DOM), then empties the registry to pin the friendly no-standalone fallback the
  real glob can never reach. Contract +
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
  tries `GET <api>/admineverywhere/branding/`; a server brand replaces the
  static one, and `applyBrand()` fans it out (store + `document.title` +
  favicon + `injectBrandCss()` writing a `<style id="brand-runtime">`
  with the same `--brand-*` variables + Tauri `setTitle`). `brandToCss()`
  mirrors `branding.render_css()` output — keep them in sync, and the claim is
  now re-runnable rather than prose: `python3 scripts/brand_twin_diff.py` feeds
  every brand the server's own `validate_brand()` accepts through BOTH writers and
  diffs the declarations from the first `@import` (the two banner comments differ
  by design, so that region is the one thing the compare must not see — the same
  normalization hazard as the CSV twins, arriving from the opposite side: there a
  naive compare produced false divergences, here it would guarantee one). It then
  checks the shipped `app/public/brand.css` against `render_css` AND `brandToCss`
  of the `brand.json` beside it — a stale bundle, or a boot-time inject that
  differs from it, is the visible re-theme flicker the static bundle exists to
  prevent, and no per-side unit test can see either because each writer is green
  against its own fixture — and that shipped `brand.json` is looked up in the
  accepted set BY IDENTITY, never by position, because a positional read once
  compared it against an unrelated brand and reported the invented divergence as a
  re-theme flicker. A brand the server REFUSES is out of domain, not a
  divergence: the client sanitizes so a hand-edited bundle still paints. But the
  matrix's own population is pinned, not just printed: the sentinel count is
  asserted against a literal AND against the sum of the `VALID_*`/`BAD_*` lists,
  and each sentinel carries the verdict `validate_brand()` owes it, checked row by
  row — a printed count with no expectation attached passed rc 0 after 7 legal-font
  cases were deleted and again after the server's radius rule stopped refusing
  unitless values (DEVGUIDE *ELEVENTH harness law*). Plain DRF
  backends without the plugin degrade silently to the static brand.
- Brand writes are staff-only (DRF token auth) and validated server-side
  by the SAME closed schema as `build_admin` (`brandstore.save_brand`);
  uploads must be data URLs (png/jpeg/svg, magic-byte checked, 1 MB cap).
  `rev` (mtime+1) advances on every save so clients can poll for remote
  rebrands.

## CI — build-all, live

`.github/workflows/build-all.yml` is the E2 pipeline: the `test-gate` job
(vitest 416 + pytest 299 as measured 2026-10-21 — the workflow's own header
comment at `.github/workflows/build-all.yml:4` still quotes 58/114 and is
Lead-owned, so it is cited here rather than edited; plus a CSP-hygiene check on the shipped
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
second half of the claim — AND any citation whose line is inside the file but not
on the `name()` the prose beside it names (the third door: DEVGUIDE once cited
`scripts/csv_twin_diff.py:109` for `run()` while that line was the closing
triple-quote of `CLIENT_SPEC`, green the whole time). It refuses a fourth class, and it
is the class a reader FOLLOWS: a suite count published as an INSTRUCTION — every count
claim inside `## Layout` and `## Commands` of this file and of `docs/DEVGUIDE.md` — must
equal the pin `scripts/landing_gate.py` enforces, read from that file's source AND from
its imported value so this harness never re-spells the number. The pins' own comment
claimed those doc quotes track the literals; nothing measured the claim until a retyped
`npm test` line answered GREEN. Counts OUTSIDE those two sections are historical records
(a state log's suite size, a control run's printed-vs-owed pair) and stay out of domain,
by the same ruling that keeps the citation leg off correct prose — and so does the
Lead-owned CI header, which is cited here rather than graded or edited. The claim class is a same-line
`name()` spelling only, measured on the delivered tree (the pair moves with every doc
edit, so it is re-measured by the DEVGUIDE control rather than trusted as prose):
widening it to any identifier word on the line scanned 576 claims and fired on 425 of
them, and widening it to backticked
identifiers still fired on three genuinely correct ones (`StatusEnum` is data
`drf_spectacular/hooks.py:91`
produces, never spells; `demo-backend/shop/models.py:87` is cited for `Order` by
lexical containment). A leg that fires on a correct citation is worse than no leg.
A bare hooks.py:50 citation is never guessed at, so
write the directory or the citation stays unverifiable (only the Lead-owned workflow still
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

- **Neutral default brand landed**: `app/brands/default/` ("Admineverywhere",
  neutral grid-mark logo + regenerated full icon set via `npx tauri icon`).
  `tauri.conf.json` productName/window title no longer say "Freshorama
  Admin" — release builds ship generic, users brand on top. freshorama +
  minimal-light remain as examples only.
- **Runtime branding API + in-app editor landed** (75 pytest / 58 vitest,
  both suites extended test-first): `plugin` gained
  `brandstore.py`/`views.py`/`urls.py` (GET public, PUT staff-token,
  closed schema, magic-byte-checked data-URL uploads ≤ 1 MB, jailed
  writes, `rev` counter); demo-backend mounts `/admineverywhere/` and points
  `ADMINEVERYWHERE_BRAND_DIR` at a gitignored runtime dir. Client: brand store
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
- **`skills/` shipped**: `admineverywhere-onboard` + `admineverywhere-build`
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

# AGENT-TEAM CHAIN (added 2026-10-21, Lead) — the automated layer

This repo now ALSO runs the agent-team CI chain (`.github/workflows/
agent-team.yml`, ported from khaalidrafi/agent-team.el): `test` ->
`turn` (TG ingest owner-locked -> session restore -> one agent segment
in the preinstalled harness container -> session scrub+upload -> branch
push) -> `finalize` (auto-merge behind the landing gate -> stall
accounting -> self-dispatch while the objective is open).

Agent law (supersedes any conflicting instruction above for CI seats):

1. SINGLE CHAT: `agent-team/CHAT.org` — append-only, FORMAT LAW
   headline grammar (headline carries FROM; `:PROPERTIES:` drawer;
   Org inactive timestamps). Direct @pings, never mailbox relay.
2. CONTROL: `agent-team/CONTROL.org` is LEAD-OWNED — seats read and
   cite, never edit. Same for `.github/workflows/*`, `.github/scripts/*`,
   `.gitattributes`.
3. BOARD: `agent-team/TODOS.org` is the source of truth for
   work. Flip your item ONGOING at start; on delivery flip to PENDING
   with `:DELIVERED:` evidence (branch, sha, gate output). DONE is
   Lead-only.
4. SECRET LAW: credentials travel as ENV VAR NAMES only (e.g.
   QODER_PERSONAL_ACCESS_TOKEN). Never echo a value — a peer confirms
   the NAME + has-it/absent; you read the value from your own
   environment. `.github/scripts/secret-guard.sh` redacts leaks at
   every commit, ingest, and session artifact.
5. SESSION LAW: CLI session files are collected each turn, scrubbed,
   uploaded (`sessions-<seat>-*`, 30d), restored before your next
   segment — resume with context.
6. OWNER LOCK: the Telegram bridge records ONLY the Owner's chat
   (TELEGRAM_OWNER_ID secret); other chats are dropped — impersonation
   impossible.
7. LANDING GATE: `python -m pytest plugin/tests -p no:cacheprovider -q`
   (299 green as measured 2026-10-21; vitest 416) + `demo-backend manage.py check` +
   `makemigrations --check`. Red work never lands. `python3
   scripts/landing_gate.py` re-runs all three behind a dep preflight, so a swallowed
   `pip install -e plugin` failure reports `CANNOT RUN` with the fix command instead of
   wearing pytest's exit 2 as a red tree — and each leg asserts its own output phrase,
   because exit 0 alone never proved anything (DEVGUIDE *EIGHTH harness law*). A lane
   whose image has no setuptools cannot build that install at all, so since 2026-10-24
   the preflight probes the interpreter as-is and then once more with this checkout's
   `plugin/src` on PYTHONPATH, and the rig bootstraps the same way
   (`demo-backend/core/devpaths.py`) — so `pytest plugin/tests`, the two Django legs and
   the rig-booting subprocess tests answer for the branch in front of a reviewer
   instead of dying on the environment. The count
   legs are graded against pinned literals `EXPECTED_PYTEST`/`EXPECTED_VITEST`/
   `EXPECTED_VITEST_FILES` (`scripts/landing_gate.py:73`) — pre-fix the PARENT gate was
   green over vanished coverage (measured: `297 passed`, rc 0), the same hole the twins
   were fixed for — so when a suite legitimately changes, bump the literal in the SAME
   commit as the diff (DEVGUIDE *ELEVENTH harness law*, extended to its own author).
   The LEG ROSTER is pinned the same way, by ordered labels (`MERGE_ROSTER` +
   `FE_ROSTER`, `scripts/landing_gate.py:92`), checked before a single leg launches:
   pre-fix, deleting the `migrations` leg answered `GATE GREEN`, rc 0 — a vanished leg
   prints no count to argue with. A roster drift is `CANNOT RUN` (the harness is no
   longer this gate), never RED; the twin roster is cross-checked against the
   `scripts/*_diff.py` files on disk, not only against its own literal, so an unwired
   harness is a refusal too. `--fe` adds vitest plus all six twin harnesses
   (csv/brand/parity byte identity, the machine-gate roster, the drop-in registry
   roster and the doc field-list roster): the merge gate deliberately stays three legs,
   because `.github/scripts/
   gate.sh` is Lead-owned and `gate_roster_diff.py` grades it against `MERGE_COMMANDS`
   leg-by-leg — a fourth leg a seat adds here would only register as machine-gate
   drift (the registry twin needs no `app/node_modules` and still cannot join) — but a
   seat delivering work that touches a twin pair must run `--fe`, because per-side
   unit tests are green against their own fixture and therefore cannot see a
   divergence *between* the two. The fourth twin is the one a seat cannot see at
   all: `.github/scripts/gate.sh` (Lead-owned, what `finalize` actually replays) is
   diffed command-by-command against `MERGE_COMMANDS` (`scripts/landing_gate.py:109`),
   which the merge legs themselves now execute — so "the landing gate runs the same"
   is measured, not asserted. Drift is RED naming `MISSING` / `UNDECLARED` / `ORDER
   changed` / `FAILURE NOT CAPTURED` (a leg that runs but whose `|| FAIL=1` is gone can
   print a red and still exit 0); a gate parsing to zero commands is `CANNOT RUN`.
   `python3 scripts/gate_roster_diff.py` runs it alone, and gate.sh is only ever opened
   read-only — controls go to copies via its `--gate` flag. THE NUMBER ITSELF IS NOW
   GRADED WHERE A READER PICKS IT UP: `scripts/release_readiness.py` reads
   `EXPECTED_PYTEST`/`EXPECTED_VITEST` out of `scripts/landing_gate.py` (from its source
   AND from the imported module, so the harness never re-spells a count) and refuses any
   suite count published as an instruction inside `## Layout` / `## Commands` of
   `AGENTS.md` or `docs/DEVGUIDE.md` that differs from it — a pin bumped without its docs
   is RED, and so is a doc retyped without the pin (DEVGUIDE *ELEVENTH law*, last link;
   narrative counts elsewhere are dated records and out of domain, the Lead-owned CI
   header included).
8. SEAT (Owner law 17:47Z): bodies are chosen BY FIT and preinstalled
   in `docker/harness/` (Docker law). Rotation pointer lives in
   CONTROL.org `#+TURN`.

## Global agent law — DISTRIBUTED (Owner order 2026-10-21 03:53Z #hq:
## "don't forget to give global instructions' AGENTS.md to the team").
## Canonical source: khaalidrafi/agent-team.el AGENTS.md.

1. FORMAT LAW: CHAT.org messages are Org headlines carrying FROM,
   routing in tags, fields in a :PROPERTIES: drawer; append at EOF only.
2. TELEGRAM LAW: TG-bound messages open with FROM:/TO: lines.
3. SECRET LAW: credentials NEVER travel in chat/files/commits — only as
   ENV VAR NAMES. A peer replies with the NAME + has-it/absent; the asker
   reads the value from their OWN environment. SECRET GUARD
   (.github/scripts/secret-guard.sh) redacts at every choke point.
4. SESSION LAW: CLI session files collected at turn end, scrubbed,
   uploaded as sessions-<seat>-* artifacts (30d), restored next turn.
5. OWNER LOCK: the TG bridge ingests ONLY the Owner's chat.
6. DOCKER LAW: agents PREINSTALLED in docker/harness; keys env-injected.
7. SEAT BOUNDARIES: never edit .github/workflows/*, CONTROL.org,
   .gitattributes; never push to ai/main (finalize auto-merges).
8. BOARD DISCIPLINE: ONGOING at start, evidence in :LOGBOOK:, DONE is
   Lead-only.
9. IDENTITY: commit as your seat identity.
10. NO SPEND, no destructive actions; :escalation: @lead after 2 failed
    self-attempts.
