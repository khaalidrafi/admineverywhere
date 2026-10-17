# Order lifecycle — server contract & client-project convention (FR-R001 / ROADLOG R-001)

Status: **reference implementation shipped on `ai/fr-r001-be`** (server side).
Every client project that manages order lifecycles copies the pattern below instead
of inventing its own state handling. The demo backend (`demo-backend/`) is the
executable spec; `plugin/tests/test_order_lifecycle.py` is its test harness.

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

## 5. Notes & compatibility

- **`status` stays writable on `PATCH /api/orders/{id}/`** — pre-existing
  MVP behavior, kept additive for the thin client's schema-driven forms.
  The transition endpoint is the governed path; a future hardening ticket
  may make the field read-only once all clients are migrated.
- `seed_demo` gives every seeded order its creation trail row (actor null),
  so demo data reads coherently through the history endpoint.
- The OpenAPI fixture used by the client's normalizer tests
  (`app/src/lib/__tests__/fixtures/openapi.json`) predates these endpoints
  and should be recaptured when the frontend integrates them.
- Test suite on this branch: `pytest` 90/90 (53 before FR-R001, +37) —
  run `cd demo-backend && python -m pytest ../plugin/tests`.
