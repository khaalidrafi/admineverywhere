# FR-R005 — Canonical CSV export: two layers, one byte format

Reference implementation: `demo-backend/shop/csv_export.py` + `OrderViewSet.export`
(`views.py`) on the server; `app/src/lib/csv.ts` + `DataTable` "Export table" +
`ModelPage` "Full export" on the client. Sibling convention docs:
`order-lifecycle.md` (R-001), `custom-actions.md` (R-003), `independent-enums.md` (R-002).

## 1. The two layers — never collapse them

| layer | source of rows | scope | dependency |
| --- | --- | --- | --- |
| **1 — table export** | what the browser already has | the CURRENT page only, the VISIBLE columns only | none — pure client, works offline, no server call |
| **2 — full export** | the server | the WHOLE collection, flattened line-level (child rows repeat parent ids) | a server `@action` the client binds a button to **only when the OpenAPI document carries it** |

Layer 1 answers "give me this screen as data"; layer 2 answers "give me the
dataset". They deliberately produce different shapes, but for the same rows
they produce **byte-identical CSV text** (§2) — so a user can diff a download
instead of guessing which layer lied.

## 2. The shared byte rules (both layers, kept in sync like `brandToCss` ↔ `render_css`)

- RFC 4180: quote a field only when it contains `,` `"` CR or LF
  (Python `QUOTE_MINIMAL`); embedded quotes double; every row ends `\r\n`,
  including the last.
- Data, not display: no `formatCell` truncation, no em-dash for nulls
  (null/None → **empty**), booleans → lowercase `true`/`false`, decimals stay
  exactly as the API sent them (a DecimalField's `"19.99"` is never
  re-flowed through `Number`).
- UTF-8 **BOM** on the document (Excel on Windows codepage-mangles a
  BOM-less file). The client's `csvBlobParts()` is BOM-idempotent: layer 2
  hands it a body the server already wrote BOM-first, and a second BOM shows
  up as a stray `ï»¿` in the first cell of every download.
- Formula injection is mitigated (OWASP CSV section): a **text** cell leading
  with `= + - @ TAB CR` gets a leading apostrophe. Real numbers are never
  touched — and because DRF serialises decimals as strings, both sides exempt
  a *numeric-shaped* string (`-5.00` is data; `-2+3` and `-IF(…)` are not).
  Same regex on both sides (`NUMERIC_SHAPED` in `csv.ts` and `csv_export.py`).

One carve-out Python has and `csv.ts` does not: `csv.writer` quotes a row
that is exactly one empty field so the line cannot collapse. No real export
row is single-column; if yours is, add the rule on both sides at once.

Floats are the value type that once disagreed by *type* rather than by shape,
and the server side now carries the rule: `csv_cell()` renders a Python `float`
with `js_number_text()`, i.e. exactly what ECMAScript's `String()` writes for
the same double. That matters because the two layers see a float differently —
layer 1 receives `JSON.parse`'d number and `String()`s it (`1.0` -> `1`,
`1e-07` -> `1e-7`), layer 2 formats it in Python (`str(1.0)` -> `1.0`), so a
client project with a `FloatField` got two buttons producing two files. Python's
shortest round-trip `repr` yields the same digits the spec would choose, so only
the presentation is re-laid out (integral floats, the `-6 < n <= 21` switch
points, unpadded exponents). `Decimal` is untouched: its own serial form is
data and must never be re-flowed (§5). The guard rides along: it is keyed on
`isinstance(value, str)`, never on the rendered text, because a negative float
in exponent form (`-1e-9`) is not numeric-shaped and would otherwise be
apostrophised server-side while the browser left it bare.

The byte-level pin is a shared table, not a claim: `FLOAT_PARITY` appears in
`plugin/tests/test_csv_export.py` and, with the same values and expectations,
in `app/src/lib/__tests__/csv.test.ts`, and the §5 golden document now carries a
`weight` column of `1.0`, `-0.5`, `1e-7`.

**Datetimes are the second divergence, and it is the same class.** A
`DateTimeField` crosses the wire as a STRING, so `csv.ts` has nothing to
format — it writes what it received. The server layer was re-rendering the
model value with `datetime.isoformat()`, which spells UTC `+00:00` where DRF's
own JSON spells it `Z`. Same instant, different bytes, on **every row of every
export with a datetime column** — which the whole float episode never touched,
because the golden document's `when` cell is a string on the JS side (a browser
only ever receives text) and a datetime object on the Python side, so the two
sides agreed by passing text through while the real rule went untested. The
server now mirrors DRF: `drf_datetime_text()` reads a naive value as
project-local, moves an aware one into the project timezone and writes UTC as
`Z` — the same three steps as `DateTimeField.to_representation`. Two
consequences for a client project:

