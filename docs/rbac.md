# FR-R007 — RBAC, phased (client-side first)

ROADLOG R-007 in two halves, both reference implementations in the demo
rig (`demo-backend/`), both contract-tested (`plugin/tests/test_rbac_roles.py`
+ `app/src/lib/__tests__/rbac.test.ts`).

## Phase (a) — the server emits role claims, the client filters

The thin client can only hide what the server tells it to. The contract
is one read-only path:

    GET /api/me/  ->  { "username": str, "is_staff": bool,
                        "is_superuser": bool, "roles": [str] }

`roles` are Django **Group names**, sorted (`demo-backend/core/views.py`).
`core/urls.py` mounts it; `seed_demo` creates `auditors` + `managers`
and holds them on `admin` so a fresh rig demonstrates claims end to end.
The seed also creates one caller per gating outcome (table below): a rig
holding only a superuser can prove acceptance but never rejection, since
`roleAllows()` lets superusers through unconditionally.

Client rules (`app/src/lib/rbac.ts`, decisions only — transport is
`api.ts:fetchMe`):

- **Discovery, never guessing.** `normalizeOpenAPI` binds `schema.mePath`
  only when the document carries `GET …/me/` with **no POST** — the same
  evidence law as `exportPath` (docs/csv-export.md) and `actionPath`.
- **Claims refresh with the schema** (`stores.ts:loadSchema`) and clear
  on logout. The store is a `svelte/store` writable — the cross-module
  state law.
- **No claims = no filtering.** A plain DRF backend without `/me/` (or a
  failed read) leaves `claims = null` and every menu/action stays visible.
  Silent degradation, branding law.

### Gating a nav entry

    export const meta = { title: "Activity", path: "/activity",
                          roles: ["auditors"] };   // optional

`Sidebar.svelte` hides a `roles`-declared entry unless the caller holds
at least one of them; superusers see everything. An invalid `roles`
declaration is **refused** into `refusedPages` with a nameable reason —
never half-registered (the R-006 refusal law).

### Gating an action

`meta.roles: ["managers"]` on an action file (`bulk_flag.ts` is the
reference) removes the button from DataTable/ModelPage for callers who
do not hold the role.

### Demo users (what `seed_demo` gives you)

| login | who they are | what the gate does |
| --- | --- | --- |
| `admin` / `admin123` | superuser, holds `auditors` + `managers` | sees **everything** — superuser short-circuits `roleAllows()` |
| `auditor` / `audit123` | non-staff, non-superuser, holds `auditors` **only** | the **rejection** path, live: the managers-only "Flag batch" button is absent from the Order table |

Both are DEV-ONLY demo credentials, same caveat as `admin123`. To watch
the gate rather than trust the unit test: `manage.py seed_demo`, log the
client in with `auditor`'s token, open Orders and select rows — the batch
button is gone. Switch to `admin` and it returns. `GET /api/me/` for each
answers `["auditors"]` vs `["auditors","managers"]` (+ `is_superuser`
false/true), which is the whole decision input — pinned by
`test_seed_demo_gives_a_nonsuperuser_single_role_holder`.

## The line that must not blur

Hiding is **UX, not security**. Every gate above is client-side; the
server stays the actual permission gate and re-validates every request.
A real deployment mirrors each role in DRF permission classes — the
reference actions deliberately stay open to any authenticated caller so
the rig keeps exercising the audit trail.

## Phase (b) — the activity screen

`app/src/pages/Activity.svelte` is a plain R-006 drop-in (one file, no
registry edit) reading the FR-R003 audit endpoint:

- resolved through `findAuditModel(schema)` → the schema-discovered
  `listPath` (byId first, then any model path ending `/audit/`), never a
  hand-written `/api/audit/`;
- newest-first pages with the server's `?object_type=` / `?object_id=`
  filters (docs/custom-actions.md);
- a backend without an audit model renders a friendly empty **naming the
  missing ViewSet** instead of 404ing a guessed URL.

## Copy checklist (client projects)

1. Add a read-only claims view (username + is_staff + is_superuser +
   sorted group names) and document it in the OpenAPI schema (GET only).
2. Optionally seed matching Groups; role names are the join key. Seed at
   least one NON-superuser holding exactly one of them, or the rejection
   path is undemonstrable — every real gate case you can click is an
   acceptance case.
3. Declare `roles` on pages/actions you want hidden; keep handlers
   server-validated anyway.
4. Nothing in `app/src/lib/*` needs editing — mePath discovery, claims
   store, sidebar/action gating and the Activity drop-in already ship.
