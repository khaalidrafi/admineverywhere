# admincraft (pip plugin)

Branding engine + schema tooling for [admincraft](../README.md), the
admin app builder for Django REST Framework backends. Install into your
Django project: `pip install admincraft`.

- `python manage.py dump_schema` — emit the drf-spectacular OpenAPI schema
  the client renders its CRUD UI from.
- `python manage.py build_admin --brand <brand.json> --app <app-dir>` —
  inject one `brand.json` (colors, radius, font, logo, app name) into the
  Tauri/Svelte client and rebuild its branded assets.
- `admincraft.branding` — the branding engine (validated `brand.json` →
  CSS variables + asset copy).

Tests live in `tests/` — run them from a checkout per the root README.