- get the text from `django.utils.timezone`, never from a hard-coded UTC. DRF
  renders in the **project** timezone, so a project with `TIME_ZONE="Asia/Dhaka"`
  sends `+06:00` in its JSON and its writer must too. Pinning UTC is the same
  bug one setting over — `TestDatetimeOverTheWire` therefore runs its wire
  assertion under both `UTC` and `America/Chicago`.
- a project that overrides `REST_FRAMEWORK["DATETIME_FORMAT"]` overrides this
  rule as well: match the format there or the two layers stop being one byte
  format. A `DateField` is unaffected (no time part, no offset to re-spell).

Because those literal expectations depend on `settings.TIME_ZONE`, the suites
that assert literal bytes pin it (`utc_project_timezone` in
`test_csv_export.py`): `plugin/tests/conftest.py` configures Django without a
`TIME_ZONE`, so the ambient value is Django's own default `America/Chicago`
while the demo rig declares `UTC` (`core/settings.py:76`). An unpinned literal
there fails on the machine, not the code.

`ISO_PARITY` (same shape as `FLOAT_PARITY`) is the Python side of that rule and
the golden document now doubles the datetime column — one row an aware
`datetime`, one row the same instant as the text a browser receives — so a
regression in the rendering rule goes red on one side and names itself.

## 3. Server contract (layer 2)

- Route: `GET <model.listPath>export/` — a DRF `@action(detail=False,
  methods=["get"])`, so the router itself mints the path. That path is what
  lands in the OpenAPI document and what the client discovers (§4).
- **Honours `?search=`, ignores pagination** — a page of an export is not an
  export. Set `pagination_class=None` on the action: the default pagination
  would document a page-wrapper shape the CSV body never has (same ruling as
  R-001 history).
- Answers a plain `HttpResponse` (`content_type="text/csv; charset=utf-8"`,
  `Content-Disposition: attachment; filename="…"`), not a DRF `Response` —
  no renderer negotiation on the body. BUT include a `text/csv` renderer in
  `renderer_classes` (here: `CSVTextRenderer`): DRF negotiates the *error*
  path against Accept too, and a client asking for `text/csv` would 406
  before the view ever ran.
- Line-level shape: parent columns first, then child columns, one row per
  (parent, child) pair, **primary-key order**, parent ids repeated on every
  child row (that repetition is what makes the flat file re-groupable
  downstream). A parent with no children still gets a row with empty child
  columns — an export that silently drops a record is the same bug as a
  kanban column that swallows a card.
- Keep the writer in its own **DRF-free module** (`csv_export.py`):
  `@extend_schema` captures `DEFAULT_SCHEMA_CLASS` at decoration time, so a
  test importing the views before the settings override lands gets a broken
  schema class (the real error was spectacular's
  `AutoSchema.get_operation() takes 3 positional arguments but 6 were given`).

## 4. Client contract (layer 2 binding — the R-003/R-004 rule again)

- `normalizeOpenAPI` binds `model.exportPath` **only when the document
  carries `GET <listPath>export/` and no POST on the same path** (a POST
  there means the router gave a different meaning to that segment — refuse
  rather than guess). "Admin binds a button to it when present": `DataTable`
  renders "Full export" iff `onserverexport` is passed, and `ModelPage`
  passes it iff `model.exportPath` exists.
- The call is `fetchCsv(cfg, token, model.exportPath, fallback)` — base URL +
  the **schema-discovered** path, never `apiUrl + "export"` (the bare-segment
  concatenation that once produced `http://hostapi…` and silently broke
  R-001 calls; see docs/DEVGUIDE.md).
- `Accept: text/csv, */*;q=0.8` — text/csv preferred, but a proxy/plain-DRF
  JSON error body must stay readable instead of 406ing at negotiation.
- The **server's filename wins** when `Content-Disposition` carries one
  (quoted or bare form), but it goes through the same `exportFileName()`
  slugifier as a client-generated name: a header is data, not a save path.
- The response bytes are handed to `downloadCsv` **untouched** — the whole
  collection is the server's answer; the client strips a duplicate BOM, not
  content.

## 5. Copy checklist for a client project

1. Copy `csv_export.py` next to the parent model; header = parent columns +
   child columns, rows = one per pair, parent id repeated, pk order,
   children-oldest-first, empty rows for childless parents.
2. Add the `@action` per §3 (search honoured, `pagination_class=None`,
   `CSVTextRenderer` in `renderer_classes`, `utf-8-sig` encode, attachment
   disposition). Add the paired columns to `@extend_schema` so the schema
   advertises it.
3. Ship `app/src/lib/csv.ts` unchanged unless you change §2 — then change
   both twins in the same commit and diff a download against a server export
   of the same rows.
4. Wire layer 1 to the table's own derived column list (never a re-derived
   copy — the file must match what the user is looking at).
