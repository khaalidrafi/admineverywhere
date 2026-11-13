# DJANGO-ADMIN-PARITY — where admineverywhere stands against django.contrib.admin

Owner order 2026-11-13 (#freshorama): "the admineverywhere app MUST have the
ability to include ALL the features of django native admin." This document is
the honest census behind board row `django-admin-parity` (agent-team/TODOS.org)
and the slice ladder that closes the distance. It is re-measured on every
landed slice — statuses claim file paths, not intentions.

## The mapping rule

Django's admin is model-registry-driven; admineverywhere is schema-driven
(OpenAPI). A native-admin capability is delivered here as a GENERIC surface on
the model pages (`app/src/pages/ModelPage.svelte` + `DataTable` + `RecordForm`)
that lights up per model ONLY when the backend's document carries the
corresponding contract — the same evidence law as `exportPath` /
`transitionPath` / `historyPath`. The reference backend (`demo-backend/shop`)
ships the Django-side half of each contract.

## Census (measured 2026-11-13)

| django.contrib.admin capability | AE status | Where |
| --- | --- | --- |
| Auto model registration + CRUD | DONE (schema-driven) | `normalizeOpenAPI` → `ModelPage` create/edit/delete |
| Changelist search | DONE | `?search=` (`SearchableModelViewSet`, `ModelPage` search box) |
| Changelist pagination | DONE | DRF `PageNumberPagination` + pager |
| `list_editable`-style bulk actions w/ intermediate input | DONE (R-003) | `actions/` registry, confirm+input dialog, audit entries |
| `admin.actions.delete_selected` | DONE (parity slice 1) | selection bar → "Delete selected" (`ModelPage.onBulkDelete`) |
| Changelist column sorting (`ordering`) | DONE (parity slice 1) | `OrderingFilter` + documented `?ordering=` → sortable headers |
| Per-record object history | PARTIAL | R-001 lifecycle trail (`OrderHistory`); generic change-log below |
| `LogEntry` (all-changes object log) | MISSING → slice 5 | today only transitions + R-003 action audit |
| `list_filter` (facets sidebar) | MISSING → slice 2 | design: enum/bool/date fields per document |
| `date_hierarchy` drill-down | MISSING → slice 3 | design: datetime field per document |
| Inlines (related objects in the form) | MISSING → slice 4 | design: FK reverse sets per document |
| FK popup "+ Add related" | MISSING → slice 4 | today: dropdown from `fetchAllRecords` |
| `fieldsets` form grouping | MISSING → slice 7 | today: flat editable field list |
| Per-model permissions (add/change/delete/view) | PARTIAL | client RBAC (R-007) + server gates per endpoint; per-model CRUD enforcement → slice 6 |
| Admin index with recent actions | PARTIAL | Dashboard widgets + Activity page; per-model recent-actions panel not built |
| Theming/customization | EXCEEDS | branding pipeline (multi-brand, baked assets) |
| Auth integration | EXCEEDS | token auth + role claims (`/me/`) + onboarding |

## Slice ladder (each = board-dispatched, tested, reviewed)

1. ~~changelist sorting + delete-selected~~ — LANDED on
   `ai/django-admin-parity--gf_z.ai` (vitest 647/647, pytest 516 passed).
2. list-filter rail — enum/bool/date facets per document (codebuddy seat).
3. `date_hierarchy` drill-down (relief seat).
4. inlines + FK quick-create (codebuddy seat).
5. LogEntry-style object log — server middleware + FE history tab (qoder platform seat).
6. server-side per-model CRUD permission enforcement (completes R-007) (qoder platform seat).
7. fieldsets (relief seat).

A backend that documents none of the new contracts keeps today's UI — the
surface degrades silently, never guesses.
