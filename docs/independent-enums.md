# Independent enums ("separated status fields") — convention & guardrails (FR-R002 / ROADLOG R-002)

Status: the pattern **already exists** — the schema-driven `RecordForm` renders each
choice field as its own select, and nothing in `app/src` derives one enum from
another. This document is the R-002 deliverable: it pins the vocabulary, the
server-side rules that keep the schema honest, the client-side rules that keep the
UI honest, and the three failure modes with the warning text that names them.

ROADLOG R-002 (`ROADLOG.org:12-15`): *"Independent enums already render as
independent select fields (schema-driven RecordForm); guardrails: never derive one
from the other in client code. Doc path: docs/DEVGUIDE.md hard-won contracts. Kanban over
them needs R-001/R-004."*

## 0. What "independent enum" means here

Two or more choice fields whose value sets carry **different meanings and evolve
separately**. In this product it shows up in three shapes:

| shape | example | why it is independent |
| --- | --- | --- |
| same field name, different models | `order.status` (lifecycle) vs a hypothetical `shipment.status` (progress) | same word, unrelated machines |
| different field names, one model | `order.status` + a hypothetical `order.payment_method` | orthogonal axes |
| lifecycle status beside free enums | `order.status` (governed by R-001) + `order.notes`-adjacent flags | only one of them may be transition-governed |

One-line rule, quoted throughout: **each field's option set is its own contract —
no layer (server, schema, client) may derive one field's value or options from
another field.**

## 1. Server-side pattern (Django / DRF)

1. **One `Choices` class per semantic field, nested in its model, never shared.**
   `demo-backend/shop/models.py:86-93` declares `class Order.Status(models.TextChoices)`
   and only `Order` uses it (`demo-backend/shop/models.py:111`). A second concept gets a second class
   (`class PaymentMethod(models.TextChoices)`), even if the values temporarily match.
   Reusing one choices tuple across two unrelated fields is what turns two
   independent enums into one accidental dependency.
2. **Values are the wire contract; labels are display-only.** The label ("Paid")
   never reaches the client — `CharField.choices` emits the value. drf-spectacular
   hashes the (name, value) pairs (`drf_spectacular/hooks.py:50-58`, `x-spec-enum-id`), which is why
   relabelling a choice does not change the schema shape.
3. **Lifecycle order lives in the machine, not in the schema.** A status field that
   is lifecycle-governed carries `STATUS_ORDER` + `TRANSITIONS` on the model
   (`demo-backend/shop/models.py:97`, `:102-107`) and the R-001 API (`docs/order-lifecycle.md`). A free
   enum carries neither. The client cannot tell them apart from the enum list — see §3.
4. **Do not set `blank=True` on a choices field unless an empty state is real.**
   It changes the emitted schema shape (`BlankEnum`, §2 case C) and the client now
   reads that union (§4) — but the schema churn is still a reviewable cost.

## 2. What the schema actually emits (measured on drf-spectacular 0.30)

Enum hoisting is done by the `postprocess_schema_enums` hook
(`drf_spectacular/hooks.py:40-177`) and the component name is keyed on the
**property name, not the model** (`drf_spectacular/hooks.py:67-76`). Consequences, measured by
feeding the hook synthetic schemas (no app changes; recipe in §5):

- **Case A — one field name, one choice set.**
  `Order.status` and `Invoice.status` with identical sets → a single shared
  component `StatusEnum`, both properties `$ref` it (`drf_spectacular/hooks.py:89-91`). Legal, but it
  is the case to watch: the sharing holds only while the sets stay equal, and the day
  one model gains a value, the schema silently renames the component under both.
- **Case B — same field name, different sets, each used by one model.**
  `Order.status` = `pending|paid`, `Shipment.status` = `new|delivered` → the name
  gains the component prefix: `OrderStatusEnum` and `ShipmentStatusEnum`
  (`drf_spectacular/hooks.py:92-95`). **Independent enums stay independent in the schema** — this is
  the outcome the R-002 pattern relies on, and it needs no client work.
- **Case C — a set reused across several components *and* competing sets under one
  name.** Non-optimally resolvable collision → hash-suffixed name
  (`Status<Hash3>Enum`) **plus a warning** (`drf_spectacular/hooks.py:96-103`):
  > `enum naming encountered a non-optimally resolvable collision for fields named "status". … add an entry to ENUM_NAME_OVERRIDES to fix the naming.`
  Two further warnings mean the same thing from the other side: *multiple names for
  the same choice set* (`drf_spectacular/hooks.py:104-110`) and, at the registry,
  *`Encountered 2 components with identical names "X" and different identities …
  This will very likely result in an incorrect schema. Try renaming one.`*
  (`drf_spectacular/plumbing.py:795-803`). All three are the schema-level form of "you derived one
  enum from another" — treat any of them as a build defect.
