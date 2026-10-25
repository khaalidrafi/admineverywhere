# Order lifecycle — server contract & client-project convention (FR-R001 / ROADLOG R-001)

Status: **reference implementation shipped — server side and client side**
(`docs/order-lifecycle.md` §4A is what the thin client binds).
Every client project that manages order lifecycles copies the pattern below instead
of inventing its own state handling. The demo backend (`demo-backend/`) is the
executable spec; `plugin/tests/test_order_lifecycle.py` is its test harness and
`app/src/lib/__tests__/lifecycleMount.test.ts` is the client's wire-level proof.

## 1. The state machine

The lifecycle is an **ordered enum plus an explicit transition table** — both
live on the model, in one place, and nothing else may hand-roll status rules.

```
                pay                ship               refund
  [pending] ---------> [paid] ---------> [shipped] ---------> [refunded]
                          \                                  ^
                           +---------------------------------+
                                      refund (before shipping)

  refunded is TERMINAL — nothing leaves it.
```

- `Order.Status` (TextChoices) is declared **in lifecycle order** —
  `pending, paid, shipped, refunded`. Declaration order is the contract.
- `Order.STATUS_ORDER` pins the canonical order explicitly (index 0 is the
  entry state; `refunded` sits last as the absorbing exit, not a stage).
- `Order.TRANSITIONS` maps every state to the frozenset of legal targets:

  | from      | legal targets            |
  | --------- | ------------------------ |
  | `pending` | `paid`                   |
  | `paid`    | `shipped`, `refunded`    |
  | `shipped` | `refunded`               |
  | `refunded`| — (terminal)             |

- `Order.transition_allowed(current, target)` is the single predicate; it
  answers `False` for unknown states, never raises.
- `Order.apply_transition(target, actor=None)` performs a move:
  validates → opens `transaction.atomic()` → runs the side-effect seam →
  saves `status` → appends the `OrderHistory` row. Illegal moves raise
  `IllegalTransition` carrying a stable human-readable `reason`.

## 2. API contract

Both endpoints are DRF `@action`s on `OrderViewSet` (router basename
`order`), so they ride the existing auth (token) and permissions.

### POST /api/orders/{id}/transition/

Body `{"transition": "<target state>"}` — the target, not the verb.

| case                          | status | body |
| ----------------------------- | ------ | ---- |
| legal move                    | `200`  | updated `Order` object |
| machine-illegal / no-op / terminal | `409` | `{"reason": "<why>"}` |
| unknown target status         | `400`  | `{"reason": "<why>"}` (lists valid values) |
| missing `transition` field    | `400`  | `{"reason": "<why>"}` |
| unauthenticated               | `401`  | DRF default |
| unknown order                 | `404`  | DRF default |

The 409 body is **exactly one key, `reason`** — clients surface it verbatim;
it is never localized and never changes shape. Guard errors are 409 (not
422) because the request is well-formed but conflicts with resource state.

### GET /api/orders/{id}/history/

Returns the **append-only, timestamped trail, oldest first**, deliberately
NOT paginated (clients always get the full trail):

```json
[
  {"id": 1, "order": 42, "from_status": "",         "to_status": "pending",
   "actor": "admin", "created_at": "2026-10-17T09:00:00.123456Z"},
  {"id": 2, "order": 42, "from_status": "pending",  "to_status": "paid",
   "actor": "ops1",  "created_at": "2026-10-17T11:30:00.654321Z"}
]
```

- The **creation entry** has `from_status: ""` and is written by
  `perform_create` on `POST /api/orders/` (with the requesting user as
  actor). System/seed moves carry `actor: null`.
- Rows are never edited or deleted through the API.

### OpenAPI

The thin client derives everything from `/api/schema/`, so both endpoints
are documented there automatically (`@extend_schema` on the actions): the
request body is the `TransitionRequest` component and its `TransitionEnum`
carries the states **in lifecycle order**.

## 3. Side-effect seam (what clients implement)

`Order._apply_side_effects(order, from_status, to_status)` runs **inside the
transition transaction**. The reference implementation ships it as
deliberate `# TODO(client)` no-ops:

- `pending -> paid`: **reserve stock** (TODO client no-op)
- `* -> refunded`: **release stock** (TODO client no-op)

Client projects replace the two bodies with their own stock policy and keep
the seam: same name, same `(order, from, to)` signature, still called inside
the transaction. If your side effect raises, the whole transition — status
change included — rolls back and no history row is written; that is the
guarantee that makes the stub safe to leave empty in the reference build.

## 4. Client-project convention (copy this pattern)

1. **Ordered enum on the model** — `TextChoices` declared in lifecycle
   order; never sort or compare states by string.
2. **One transition table** — a `TRANSITIONS` dict on the model is the only
   source of legality. Views/serializers/tests derive from it; nobody
   hand-rolls `if status == ...` rules.
3. **One guarded entry point** — `apply_transition(target, actor)` does
   validation + side effects + save + history inside one transaction and
   raises a typed `IllegalTransition(reason)`.
4. **Two generic endpoints** — `POST .../transition/` (409 + `reason` on
   guard failure) and `GET .../history/` (append-only, oldest first, with
   actor). Wire them as `@action(detail=True)` so schema and auth come free.
5. **Creation entry** — write the `from_status=""` trail row in
   `perform_create`, so every order's trail starts at birth.
6. **Side-effect stubs stay no-ops in the reference** — implement reserve/
   release in the seam, inside the transaction, and keep the signature.
