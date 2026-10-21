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

A second divergence, reachable only by *type*, not by this product's data: a
Python `float` cell. `csv_cell(1.0)` writes `1.0`, `str(-0.0)` writes `-0.0`,
`str(1e-07)` writes `1e-07`, while `String()` on the same value gives `1`, `0`
and `1e-7`. Nothing else in the two writers disagrees — quoting, CRLF, null,
booleans and the formula guard are byte-for-byte twins for every value a JSON
response can carry (string/number-int/bool/null), which is what a DRF
`JSONRenderer` sends: decimals and dates arrive as STRINGS, so a client row
never holds a float to re-format. A client project that exports from a
`FloatField` through a hand-rolled path (not the API's own JSON) is the one
case that can drift; if you hit it, format on both sides or ban the field from
export.

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
  R-001 calls; see AGENTS.md).
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

- `plugin/tests/test_csv_export.py` — writer byte rules, formula guard both
  shapes, line-level ordering, childless parents, search honoured, no
  pagination wrapper, 401 on anonymous, schema advertises the path.
- `app/src/lib/__tests__/csv.test.ts` + `api.test.ts` — the same §2 rules on
  the client twin, BOM idempotency, filename slug safety (a model named
  `../../etc/x` cannot steer a save path), and the live-schema
  discovery/`fetchCsv` contract against a mocked fetch.
- Cross-layer diff: log into the demo rig, open Orders, export the table and
  the full export, and diff the parent columns of any overlapping row — they
  are byte-identical.
- Randomised cross-twin diff (measured 2026-10-21, platform-engineer): the
  real `csv_cell`/`csv_text` from `shop/csv_export.py` and the real
  `buildCsv` from `csv.ts` were fed the SAME value matrix — 12 seeds × 250
  rows over an alphabet built to break a writer (embedded `"`/`,`/CRLF/LF/CR,
  TAB- and `-`-lead, `=HYPERLINK(…)`, `-2+3` vs `-5.00`, bare `-`/`.`,
  `\u0000`, emoji + CJK, 300-char runs, int/bool/null/empty) restricted to
  the types a JSON body can carry — plus the live rig's own 63 rows including
  three created with formula-lead notes. Every run came out byte-identical,
  and the guard fired identically (`=HYPERLINK` and `-2+3` apostrophised,
  `-5.00` left as data). Re-run it with floats in the matrix and the ONLY
  cells that diverge are the `float`-repr ones above — that is how the §2
  caveat was found, and it is the whole extent of the disagreement.
