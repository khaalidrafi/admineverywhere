# Custom actions + audit — server contract & client-project convention (FR-R003 / ROADLOG R-003)

Status: **reference implementation shipped on `ai/fr-r003-be`** (server side,
stacked on `ai/fr-r001-be`). Every client project that adds record/bulk actions
copies the pattern below instead of inventing its own wiring. The demo backend
(`demo-backend/`) is the executable spec; `plugin/tests/test_audit_actions.py`
is its test harness.

## 1. The registry contract (FE meta ↔ BE @action)

R-003 mirrors the widget contract: the FE registers one `.ts` file exporting
`meta{label, scope: record|bulk, confirm?, handler}`; the handler fires a DRF
`@action` endpoint. The server half of that contract is what this repo ships:

| FE meta           | BE surface                                |
| ----------------- | ----------------------------------------- |
| `scope: "record"` | `@action(detail=True, methods=["post"])`  |
| `scope: "bulk"`   | `@action(detail=False, methods=["post"])` |
| `confirm?`        | FE-only dialog; the BE always re-validates |
| `handler`         | fires the endpoint, then refreshes the record + audit sub-view |

### The client half (shipped on `ai/main`, FR-R003-FE)

* `app/src/lib/actions/index.ts` — the drop-in registry: `import.meta.glob`
  over `app/src/actions/*.ts`, same no-registry-to-edit promise as widgets.
  `actionsFor(modelId, scope)` filters by `scope` and by the optional
  `meta.model` (url segment); omit `model` to offer the action everywhere.
* A handler receives `{cfg, token, model, rows, input}` and resolves to the
  audit entries the server wrote (`AuditEntry[]`). Two meta fields extend the
  original sketch, both FE-only: `meta.input` (a label, e.g. `"Reason"`) makes
  the confirm dialog collect one text value and pass it as `input`;
  `meta.confirm` stays the yes/no guard.
* `app/src/actions/flag.ts` (record) and `app/src/actions/bulk_flag.ts` (bulk)
  are the reference registrations, wired to the two BE endpoints below via
  `callRecordAction` / `callBulkAction`.
* URL building is centralized in `actionPath(model, slug, recordId?)`
  (`app/src/lib/api.ts`) and is derived from the schema-discovered
  `model.listPath` — never from a string guess at the url segment, and never by
  concatenating `apiUrl + modelId` (that form silently produced
  `http://hostapi…` for the R-001 transition/history calls; both now share this
  helper and are pinned by tests).
* `ModelPage` renders record actions as per-row buttons, bulk actions over the
  `DataTable` selection (a checkbox column appears only when a bulk action is
  registered), then reloads the list and refreshes the open record sub-view.
  A rejected action surfaces the server `reason` (400/409 shape), never a bare
  status code.
* The record sub-view (history icon, now available for every model) shows the
  R-001 lifecycle trail oldest-first and, below it, this record's audit entries
  newest-first — `GET /api/audit/?object_type=<model singular>&object_id=<pk>`.

## 2. The audit log (append-only by construction)

`AuditEntry` (`demo-backend/shop/models.py`) — one loose-coupled table any
model's actions write into:

- fields: `actor` (nullable FK, SET_NULL), `action` slug, `object_type` +
  `object_id` (strings, **no FK** — any model audits into this one table),
  `summary`, `data` (JSON, action-defined), `created_at`.
- API: `GET /api/audit/` (list) + `POST /api/audit/` (append) — nothing else.
- **Append-only is structural, not promised**: the ViewSet carries List+Create
  mixins only, so PUT/PATCH/DELETE answer 405 and the router never generates a
  detail route at all — rows have no URL surface to mutate through.
- `actor` is ALWAYS derived from the authenticated request; a client-supplied
  actor is ignored (test-pinned).
- Ordering ruling (decided once, in the model): audit reads **newest-first**
  (triage wants the latest event on top); lifecycle history (R-001
  `OrderHistory`) stays **oldest-first** (replay). Both tie-break by id.
- Optional `?object_type=` / `?object_id=` filters back the record sub-view and
  the R-007 activity-log screen.

### GET /api/audit/ — paginated (the log grows unbounded)

Standard DRF `{count, next, previous, results}` shape; results newest first:

```json
{"id": 9, "action": "order.flag", "object_type": "order", "object_id": "42",
 "actor": "ops1", "summary": "Order flagged: suspected fraud",
 "data": {"reason": "suspected fraud"},
 "created_at": "2026-10-19T03:40:00.123456Z"}
```

### POST /api/audit/ — the append surface

