---
name: admineverywhere-onboard
description: Wire an existing Django/DRF repository onto admineverywhere — the pip-installable plugin (branding engine + runtime branding API) plus the Tauri 2/Svelte 5 thin-client admin that renders CRUD from any drf-spectacular OpenAPI schema. Use this skill whenever the user wants to "onboard/adopt/integrate admineverywhere" into a repo, "add an admin app to my Django REST API", "prepare my repo for admineverywhere", "set up the admineverywhere plugin", or mentions giving an existing DRF backend an admin client. Covers: installing the plugin, wiring settings.py/urls.py, choosing the brand (guided or derived automatically from the project's own source), pointing the thin client at the API, and verifying the whole chain with curl.
---

# admineverywhere-onboard — prepare an existing repo for admineverywhere

## What you are building

admineverywhere is split in two, and this skill touches both sides:

- **Server side (the repo you're onboarding):** the `admineverywhere` pip package
  (Django plugin) — branding engine, `build_admin`/`dump_schema` management
  commands, and the runtime branding API (`GET/PUT /admineverywhere/branding/`).
  The host keeps doing what it already does: DRF endpoints + token auth +
  a public drf-spectacular schema.
- **Client side (the admin app users launch):** a Tauri 2 / Svelte 5 thin
  client that reads the OpenAPI schema at runtime and renders the whole
  CRUD admin, dashboard widgets and an OpenAI-compatible chat. It lives in
  the admineverywhere repo (`app/`) or as a release bundle — you point it at
  the API via one `config.json`.

The thin client needs exactly three things from the host: a token-auth
login route, a public schema route, and CORS for the client's origin.
Everything else is optional.

## Modes: ASK vs AUTO

Pick the mode from the user's phrasing (say which one you chose):

- **AUTO** — "just do it", "all by yourself", "don't ask me", "figure it
  out", or the user is clearly hands-off. Derive every choice from the
  project's own source (scripts below), apply, and report a diff-style
  summary at the end. Still surface anything genuinely dangerous.
- **ASK** (default) — show the derived proposal first and confirm the
  decisions that are hard to undo: the app name, the brand identity, and
  any settings.py edit. Batch the questions into ONE compact list; don't
  drip them one at a time.

Never ask about things that have only one sane answer (e.g. "should I
add admineverywhere to INSTALLED_APPS?").

## Workflow

### 1. Scan the repo

```bash
python scripts/inspect_project.py --root <repo>
```

Read the manifest before touching anything. It tells you: where
`manage.py`/settings live, whether DRF + drf-spectacular + authtoken are
installed, the project's name candidates, logo candidates, and which
Django apps have models (those become the admin's nav).

If the manifest says `is_django: false` → stop and tell the user
admineverywhere needs a Django REST Framework backend; don't improvise.

### 2. Check the three prerequisites

| need | why | fix if missing |
| --- | --- | --- |
| `rest_framework` | the client speaks DRF (token auth, pagination, validation errors) | `pip install djangorestframework` + INSTALLED_APPS |
| `drf_spectacular` | the entire UI is generated from the OpenAPI schema | `pip install drf-spectacular` + INSTALLED_APPS + serve the schema publicly |
| token auth | login flow (POST username/password → token) | `rest_framework.authtoken` + `path("api/auth/token/", obtain_auth_token)` |

Missing pieces are normal — propose the exact edits and apply them (ASK
mode: one confirmation for the settings.py diff).

### 3. Install the plugin

```bash
pip install admineverywhere                # from the GitHub release wheel
# or, from a checkout of the admineverywhere repo:
pip install -e /path/to/admineverywhere/plugin
```

### 4. Wire the host (exact diff)

```python
# settings.py
INSTALLED_APPS = [..., "admineverywhere"]
ADMINEVERYWHERE_BRAND_DIR = BASE_DIR / "admineverywhere_brand"   # runtime brand store

# urls.py
from django.urls import include, path
urlpatterns = [
    ...,
    path("admineverywhere/", include("admineverywhere.urls")),   # runtime branding API
]
```

Details and troubleshooting (CORS for the client origin, pagination,
auth route shapes): **references/wiring.md**.

### 5. Brand it

- **AUTO:** `python scripts/derive_brand.py --root <repo> --out <repo>/brand`
  → complete brand kit (name from pyproject/README, tagline, colors —
  extracted from an SVG logo if one exists, generated grid-mark icons if
  not). Inspect `brand/brand.json` and mention the chosen name in your
  report.
- **ASK:** run the same script to get a *proposal*, then present its
  choices (name / tagline / palette / logo) as one confirmation round and
  pass the overrides via flags (`--name`, `--tagline`, `--palette light`,
  `--logo path`).

### 6. Point the client at this API

If the admineverywhere repo is available locally:

```bash
# 1. configure + inject the brand into the client bundle
python manage.py build_admin --brand <repo>/brand/brand.json --app <admineverywhere>/app
# 2. edit <admineverywhere>/app/public/config.json:
{ "apiUrl": "http://127.0.0.1:8000", "authPath": "/api/auth/token/", "schemaPath": "/api/schema/" }
# 3. run it
cd <admineverywhere>/app && npm install && npm run dev     # browser mode is feature-identical
```

The three paths in `config.json` must match the host's actual routes —
the manifest's `urlconf_files` tells you where to check.

### 7. Verify the whole chain (curl, before any UI work)

```bash
curl -s $API/api/schema/ | head -c 200          # OpenAPI JSON
curl -s -X POST $API/api/auth/token/ -d "username=...&password=..."   # token
curl -s $API/admineverywhere/branding/               # 404 = fine (no runtime brand yet)
```

### 8. Report

A compact table: what was detected, what was installed, what was edited
(file:line), the brand chosen, and the exact commands to run the client.
Call out anything the user must do themselves (superuser creation,
CORS/ALLOWED_HOSTS for their deployment, HTTPS in production).

## Guardrails

- Never commit runtime state: `admineverywhere_brand/`, `db.sqlite3`.
- Don't touch business code — settings.py, urls.py, requirements only.
- If the host has `DEBUG=False`, the schema route must still be public
  (the client needs it to render anything) — flag the security tradeoff
  explicitly and let the user decide.
- Version pins: Django >= 4.2, DRF >= 3.14.
- The server validates every brand write against a closed schema — when
  a PUT is rejected, fix the listed field problems; don't retry blindly.