- **Fix for a collision you cannot rename away:** declare the names explicitly —
  `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"] = {"StatusEnum": Order.Status.choices}`
  (default `{}`, `drf_spectacular/settings.py:118`); `ENUM_SUFFIX` (`:125`) is the
  other knob.
- **Blank/nullable choices split into extra components** (`drf_spectacular/hooks.py:145-164`, and
  `ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE` defaults to **True**, `drf_spectacular/settings.py:120`), so
  the property stops being a plain `$ref`:

  ```json
  {"$ref": "#/components/schemas/StatusEnum"}                                  // no blank  (case A/B)
  {"oneOf": [{"$ref": "…/PriorityEnum"}, {"$ref": "…/BlankEnum"}]}             // blank=True (case C)
  ```

- Fixture evidence for the shipped shape:
  `app/src/lib/__tests__/fixtures/openapi.json` carries
  `components.schemas.StatusEnum = {"enum": ["pending","paid","shipped","refunded"], "type": "string"}`
  and `Order.properties.status = {"$ref": "#/components/schemas/StatusEnum"}`.
- Enum **value order is not a contract**: serializer properties emit declaration
  order (`drf_spectacular/plumbing.py:449-451`), but query/filter parameters get `sorted(enum)`
  (`drf_spectacular/plumbing.py:400-407`). Never read lifecycle sequence out of an `enum` array.

## 3. Client contract (what the thin client does, and must keep doing)

- Each field's options come from **that field's own** schema entry: enum detection at
  `app/src/lib/openapi.ts:95-96` (inline `enum`, or a `$ref` resolving to a component
  that carries `enum`), choices copied per field at `app/src/lib/openapi.ts:137-155`. `FieldSpec.choices`
  is per-field — no option list is ever merged, cached by name, or shared across
  models.
- `RecordForm` renders **one select per enum field** straight from `f.choices`
  (`app/src/components/RecordForm.svelte:190-197`). Two enum fields on one model
  produce two independent selects: no cascade, no defaulting one from the other.
- Lifecycle affordances are keyed **per model**, never per field name: the registry
  `app/src/lib/statusTransitions.ts:23-34` maps `orders → {statusField, states,
  transitions}`, and `hasLifecycle(modelId)` (`:55-57`) gates the whole feature — a
  field named `status` on any model without an entry gets no transition buttons and
  `getLegalTransitions` answers `[]` (`:37-41`). `DataTable`'s status chip compares
  `col.name === statusField` **within that model** (`app/src/components/DataTable.svelte:35`, `:178-179`).

The guardrails, as checks a reviewer can run on a diff:

1. **Never compute one enum's value from another field in client code** — no
   `if (row.paid_amount) row.status = "paid"`. Booleans, money and dates feed the
   *server* machine through the R-001 API, not the client's idea of status.
2. **Never reuse another model's options or transitions because the field name
   matches.** `orders.status` governance does not transfer to `shipments.status`.
3. **Never infer lifecycle order from the schema `enum` list** (§2, last bullet) —
   order comes from the registry entry / the server's `STATUS_ORDER`.
4. **Never `PATCH` one model's status to "sync" another model's.** Cross-model
   coherence is a server transaction (R-001 side-effect seam), not a client effect.
5. **Free enums stay free.** Do not add a status field to `statusTransitions` unless
   the backend actually exposes `/transition/` + `/history/` for it — otherwise the
   UI offers buttons the server rejects.

## 4. Case C, found here and closed by the FE segment (2026-10-23)

`deref()` (`app/src/lib/openapi.ts:28-34`) follows a **top-level `$ref` only** — correct
for its own job, but a blank-allowing choice field arrives as
`{"oneOf": [PackagingEnum, BlankEnum]}` (§2 case C), which no branch of `fieldTypeOf`
recognised, so it fell through to the schemaless default `"text"`
(`app/src/lib/openapi.ts:126-128`) — **the select degraded to a free-text input**, with no
error anywhere. The demo rig had no `blank=True` choices field, so the shipped fixture
never showed the shape; a real customer API very likely does.

Closed as this section prescribed, and pinned on both sides of the wire:

