# Django-admin feature parity — audit + wave-2 plan

Owner order 2026-11-08: "admineverywhere and our Freshorama admin apps MUST
contain all the features from Django's own admin. In admineverywhere, it
should be up to user choice." This is the working audit against Django 5's
`django.contrib.admin`. Status marks: ✅ shipped, 🟡 partial, ❌ missing.

## What Django's admin actually offers (the checklist)

| # | Django admin feature | admineverywhere / Freshorama admin | status |
|---|----------------------|-------------------------------------|--------|
| 1 | Auth: login/logout, password change/reset | token login + Sign out; NO self-service password change (needs a server endpoint contract) | ❌ (server-side gap) |
| 2 | Per-model list: search | DataTable search (client-side + agent server-side `?search=`) | 🟡 |
| 3 | Per-model list: filters (faceted, right rail) | absent — only column search | ❌ |
| 4 | Per-model list: date drill-down (date_hierarchy) | absent | ❌ |
| 5 | list_display links → change form | row click opens RecordForm | ✅ |
| 6 | Add / edit / delete per object | RecordForm + delete + RBAC | ✅ |
| 7 | Bulk actions (delete, custom) | bulk flag action + bulk delete; custom drop-in actions (`app/src/actions/`) | ✅ |
| 8 | Inlines (edit related objects on one form) | absent | ❌ |
| 9 | Object history | per-record history + append-only audit trail | ✅ (stronger than Django) |
| 10 | Recent actions (dashboard) | Activity screen (full audit, filters) | ✅ (stronger) |
| 11 | Log entries / admin logs API | audit model + agent `read_audit` tool | ✅ |
| 12 | Permissions per model/user/group (add/change/delete/view) | RBAC claims (FR-R007) driven by server `/me/`, server stays the gate | ✅ |
| 13 | "View on site" | n/a (admin app, not the site) | — |
| 14 | CSV/inline admin export | dual-layer CSV export (Django has none built-in) | ✅ (extra) |
| 15 | Widgets/reports beyond lists | Widget Studio + business reports (Freshorama) | ✅ (extra) |
| 16 | AI assistant / agent | chat + agent with confirm-gated actions | ✅ (extra) |
| 17 | Onboarding/tour | AI + classic tour (2026-11-08) | ✅ (extra) |
| 18 | Self-updater | GitHub releases + OAuth device flow (2026-11-08) | ✅ (extra) |

## Wave-2 work items (ordered by operator value)

1. **Faceted filters (the big Django win)** — a filter rail built from the
   OpenAPI schema's filter parameters (drf-spectacular emits them when the
   backend uses DjangoFilterBackend): enum selects, boolean tri-state, date
   ranges. Server-side query params; the agent's `list_records` already
   speaks that wire. Evidence-law: only filters the schema documents.
2. **Server-side search handoff** — pass the DataTable's search box to the
   documented `?search=` param when the schema lists it (fallback stays
   client-side).
3. **Date drill-down** — year/month/day chips from a schema-documented date
   filter; maps to Django's date_hierarchy UX.
4. **Inlines** — reverse-FK editing on RecordForm. Needs the schema to
   expose the child list endpoint per parent (drf-spectacular route
   patterns); without server evidence, stays out (no guessed URLs).
5. **Self-service password change** — needs a plugin endpoint contract
   (`POST /admineverywhere/password-change/`), then a form page + the
   agent keeps its hands off it.

## "In admineverywhere it should be up to user choice"

The parity surfaces (filters rail, date drill-down, inlines once they
exist) ship as per-page opt-ins: a model page declares `parity: ["filters",
"date_hierarchy", …]` in its meta; the stock default is ON for Freshorama
builds (MUST), OFF in the neutral admineverywhere brand until the builder
turns it on (`build_admin --parity filters,date_hierarchy` → inlined into
brand.gen config). Wave 2 lands the flags with the features.