7. **Test the contract, not the decoration** — machine matrix (all
   current×target pairs), 409+reason shape, trail order/actor, creation
   entry, seam-invoked + rollback-on-failure, schema exposure. See
   `plugin/tests/test_order_lifecycle.py` for all seven, ready to copy.

## 4A. What the thin client binds (FR-R001-FE)

The renderer offers a lifecycle only where **both** halves agree:

- `app/src/lib/statusTransitions.ts` declares the machine, keyed by model id
  (never by "the field named status").
- `normalizeOpenAPI` binds `model.transitionPath` and `model.historyPath` from
  the document itself — `POST <detail>transition/`, and GET-without-POST
  `<detail>history/`. That is the same evidence law that binds `exportPath`
  (FR-R005) and `mePath` (FR-R007): absence is silent degradation, never a guess.

A machine declared client-side but not documented server-side is **refused**, not
rendered optimistically. `lifecycleProblem()` names the reason; `DataTable` draws
no `→ <state>` buttons; `resolveAxis()` refuses a `transition` kanban axis; the
record sub-view states that the API documents no trail.
`transitionRecord()` / `fetchHistory()` call the discovered templates (`{id}`
substituted, pk percent-encoded) and raise before any network call when handed a
model that carries neither — `apiUrl` is only ever the base origin.

Wire-level proof: `app/src/lib/__tests__/lifecycleMount.test.ts` mounts the real
`ModelPage` against the captured document and asserts what goes over the wire —
the exact POST URL and `{transition: "<target>"}` body, a 409's `reason` surfaced
verbatim in the toast (not a generic failure banner), the trail read through the
discovered history path in oldest-first order, and zero buttons plus zero
requests once the actions are stripped from the schema.

The refusal is anchored TWICE, which a 2026-10-22 QA mutation audit measured: the
button block requires `hasLifecycleGovernance` (`app/src/components/DataTable.svelte:159`)
AND iterates the registry's own target list through `getLegalTransitions`
(`app/src/components/DataTable.svelte:160`), so a schema that documents
`POST …/transition/` for a model the client never declared still renders nothing —
and deleting only the `lifecycleAvailable` call is an EQUIVALENT mutation (no
reachable input changes its output, so no test can and none should pin it). The
five mutations that do change behavior are each killed by a named test: binding
`transitionPath` without POST evidence, binding `historyPath` on a document that
also accepts POST, replacing the missing-path refusal with a guessed URL, hiding
the 409 `reason` behind a generic banner, and treating every model as governed.
One anchor the audit initially found UNPINNED is now witness-backed: both lifecycle
calls substitute the pk into the discovered template themselves (never through
`actionPath`), so `transitionRecord`/`fetchHistory` carry their own
percent-encoding assertion in `app/src/lib/__tests__/actions.test.ts` — dropping
`encodeURIComponent` there turns the suite red instead of shipping a URL whose
space fetch may reject and whose `/` silently retargets another record's trail.

Live-transport check (same audit, real HTTP against the running rig, not the
fixture): the §2 table answers exactly as documented — legal move `200` with the
updated object, no-op/illegal/terminal `409` with a one-key `{reason}` body,
unknown target and missing field `400` with `{reason}`, unauthenticated `401`,
unknown order `404`, and `GET …/history/` a plain list, oldest first, whose first
row is the creation entry (`from_status: ""`, `actor: null`). The schema still
documents `transition` as `[post]` and `history` as `[get]`, which is the evidence
`normalizeOpenAPI` binds on.

## 5. Notes & compatibility

- **`status` stays writable on `PATCH /api/orders/{id}/`** — pre-existing
  MVP behavior, kept additive for the thin client's schema-driven forms.
  The transition endpoint is the governed path; a future hardening ticket
  may make the field read-only once all clients are migrated.
- `seed_demo` walks every seeded order through `apply_transition()` — the
  creation row (`from_status: ""`, actor null) plus one row per legal hop to
  the status the order ends on, refunds performed by the seeded non-superuser
  `auditor`. The trail is produced by the machine, never hand-written, so a
  demo trail can never show a hop the endpoint would refuse with 409;
  `plugin/tests/test_seed_demo.py` grades exactly that invariant.
- The client's proof fixture `app/src/lib/__tests__/fixtures/openapi.json` IS
  the captured document of this rig (recaptured 2026-10-21 from a running
  `manage.py runserver` + `GET /api/schema/?format=json`: 16 paths, 5 models,
  the R-001 `transition`/`history`, the R-003 `flag`/`bulk_flag`/`audit`, the
  R-005 `export` and the R-007 `me`). Recapture it whenever the rig gains an
  endpoint — a client test that passes against a document the server no longer
  answers is not proof. That duty is now a gate, not prose:
  `plugin/tests/test_schema_drift.py` regenerates the schema in a subprocess
  under the rig's own `core.settings` and fails the pytest suite on any drift
  between the rig and the fixture (paths and component schemas compared
  key-by-key, plus witnesses that `COMPONENT_SPLIT_REQUEST` and the four
  evidence-law endpoint shapes are still documented). It runs the rig's own
  `core.settings` because that is what the deployed rig serves — and the
  in-process rig scope in `plugin/tests/conftest.py` is aligned to the same
  profile (`COMPONENT_SPLIT_REQUEST` since 2026-10-21, measured zero drift on
  all 16 paths), so the four rig modules' schema tests generate a
  fixture-consistent document too.
- Suites: `pytest 299` / `vitest 418` (32 files) — the counts `scripts/landing_gate.py`
  pins (`EXPECTED_PYTEST`/`EXPECTED_VITEST`/`EXPECTED_VITEST_FILES`), re-measured
  2026-10-22 by the QA seat on this branch.
