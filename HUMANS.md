# HUMANS.md — admineverywhere (this repo's directory name is admincraft)

A guide for humans navigating and developing this codebase. Written
2026-11-18 per the org-wide rule that every agent-developed repo
carries one.

## What this is

A branded, extensible, AI-powered admin app builder for any Django
REST Framework backend, in two installable halves:

- **`plugin/`** — a pip-installable Django plugin (`admineverywhere`):
  branding plus schema tooling plus a runtime branding API, mounted on
  drf-spectacular OpenAPI schemas.
- **`app/`** — a Tauri 2 / Svelte 5 / Tailwind 4 thin client that
  renders the entire CRUD UI from that schema. Targets Android .apk,
  Windows .exe, Linux .AppImage.

The pitch: one `brand.json` rebrands the whole app in under a second,
and once the backend runs the plugin you can rebrand from INSIDE the
app (Settings -> Branding: name, colors, font, logo — applied live,
no rebuild). Release builds ship a neutral default identity that
every user replaces. An OpenAI-compatible streaming AI assistant
(Ctrl+K) knows your models. Two agent skills under `skills/`
(`admineverywhere-build`, `admineverywhere-onboard`) onboard an
existing repo and derive its branding automatically.

`demo-backend/` is a seeded Django 5 + DRF + drf-spectacular backend
with role-demo logins (admin/auditor/manager) so permission gates are
visibly testable.

## Mental model

The OpenAPI schema is the contract. The plugin exposes it (plus
branding + registration endpoints); the client derives every page,
widget and action from it; the AI assistant reads it to know the
models. Adding a model to the Django backend needs zero client work —
that is the whole point of "thin client".

Layout:

| Path | What it is |
|---|---|
| `plugin/src/admineverywhere/` | The Django plugin source (branding, schema tooling, agent embed, runtime API). The `.md` files beside the code are living design docs (rbac, custom-actions, django-parity, order-lifecycle...) — read the relevant one before touching that area. |
| `plugin/tests/` | The plugin's Python test suite. |
| `app/src/` | The Svelte 5 client: `pages/`, `components/`, `widgets/`, `actions/`, `ai/` (the assistant), `onboarding/`, `lib/`. |
| `app/brands/` | Brand definitions (e.g. `minimal-light/brand.json`). |
| `demo-backend/` | Seeded demo DRF backend (logins in README). |
| `skills/` | Two agent skills: build (branding craft) and onboard (wire an existing repo). |
| `docker/`, `flake.nix`, `guix.scm` | The build/packaging lanes. |
| `frontend-dist/` | Prebuilt client bundle for packaging lanes that do not run npm. |
| `agent-team/`, CHARTER.org, ROADLOG.org, HANDOFF.org | The agent-team state: the org chart (centralized tiers: Owner; EM; PA; specialists), the roadlog, handoffs. |
| `ci/` | The agent-team-ci kit submodule (laws, harness, guards). |

## Invariants and gotchas

- **Identity law (repo history)**: this repo's history was restored
  on 2026-11-18 after an org-wide rewrite that had absorbed Flash's
  commits into the Lead identity; attribution is sticky (Flash's
  commits stay Flash, the Lead never authors member work). The
  restored line is the truth — never rewrite it again.
- The client is THIN: business logic belongs in the plugin/backend.
  If you find yourself putting policy in Svelte, stop.
- Branding must be live-reloadable both ways (build-time brand.json
  AND in-app Settings); breaking one path breaks the demo pitch.
- Production CSP substitution: `--api-host https://...` (https only;
  localhost/wildcards rejected) when building a deploy bundle.
- The demo logins are load-bearing for manual testing (auditor vs
  manager vs superuser shows the RBAC gates); keep `seed_demo`
  producing all three roles.
- Every claim in agent work carries evidence (sha / command output /
  file:line) — "Done" without evidence is PENDING (CHARTER law).

## Developing

```bash
# Demo backend (Django 5 + DRF):
cd demo-backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt -e ../plugin
.venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo && .venv/bin/python manage.py runserver

# Client (vite dev; identical inside Tauri):
cd app && npm install && npm run dev

# Plugin tests:
cd plugin && python -m pytest tests/

# Build-time branding:
cd demo-backend && .venv/bin/python manage.py build_admin --brand ../app/brands/minimal-light/brand.json --app ../app
```

Branch law: work lands on `ai/main`. Team-file edits (board, roster,
STATE) go on the trunk; application work rides task branches.