5. Do NOT touch `normalizeOpenAPI` for a per-API special case; if an export
   is not in the document, the button does not exist. That is the feature.

## 6. Proving it

- Re-runnable harness (2026-10-21): `python3 scripts/csv_twin_diff.py` feeds one
  generated matrix (sentinel strings + float switch points + N random cells,
  default 3000) through BOTH writers exactly as each one produces a download —
  `csv_text(header + [[csv_cell(v)]])` on the server, `buildCsv(header, raw)` on
  the client via the real `csv.ts` under vitest — and compares raw bytes. Exit 0
  identical, 1 divergence (first 20 differing lines printed), 2 rig could not
  run. Measured green at this HEAD (870 cells / 17004 B, and 3082 cells earlier
  the same day), and its negative control bites: disabling the server's formula
  guard makes it name every missing apostrophe. Compare DOCUMENTS, not cells —
  `csv_cell` guards before `csv.writer` quotes, while `csvCell` does both, so a
  stage-by-stage diff invents divergences (see docs/DEVGUIDE.md, FIFTH law).
  It needs no venv: layer 2 runs on `demo-backend/.venv/bin/python` when that
  exists and can import the rig's deps, otherwise on the interpreter running the
  script, chosen by an import PROBE (`django, rest_framework, drf_spectacular,
  admincraft`) — never by assumption, and the verdict prints
  `layer 2 interpreter: …` so a pass always says which python proved it. `--python
  <exe>` forces one interpreter exclusively: if a seat names it, its failure is
  the answer rather than a licence to fall back and report a pass from another
  environment. Measured 2026-10-21 on a box with NO venv at all: previously exit
  2 ("`…/.venv/bin/python` missing") in 0 s while the system python satisfied every
  dependency — the CI landing gate pip-installs the plugin into its own
  environment and never builds a rig venv, so this harness's claim was
  un-re-runnable exactly where the gate runs; now BYTE-IDENTICAL 3070 cells /
  56287 B in 2.9 s. Controls: `--python /nonexistent/python` → 2 (`cannot
  launch`), `--python <venv without django>` → 2 naming
  `No module named 'django'`, a real dep-free `.venv` present → falls back and
  says so, and a server-side `true/false` → `1/0` mutation → 1 naming the line
  (`line 101: client=b'98,false' server=b'98,0'`), file restored byte-identical.
- Re-runnable harness for the SHARED TABLES too: `python3 scripts/parity_table_diff.py`
  diffs `FLOAT_PARITY` and the golden document literal between
  `plugin/tests/test_csv_export.py` and `app/src/lib/__tests__/csv.test.ts`. Each
  suite is green against ITS OWN copy, so before this script a one-sided edit (a
  value added, a golden re-wrapped) kept 299 pytest + 416 vitest green while the
  word "shared" stopped meaning anything. Floats are keyed by their IEEE-754 bytes,
  never by `str()`/`String()` — the rendering is the claim under test, and the two
  languages differ in it on purpose (`1e17`). The golden ROWS are deliberately not
  compared (`Decimal("19.99")` server-side vs the text DRF sent, an aware
  `datetime` vs its `Z` string); the asserted BYTE STRING is what must match. Exit
  0 / 1 / 2 as above; it parses both files instead of importing them, so it needs
  `node` but no `node_modules` and no venv. See docs/DEVGUIDE.md, SEVENTH law.
- BOTH harnesses pin their own POPULATION (2026-10-21), because a byte compare is
  structurally blind to its own coverage. `csv_twin_diff.py` feeds ONE matrix to both
  writers, so shrinking the matrix cannot make them disagree — measured before the
  pins: 5 sentinels deleted (both line-breakers, `cr\rhere`, and the `=SUM`/`+cmd`
  guard leads, i.e. the cells §2 credits with divergences #1 and #2) answered
  `BYTE-IDENTICAL — 3065 cells`, rc 0, against the honest 3070. `parity_table_diff.py`
  compares two COPIES, so a row deleted from both still compares equal — measured: the
  `1e-7` row gone from both files answered `FLOAT_PARITY: 24 rows, identical values AND
  expectations`, rc 0, against the honest 25. Now each carries a literal population
  (`EXPECTED_SENTINELS`/`EXPECTED_FLOATS`, `EXPECTED_ROWS`) that must agree with the
  lists / parsed rows, and the rows holding a RECORDED divergence are pinned one by one
  by identity: floats by IEEE-754 bytes, never by equality, since `0.0 == -0.0` in
  Python cannot tell a matrix that kept negative zero from one that lost it; the golden
  document by required substrings (`2026-10-20T21:00:00Z`, `'=HYPERLINK`,
  `"Gizmo, big"`, `-5.00`, `1e-7`) rather than by length, which a re-wrap legitimately
  moves. The verdict split matches the brand twin: population disagrees with its pin →
  exit 2 `CANNOT RUN` (the harness does not understand its input, so there is no
  verdict); a pinned row vanished → exit 1 RED naming the row and the promise it
  carried (a proof regression, not a tooling gap). Controls, each restored
  byte-identical: 5 sentinels deleted → 2 `43 sentinels in the literal, 38 built`; one
  NON-required sentinel → 2 at 42-vs-43 (only the literal can see it); `build_matrix`
  dropping a float while both lists stayed honest → 2 `MATRIX TRUNCATED: 3069 cells
  built against 3070 expected`; `1e-7` → `1e-8` swapped on BOTH sides with 25 rows
  intact → 1 `COVERAGE LOST … python copy lost 1e-07` naming both copies; the guard
  dropped from both golden literals → 1 naming `'=HYPERLINK` in each. A line COUNT is
  not a row count: the first attempt pinned `cells + 1 == CRLF lines` and went RED on
  the honest run, because 3070 cells ride 3097 lines — a quoted cell may contain CRLF —
  so the compare's coverage is pinned by row IDENTITY (column 0 is the index the probe
  was handed, so the last matrix index must appear as its own record).
  See docs/DEVGUIDE.md, ELEVENTH law.

