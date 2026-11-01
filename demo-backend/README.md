# demo-backend — the admineverywhere demo rig

A self-contained Django shop (sqlite) that mirrors production
`shop/models.py` verbatim — including the BYTE-SACRED 11-state COD
order machine — so the plugin's generated clients (admin app, CLI, MCP,
Emacs) can be exercised end-to-end without touching real data.

**DEV-ONLY RIG.** Settings run `DEBUG=True`, `ALLOWED_HOSTS=['*']`,
`CORS_ALLOW_ALL_ORIGINS=True`. Serving invocations hard-exit without
the `DEMO_DEV=1` acknowledgement. Never deploy this rig.

## Boot

```bash
cd demo-backend
pip install -e ../plugin --no-deps   # the admineverywhere plugin package
pip install -r requirements.txt      # Django + DRF + spectacular + cors
export DEMO_DEV=1                    # required ack for any serving command
python manage.py migrate
python manage.py runserver 127.0.0.1:8017 --noreload
```

`/api/schema/` is the drift gate: the thin client's baked contract and
`/api/schema/` must move in lockstep (schema-drift test pins this).

## Seed

```bash
python manage.py seed_demo
```

Creates 5 categories, 22 products, 12 customers and 60 orders spread
over the last 14 days, walked across the REAL 11-state machine
(legal transitions only — every trail is checked by
`plugin/tests/test_seed_demo.py::test_every_seeded_trail_is_a_legal_walk_of_the_machine`),
plus per-transition history rows and audit entries.

The command is IDEMPOTENT (`help` promises it): re-running wipes the
seeded orders (history rides the cascade) and the audit log with them,
so no orphan rows survive — pinned by
`test_reseeding_does_not_accumulate_the_trail_or_the_log`.

## Demo accounts

| Account   | Password   | Scope                                              |
|-----------|------------|----------------------------------------------------|
| admin     | admin123   | superuser (DEV ONLY — sees everything, by bypass)  |
| auditor   | audit123   | Group `auditors` only — managers-gated surfaces hidden |
| manager   | manager123 | Group `managers` only — auditors-gated surfaces hidden |

The two non-superusers exist so client-side RBAC can be observed for
real: the harness `rbac_live_check` logs in as both and grades what the
server actually hides. Never reuse these passwords anywhere real.

## Reset

```bash
rm -f db.sqlite3
python manage.py migrate
python manage.py seed_demo
```

Nothing in the rig holds state outside `db.sqlite3`.