Body `{"action", "object_type", "object_id", "summary"?, "data"?}` → `201`
with the created entry; `actor`/`created_at` are read-only. Intended for
actions the server cannot anticipate yet — first-party action code should
create entries server-side (see the reference actions below).

| case                 | status | body         |
| -------------------- | ------ | ------------ |
| append               | `201`  | AuditEntry   |
| unauthenticated      | `401`  | DRF default  |
| PUT / PATCH / DELETE | `405`  | DRF default — append-only |

## 3. The reference actions (copy these two)

Both are `@action`s on `OrderViewSet`; guard errors keep the R-001 shape —
400 with **exactly one key, `reason`**.

### POST /api/orders/{id}/flag/ (record scope)

Body `{"reason": "<text>"}` → `201` with the new audit entry. Changes **no
order fields** — audit-only by design, so it is safe to fire from any UI state.

| case                | status | body                    |
| ------------------- | ------ | ----------------------- |
| flagged             | `201`  | audit entry             |
| missing `reason`    | `400`  | `{"reason": "<why>"}`   |
| unknown order       | `404`  | DRF default             |
| unauthenticated     | `401`  | DRF default             |

### POST /api/orders/bulk_flag/ (bulk scope)

Body `{"ids": [<order id>, ...], "reason": "<text>"}` → `201` with **one audit
entry per order** (duplicates collapse to one per order); each entry's `data`
carries bulk provenance `{"reason", "bulk": true, "batch": N}` so the record
sub-view sees the batch effect on every touched record.

| case                          | status | body                              |
| ----------------------------- | ------ | --------------------------------- |
| flagged                       | `201`  | array of audit entries            |
| missing/empty `ids`           | `400`  | `{"reason": "<why>"}`             |
| missing `reason`              | `400`  | `{"reason": "<why>"}`             |
| non-integer ids               | `400`  | `{"reason": "<why>"}`             |
| unknown ids                   | `400`  | `{"reason": "<why>"}` (lists them; nothing written) |
| unauthenticated               | `401`  | DRF default                       |

### OpenAPI

The thin client derives everything from `/api/schema/`, so the audit endpoint
and both action request bodies are documented automatically
(`FlagRequest` / `BulkFlagRequest` components via explicit request serializers).

## 4. Client-project convention (copy this pattern)

1. **One audit table, loose targeting** — `actor`/`action`/`object_type`/
   `object_id`/`summary`/`data`/`created_at`; no GenericFK, strings travel.
2. **Structural append-only** — list+create surface only; never add update or
   delete routes, and let the router omit the detail route (test pins it).
3. **Actor from the request, never the body** — spoofing is a test case here.
4. **Ordering ruling up front** — audit newest-first, history oldest-first;
   both tie-break by id.
5. **One `@action` per scope to start** — record (`detail=True`) + bulk
   (`detail=False`); 400 + `{reason}` guards; audit row written inside the
   same request, after the effect succeeds.
6. **Bulk writes one row per target** — with provenance in `data`, so
   per-record views stay truthful.
7. **Schema-visible bodies** — explicit request serializers so OpenAPI
   documents the contract the client derives from.
8. **Test the contract, not the decoration** — append shapes, 405 /
   no-detail-route, actor spoofing, newest-first ordering, object filters,
   schema exposure. See `plugin/tests/test_audit_actions.py`, ready to copy.

## 5. Notes & compatibility

- **Stacked on FR-R001**: `ai/fr-r003-be` is based on `ai/fr-r001-be` (the
  audit reference shares the demo-rig conftest scoping introduced there);
  it merges after R-001-BE.
- **R-007 (RBAC + audit screen) reads this endpoint** through the object
  filters — the response shape is the contract; keep it stable.
- Lifecycle transitions deliberately do NOT double-write audit entries:
  `OrderHistory` is the lifecycle trail; `AuditEntry` is for custom actions.
- `seed_demo` does not fabricate audit entries; the log fills as actions run.
- The OpenAPI fixture used by the client's normalizer tests
  (`app/src/lib/__tests__/fixtures/openapi.json`) is recaptured from the live
  rig, so it carries the audit registration. Nothing in the FE builds the log
  URL from a string: action calls come from `model.listPath` through
  `actionPath()`, and `fetchAudit()` takes the `listPath` that
  `findAuditModel()` resolved from the document — with no audit model in the
  schema it throws `ApiError` and fires zero requests, the same evidence law
  as `transitionRecord()`/`fetchHistory()`. `ModelPage.showHistory()` therefore
  skips the log half rather than probing a guessed `/api/audit/`, a segment a
  different backend app might own.
- Test suite on this branch: `pytest` 175/175 (151 before FR-R003, +24) —
  run `cd demo-backend && python -m pytest ../plugin/tests`.
