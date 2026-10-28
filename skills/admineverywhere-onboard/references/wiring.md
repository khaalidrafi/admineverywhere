# wiring.md — host-project wiring details (admineverywhere-onboard)

Read this when the basic four-line diff isn't enough: CORS, auth route
shapes, pagination, static schema serving, troubleshooting.

## settings.py — full picture

```python
INSTALLED_APPS = [
    # ... existing apps ...
    "admineverywhere",                       # branding engine + commands + API
]
ADMINEVERYWHERE_BRAND_DIR = BASE_DIR / "admineverywhere_brand"   # runtime brand store
```

Notes:

- `admineverywhere` needs `django.contrib.contenttypes` + `django.contrib.auth`
  in INSTALLED_APPS (they usually already are — the token auth needs
  them anyway). The plugin itself has no models and no migrations.
- `ADMINEVERYWHERE_BRAND_DIR` is optional; default is
  `<BASE_DIR>/admineverywhere_brand`. It's runtime state — gitignore it.
- DRF settings the thin client expects (defaults are usually right):
  `DEFAULT_AUTHENTICATION_CLASSES` including
  `rest_framework.authentication.TokenAuthentication`, page-number
  pagination, and `DEFAULT_SCHEMA_CLASS = "drf_spectacular.openapi.AutoSchema"`.

## urls.py — the routes

```python
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path("api/auth/token/", obtain_auth_token),           # client login
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[])),  # public!
    path("admineverywhere/", include("admineverywhere.urls")),      # runtime branding
    ...,
]
```

The schema route MUST be reachable without authentication — the client
renders the entire UI from it before/without a token. The per-model
endpoints behind it stay token-protected as the host configured them.

## CORS (dev: Vite on :5173, Tauri, packaged builds)

```python
INSTALLED_APPS += ["corsheaders"]
MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware", ...]
# DEV ONLY:
CORS_ALLOW_ALL_ORIGINS = True
# PROD: enumerate the origins you actually serve the client from
CORS_ALLOWED_ORIGINS = ["https://admin.example.com"]
```

In production serve the built web bundle from the same origin as the API
and CORS stops mattering.

## config.json (client side)

```json
{ "apiUrl": "http://127.0.0.1:8000", "authPath": "/api/auth/token/", "schemaPath": "/api/schema/" }
```

- `authPath`: any route that accepts `POST {username, password}` and
  returns `{"token": "..."}`. DRF authtoken's `obtain_auth_token` is the
  reference shape.
- `schemaPath`: the public drf-spectacular route.
- Users can override the API URL in the app's login screen — useful for
  packaged desktop/mobile builds pointing at their own deployment.

## Commands the skill relies on

| command | what it does |
| --- | --- |
| `manage.py build_admin --brand <brand.json> --app <dir> [--build]` | inject brand into the client (CSS vars, assets, productName/window title); `--build` also runs `npm run build` |
| `manage.py dump_schema` | capture the OpenAPI doc to a file (fixtures/tests) |
| `GET /admineverywhere/branding/` | current runtime brand (`404` = none configured → client uses its bundled static brand) |
| `PUT /admineverywhere/branding/` (staff token) | replace the runtime brand; body = brand.json schema, logo/favicon may be `data:` URLs |

## Troubleshooting

- **Client shows "Schema unavailable"** → check `schemaPath` in
  config.json vs the actual route; check the route is public
  (`permission_classes=[]`), check CORS in dev.
- **Login fails, 401/403** → `authPath` mismatch, or
  `rest_framework.authtoken` not in INSTALLED_APPS (token table missing
  → migrate).
- **PUT branding returns 401** → token must belong to a **staff** user.
- **PUT branding returns 501** → host has no DRF; edit brand files and
  run `build_admin` instead.
- **400 with `errors: [...]`** → closed-schema violations; fix the named
  fields (hex colors, radius format, unknown keys, oversized logos).
- **Android APK won't install over an existing one** → different signing
  key (debug keys differ per machine) — uninstall the old app first, or
  build with a stable committed key like the admineverywhere repo does.
- **FK dropdowns empty** → the schema must include the related model's
  list route; FKs are detected by name-matching in the schema.

## What NOT to do

- Don't run the host with `DEBUG=True` + `ALLOWED_HOSTS=["*"]` in any
  real deployment — onboarding should flag existing dev-only values
  loudly rather than silently inheriting them.
- Don't commit `admineverywhere_brand/` or `db.sqlite3`.
- Don't hardcode the brand into the client source — brand.json is the
  only place identity lives.
