# FR-R007 — RBAC, phased (client-side first)

ROADLOG R-007 in two halves, both reference implementations in the demo
rig (`demo-backend/`), both contract-tested (`plugin/tests/test_rbac_roles.py`
+ `app/src/lib/__tests__/rbac.test.ts` + the rendered gate in
`app/src/lib/__tests__/rbacNavMount.test.ts`).

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

    export const meta = { title: "Modules", path: "/modules",
                          nav: "main", roles: ["managers"] };   // optional

`Sidebar.svelte:20` (`mainNav`) and `Sidebar.svelte:21` (`settingsNav`) hide a
`roles`-declared entry unless the caller holds at least one of them; superusers
see everything. An invalid `roles` declaration is **refused** into `refusedPages`
with a nameable reason — never half-registered (the R-006 refusal law).

That hiding is graded by the DOM, not by the comment above
(`app/src/lib/__tests__/rbacNavMount.test.ts`, 9 tests). Measured before the
harness existed: deleting **both** `roleAllows` filters from `Sidebar.svelte`
— removing the entire nav half of FR-R007 — left the shipped suite answering
`463 passed / 37 files`, rc 0. The reason was structural, not accidental: no
shipped page declared `roles` then, so every real-glob render (`navMount.test.ts`,
`shell.test.ts`) is an unfiltered render and agrees with a gate that hides
nothing, while `rbac.test.ts` graded only the pure function and the registry's
handling of the field. (That blank is what the section below closes: the
reference app now carries a gated page in each nav group, asserted over the
shipped glob.) The harness therefore feeds the REAL `collectPages`
validation a fixture that the glob cannot produce, and asserts an EXACT rendered
button set per claims state:

| claims | what the sidebar must render |
| --- | --- |
| `null` (no `/me/` in the schema, or the read failed) | the whole declared nav — plain DRF keeps everything |
| a single-role caller | ungated entries + their own entry + the entry listing their role among several |
| a caller holding none of the declared roles | the ungated entries only, and NO empty Settings frame |
| a superuser with zero role groups | everything (the short-circuit that forces `seed_demo` to add a non-superuser) |

plus three things a set-per-state table cannot say: the gate is **live** (claims
changing after mount re-render the nav, and `logout()` clears claims, which means
filtering NOTHING — a menu still hidden after sign-out is "hiding is security" in
the wrong direction); a gated entry that IS shown still routes to the href IT
DECLARED (the gate changes visibility, never the address); and a refused `roles`
declaration renders no button in any claims state while its reason stays
nameable. Population is pinned first (six accepted nav pages, four of them
role-gated), because an exact set over a fixture whose `roles` key silently
stopped reaching the registry would otherwise agree with an unfiltered render
(DEVGUIDE *ELEVENTH harness law*). Eleven mutants of the shipped sources
(`Sidebar.svelte`, `rbac.ts`, `lib/pages/index.ts`, `stores.ts`) — each filter
deleted, claims ignored, `!claims` hiding everything, superuser short-circuit
gone, `some`→`every`, ungated entries hidden, the `roles` hand-off dropped, a
malformed list registered instead of refused, the empty Settings frame forced,
logout keeping stale claims — every one KILLED, sources restored
byte-identical (md5 verified). Four of them (`mainNav` filter, `settingsNav`
filter, stale-`null` claims, forced Settings frame) are killed ONLY here; the
rest the shipped files catch as well.

The reference app declares the gate in **both** nav groups, because gating
one group alone leaves the other filtering leg graded by vacuous truth:

| page | group | gate | who loses it, live |
| --- | --- | --- | --- |
| `Modules.svelte` | main | `["managers"]` | `auditor` — the registry inspector is an onboarding/admin surface |
| `Branding.svelte` | settings | `["managers"]` | `auditor` — brand PUT is staff-only server-side, so the editor would only 403 |

### The registry inspector does not leak the click

`Modules.svelte` lists what the glob registered — that is its whole job — so
a gated page keeps its **row**. What it must not keep is the **Open
button**: the screen runs the same `roleAllows()` decision as the sidebar, so
a caller the gate excludes sees the row annotated `gated · <roles>` and gets
no button. Hiding the row would destroy the diagnostic; leaving the button
would hand out, on a self-documenting screen, the navigation the sidebar
withheld.

### Proof

`app/src/lib/__tests__/rbac.test.ts` mounts the REAL `Sidebar` and the REAL
`Modules` screen over the shipped glob, with the two captured live `/api/me/`
bodies plus a managers holder and `claims = null`, and asserts each rendered
group is **exactly** what `roleAllows` declares (both directions, four claims
states) — the population leg pins that a gated entry exists in EACH group, so
a deleted declaration is red rather than quietly narrowing the domain.
Eight mutants were killed against it (sources restored byte-identical, md5
re-checked after every one): settings filter removed, main filter removed,
Modules hands the Open button anyway, Modules hides the row instead of the
click, the gate reason names no role, `roleAllows` filters a no-claims
backend, the shipped `roles` declaration deleted, and the gate switched to a
role the seeded auditor already holds.

### Gating an action

`meta.roles: ["managers"]` on an action file (`bulk_flag.ts` is the
reference) removes the button from DataTable/ModelPage for callers who
do not hold the role.

### Demo users (what `seed_demo` gives you)

| login | who they are | what the gate does |
| --- | --- | --- |
| `admin` / `admin123` | superuser, holds `auditors` + `managers` | sees **everything** — superuser short-circuits `roleAllows()` |
| `auditor` / `audit123` | non-staff, non-superuser, holds `auditors` **only** | the **rejection** path, live: the managers-only "Flag batch" button is absent from the Order table, and the **Modules** and **Branding** entries are absent from the sidebar (one per nav group) |

Both are DEV-ONLY demo credentials, same caveat as `admin123`. To watch
the gate rather than trust the unit test: `manage.py seed_demo`, log the
client in with `auditor`'s token, open Orders and select rows — the batch
button is gone; look at the sidebar — no Modules, no Branding (typing
`#/modules` by hand still paints the inspector, and there both rows are
marked `gated` with no Open button).
Switch to `admin` and everything returns. `GET /api/me/` for each
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
4. Gate at least one entry in EVERY nav group you render. A gate that only
   exists in the settings block leaves the main-group filter unexercised —
   exactly the mutant that survived the first draft of this harness.
5. Any self-documenting screen that lists registered modules must run its
   own click through the same `roleAllows()` decision, or it leaks the
   navigation the sidebar withheld. List the row, withhold the button.
6. Nothing in `app/src/lib/*` needs editing — mePath discovery, claims
   store, sidebar/action gating and the Activity drop-in already ship.
7. If you add a gated page, add it to the fixture in
   `app/src/lib/__tests__/rbacNavMount.test.ts` and say which claims state must
   hide it. A gate nobody can render is a gate nobody can review — the shipped
   suite stayed green over the deleted `Sidebar.svelte` filters precisely because
   no declaration in the glob carried a role.