- The normalizer reads unions through — `sentinelKinds()` / `unionMembers()` /
  `effectiveSchema()` (`app/src/lib/openapi.ts:49-88`), applied in `fieldTypeOf()`
  (`app/src/lib/openapi.ts:91`) and `propToField()` (`app/src/lib/openapi.ts:139`).
  `oneOf`, `anyOf` and `allOf` all resolve, by `$ref` member or inline shape.
- **The two sentinels are not the same signal.** `BlankEnum` means the field
  accepts the empty string; `NullEnum` means it accepts JSON `null`. Only the
  second sets `FieldSpec.nullable`, because `blank=True` fields are usually still
  non-nullable and `RecordForm.buildPayload` must OMIT an empty value there —
  sending it `null` is the documented DRF 400. (This distinction was found by the
  mount test, not in review: the first cut treated any sentinel as nullable and
  the create case's exact-payload assertion failed with `packaging: null`.)
- The rig now ships the shape for real: `Product.packaging`
  (`demo-backend/shop/models.py:52`) is a `blank=True` choices field whose schema
  emits `oneOf: [PackagingEnum, BlankEnum]` on `Product`, `ProductRequest` and
  `PatchedProductRequest`, and the fixture was recaptured from that schema
  (`app/src/lib/__tests__/fixtures/openapi.json`). `plugin/tests/test_schema_drift.py`
  (`test_blank_choices_union_documented`) refuses a rig that stops emitting it, so
  the server half of the proof cannot rot silently.
- The client half is pinned three times over: seven synthetic union shapes and one
  fixture assertion in `app/src/lib/__tests__/openapi.test.ts` (the
  `union members (FR-R002 case C)` block), and the wire-level proof in
  `app/src/lib/__tests__/recordFormMount.test.ts` — a mounted ModelPage asserts
  `#f-packaging` is a `SELECT` carrying `["", "box", "crate", "pallet"]` (the "—"
  IS the blank state, so the sentinel never joins the choices) and that picking a
  value PUTs it.
- Guardrail 4 (§1) still stands as advice: an unnecessary `blank=True` churns the
  schema shape. But "unnecessary" no longer means "invisible" — the field now
  renders as the select it declares.

## 5. Copy checklist for a client project + how to reproduce the measurements

- [ ] one `Choices` class per semantic field, nested in the model, never shared across models
- [ ] no `blank=True` on a choices field unless an empty state is a real value
- [ ] if two models must share a field *name* with different sets → add
      `ENUM_NAME_OVERRIDES` entries so component names are stable and reviewable
- [ ] generate the schema and grep the output/logs for the three collision warnings
      (`non-optimally resolvable collision`, `multiple names for the same choice set`,
      `2 components with identical names`) — a hit means the enums are not independent
- [ ] client: add a `statusTransitions` entry only for models that expose the R-001
      endpoints; key everything by model id, never by field name alone

Reproduce §2 without touching the app (the script used for this doc — it drives the
real hook, so the names it prints are the names your schema will carry):

```python
from drf_spectacular.plumbing import ComponentRegistry
from drf_spectacular.hooks import postprocess_schema_enums

reg, holder = ComponentRegistry(), {"Order": {"type": "object", "properties": {
    "status": {"type": "string", "enum": ["pending", "paid"]}}}}
class G: pass
g = G(); g.registry = reg
postprocess_schema_enums({"components": {"schemas": holder}}, view=None, generator=g)
print({k: v.schema for k, v in reg._components.items()})   # component names
print(holder["Order"]["properties"]["status"])             # property shape ($ref | oneOf)
```

Add a second model with a different `status` set to see case B; add `""` to an `enum`
to see case C's `oneOf`/`BlankEnum`.

## 6. Kanban (R-004) depends on this doc

A kanban board groups records by **exactly one** enum field, and the ROADLOG ties the
two together: *"Kanban over them needs R-001/R-004"* (`ROADLOG.org:15`). Therefore,
when R-004 lands:

- the board axis must be **declared** (registry entry or explicit widget/page meta),
  never guessed from "the field named `status`" or "the first enum field" — on a model
  with `status` + `priority` either guess can be wrong, and guessing is precisely the
  cross-derivation §3 forbids;
- drag-and-drop fires the **R-001 transition API** only when the axis is a
  lifecycle-governed field (an entry exists in `statusTransitions` **and** the schema
  exposes `/transition/`);
- a drop on a free-enum column is a plain `PATCH` of that one field — and must touch
  nothing else on the record (guardrail 1).
