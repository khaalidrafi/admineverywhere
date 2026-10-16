# django-ai-dashboard

A branded, extensible, AI-powered admin dashboard for any Django REST
Framework backend — pip-installable plugin (branding + schema tooling) plus a
Tauri 2 / Svelte 5 thin client that renders your entire CRUD UI from your
drf-spectacular OpenAPI schema. Includes an OpenAI-compatible streaming AI
assistant (Ctrl+K) that knows your models. One `brand.json` rebrands the whole
app in under a second. Ships as Android .apk, Windows .exe and Linux
.AppImage.

**Repo:** `khaalidrafi/django-ai-dashboard` · stack: Django plugin (pip) +
Tauri 2 + Svelte 5 + Tailwind 4 + DRF/drf-spectacular backend.

## Try it in 3 steps

```bash
# 1. Run the demo backend (Django 5 + DRF + drf-spectacular, seeded)
cd demo-backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt -e ../plugin
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo && .venv/bin/python manage.py runserver
#    (login: admin / admin123 · schema: http://localhost:8000/api/schema/)

# 2. Run the thin client (vite dev; works identically inside Tauri)
cd ../app && npm install && npm run dev            # -> http://localhost:5173

# 3. Rebrand it — edit app/brands/freshorama/brand.json (or use minimal-light), then:
cd ../demo-backend && .venv/bin/python manage.py build_admin --brand ../app/brands/minimal-light/brand.json --app ../app
```

Screenshot flow worth demoing: login → dashboard widgets (record counts,
14-day activity chart, daily quote) → Product table → New Order (FK
dropdowns + enum) → **Ctrl+K** → ask "what models do I have?" and watch it
stream. Then run the rebrand command above and reload — whole app, new
identity, one second.

## Layout

| dir | what |
| --- | --- |
| `plugin/` | pip package `django-ai-dashboard` — `build_admin` (brand injection), `dump_schema`, branding engine (29 pytest cases) |
| `app/` | Tauri 2 + Svelte 5 thin client — schema-driven CRUD, widgets, AI chat (27 vitest cases) |
| `demo-backend/` | realistic DRF backend exercising every field type (FK, enum, decimal, date, bool) |
| `app/brands/` | two example brands: dark SaaS (Freshorama) + light minimal (Ledgerly) |
| `.github/workflows/` | .exe/.AppImage + Android .apk builds (tag/dispatch only, no push CI) |

## Extending

- **New dashboard widget** = drop one `.svelte` file in `app/src/widgets/`
  with `<script module>export const meta = { title, size: 'sm'|'lg' }</script>`.
  No registration, no config.
- **New backend**: point `app/public/config.json` (or the API URL field on
  the login screen) at any DRF + drf-spectacular server using token auth.
- **AI provider**: any OpenAI-compatible endpoint (OpenAI, Groq, Ollama, LM
  Studio…) — set Base URL / key / model in the chat panel settings. The key
  goes to the OS keychain in the packaged app.

## Tests

```bash
cd app && npm test                    # 27 vitest (schema normalizer, SSE parser)
cd demo-backend && .venv/bin/python -m pytest ../plugin/tests   # 29 pytest
```

## Notes

- AI chat: streaming, no tool calling / history persistence (v2 material).
- Dev-only values in `demo-backend/` (CORS allow-all, DEBUG) — see
  `AI-REVIEW.org` before reusing anywhere.
- Placeholder icons are generated (`scripts/../gen_icon.py` +
  `npx tauri icon`); replace for client releases.
- Build desktop/mobile bundles: push a `v*` tag or run the GitHub workflows
  manually (`.github/workflows/`).