- `plugin/tests/test_csv_export.py` — writer byte rules, formula guard both
  shapes, line-level ordering, childless parents, search honoured, no
  pagination wrapper, 401 on anonymous, schema advertises the path, and the two
  **over-the-wire** classes (`TestFloatOverTheWire`, `TestDatetimeOverTheWire`)
  that drive the value through the model field and the endpoint instead of
  handing it to the writer directly. The client mirrors the premise in
  `openapi.test.ts` (the rig's `FloatField` must normalise to `type: number`,
  never an FK or a string) and in `csv.test.ts` (a float exports exactly as
  `JSON.parse` left it).
- `app/src/lib/__tests__/csv.test.ts` + `api.test.ts` — the same §2 rules on
  the client twin, BOM idempotency, filename slug safety (a model named
  `../../etc/x` cannot steer a save path), and the live-schema
  discovery/`fetchCsv` contract against a mocked fetch.
- Cross-layer diff: log into the demo rig, open Orders, export the table and
  the full export, and diff the parent columns of any overlapping row — they
  are byte-identical. The rig is now the fixture for that claim rather than an
  escape from it: `Order.weight` is a real `FloatField` (`shop/models.py`),
  seeded with the values that used to disagree — `2.0`, `0.5`, `48.5`, `100.0`,
  `1e-7`, `1e17`, `-0.00042` and `NULL` (`seed_demo.py`) — and `weight` is a
  column of the line-level header, so the float path and the datetime path are
  exercised by the same seeded data a reviewer exports by hand.
- Live end-to-end proof (measured 2026-10-21 11:30 UTC, platform-engineer, rig
  on `127.0.0.1:8042`): 60 seeded orders, both writers running real code — the
  repo's own `csv.ts` bundled with esbuild against the JSON list body, and the
  `export/` endpoint's own bytes off HTTP. Result: **60 rows × the 10-column
  parent block, 0 cell mismatches**, weight renderings
  `2 | 100 | 48.5 | 0.5 | 1e-7 | 100000000000000000 | -0.00042 | (null)`.
  The same diff run before `drf_datetime_text` landed: **60 mismatches, all of
  them `created_at`** — which is how divergence #2 was found at all, and why a
  writer-only table could not have found it.
- Randomised cross-twin diff (measured 2026-10-21, platform-engineer): the
  real `csv_cell`/`csv_text` from `shop/csv_export.py` and the real
  `buildCsv` from `csv.ts` were fed the SAME value matrix — 12 seeds × 250
  rows over an alphabet built to break a writer (embedded `"`/`,`/CRLF/LF/CR,
  TAB- and `-`-lead, `=HYPERLINK(…)`, `-2+3` vs `-5.00`, bare `-`/`.`,
  `\u0000`, emoji + CJK, 300-char runs, int/bool/null/empty) restricted to
  the types a JSON body can carry — plus the live rig's own 63 rows including
  three created with formula-lead notes. Every run came out byte-identical,
  and the guard fired identically (`=HYPERLINK` and `-2+3` apostrophised,
  `-5.00` left as data). Run the SAME matrix with `float` cells left in — the
  2026-10-21 segment that found the `repr` divergence did exactly that (144 of
  507 lines differed, every one of them a float) — and it is now byte-identical
  too: 12 seeds × 250 rows × 8 columns including integral floats, subnormals,
  `1e100`, `5e-324`, `-0.0` and random magnitudes from `1e-8` to `1e9`, 295 KB
  of output, zero differing lines. That is the whole extent of the disagreement,
  and §2 is how it is closed.
