# admineverywhere (pip plugin)

Branding engine + schema tooling + runtime branding API for
[admineverywhere](../README.md), the admin app builder for Django REST
Framework backends. Install into your Django project:
`pip install admineverywhere`.

## Commands

- `python manage.py dump_schema` — emit the drf-spectacular OpenAPI
  schema the client renders its CRUD UI from.
- `python manage.py build_admin --brand <brand.json> --app <app-dir>` —
  inject one `brand.json` (colors, radius, font, logo, app name) into the
  Tauri/Svelte client: bundled static assets + `tauri.conf.json`
  productName/window title (the launcher identity for builds). On deploy
  builds, pass `--api-host https://admin.example.com` to substitute the
  production CSP's `https://API_HOST` placeholder with the real origin
  (validated: https, dotted DNS — localhost/wildcards rejected).

## Runtime branding API (brand the app from inside the app)

Wire two things and the thin client can rebrand itself live, no rebuild:

```python
# settings.py
INSTALLED_APPS = [..., "admineverywhere"]
ADMINEVERYWHERE_BRAND_DIR = BASE_DIR / "admineverywhere_brand"   # runtime store (gitignored)

# urls.py
path("admineverywhere/", include("admineverywhere.urls"))
```

Endpoints:

- `GET /admineverywhere/branding/` — public. Current brand + `rev`, or 404
  when none configured (client keeps its bundled static brand).
- `PUT /admineverywhere/branding/` — staff token required. Body = the
  `brand.json` closed schema; `logo`/`favicon` may be
  `data:image/(png|jpeg|svg+xml);base64,...` uploads (magic-byte
  checked, 1 MB cap). Replaces the brand; every client that boots (or
  polls) picks it up and re-themes instantly.
- `GET /admineverywhere/branding/asset/<relative-path>` — serves the stored
  logo/favicon. The path is the one `brand.json` carries, directory
  included (`assets/logo.svg`, exactly what `app/brands/*/brand.json`
  ships), so the URL the client is handed always addresses the file that
  exists. Names that climb out of the brand dir are refused: the view
  rejects `.`/`..`/empty segments, absolute paths and backslashes, and
  `realpath`+`commonpath` jail catches what a well-shaped name resolves to
  (a symlinked asset).

Everything is validated by the same closed schema as `build_admin`, and
every file operation is jailed inside the brand dir. Hosts without DRF
get a 501 on PUT (edit files + `build_admin` instead).

## Modules

- `admineverywhere.branding` — the branding engine (validated `brand.json` →
  CSS variables + asset copy), pure functions.
- `admineverywhere.brandstore` — the runtime brand store (read/validate/
  persist + data-URL decoding), file-backed.
- `admineverywhere.views` / `admineverywhere.urls` — the HTTP layer above.

Tests live in `tests/` — run them from a checkout per the root README.
