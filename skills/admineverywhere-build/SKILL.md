---
name: admineverywhere-build
description: Craft and brand an admineverywhere admin app — guided branding with the user, or fully automatic branding derived from the project's own source data. Use this skill whenever the user wants to "rebrand my admin app", "make the app mine", "change the app name / colors / logo / font", "brand the admin from inside the app", "craft an admin app for my project", "set the launcher name and icons", or asks about preparing a branded release of admineverywhere (APK / exe / AppImage / web). Covers the two branding layers: runtime (in-app editor + branding API: name, tagline, colors, font, logo, favicon, window title — applied live, no rebuild) and build-time (launcher/dock name + platform icons, set before packaging).
---

# admineverywhere-build — craft admin apps with the user's brand (or entirely from source)

## The one mental model: TWO branding layers

Everything the user sees splits into what can change **live** and what is
**baked into a build**. Get this right and every request has an obvious
home:

| what | layer | how it changes |
| --- | --- | --- |
| app name in UI, sidebar, login | **runtime** | in-app Branding editor, or `PUT /admineverywhere/branding/`, or `build_admin` |
| tagline, theme colors, font, radius | **runtime** | same |
| logo + favicon shown in-app | **runtime** | same (uploads validated: png/jpg/svg, magic bytes, 1 MB) |
| window title (desktop app) | **runtime** | follows the brand automatically (Tauri setTitle) |
| tab title / favicon (web) | **runtime** | follows the brand automatically |
| **launcher / home-screen name** | **build-time** | `productName` in `app/src-tauri/tauri.conf.json` — `build_admin` patches it from the brand's appName |
| launcher / dock / home-screen icons | **build-time** | regenerate: `npx tauri icon <1024px png>` in `app/` |
| app identity (Android applicationId, updater identity) | **build-time, near-permanent** | `identifier` — treat as immutable; changing it = a different installed app |

So: "brand it from inside the app" is fully supported for everything the
user sees *in* the app; the launcher name/icons for a shipped build come
from the same brand.json at package time. This is the flexibility the
product promises — never hardcode any product name into a release; the
default brand is neutral ("Admineverywhere") and each user's identity rides
on top.

## Modes: ASK vs AUTO

- **AUTO** — user says "just brand it", "all by itself", "use whatever
  my repo says", "don't ask". Run the derivation scripts against the
  project source, apply everything, report what was derived and applied.
- **ASK** (default) — collect the branding decisions in ONE batch:

  1. App name (propose: derived from pyproject/README, or current brand)
  2. Tagline (propose: derived, editable)
  3. Palette — dark or light, or custom primary/accent (propose: colors
     extracted from their SVG logo if present)
  4. Font — any real Google Font name (default Inter)
  5. Logo — a file they point to, or the generated neutral grid mark
  6. Launcher name for builds — same as app name? (it usually is)

  Then apply. One round, not six.

## The engine scripts

```bash
# 1. Map the repo: name candidates, logos, DRF readiness, model apps
python scripts/inspect_project.py --root <repo>

# 2. Derive a complete brand kit into <repo>/brand/
#    name ← --name > pyproject name > README title > "Admineverywhere"
#    tagline ← README first sentence; colors ← hex colors inside an SVG
#    logo; icons generated if the project has none
python scripts/derive_brand.py --root <repo> --out <repo>/brand \
    [--name "Freshorama"] [--tagline "..."] [--palette light] [--logo path]
```

Both are pure stdlib. `derive_brand.py` validates its own output against
the same closed schema the server enforces — if it prints errors, fix
the named fields; don't retry unchanged.

## Applying a brand

### A. Runtime, live (preferred for everything users see in-app)

With the host backend running (needs the admineverywhere plugin wired — see
the admineverywhere-onboard skill) and a staff token:

```bash
TOKEN=$(curl -s -X POST $API/api/auth/token/ -d "username=..&password=.." | jq -r .token)
curl -s -X PUT $API/admineverywhere/branding/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d @brand/brand.json
```

Or zero-curl, from the app itself: **Settings → Branding** in the sidebar
— live preview, color pickers, logo upload, validation errors from the
server rendered inline. Saving re-themes the running app instantly.

Assets: the API form wants `logo`/`favicon` as `data:` URLs (the editor
does this automatically); the server magic-byte-checks them and stores
them in its brand dir. Relative-path values must name files already on
the server.

### B. Build-time, committed (repo state + shipped launcher identity)

```bash
# from the host project (manage.py with admineverywhere installed):
python manage.py build_admin --brand brand/brand.json --app <path-to>/app
```

This writes the bundled static brand (`app/public/brand.{css,json}` +
logo/favicon copies) AND patches `tauri.conf.json` `productName` + window
title from the brand's appName. Do this before any `tauri build` /
release run so installers carry the right name.

### C. Launcher icons

```bash
# from app/ in the admineverywhere repo — regenerates every platform icon set
# (desktop icns/ico/png + android mipmaps) from one 1024px source:
npx tauri icon brand/assets/icon-1024.png
```

`derive_brand.py` already emits a 1024px source (`icon-1024.png`) — use
the project's real logo when they have one (any square PNG ≥ 512px).

### D. Cut a branded release (admineverywhere repo CI)

1. Bump `app/src-tauri/tauri.conf.json` `version` AND `plugin/pyproject.toml`
   `version` to match the tag.
2. Merge to the repo's default branch (CI runs the test gate first).
3. Push tag `vX.Y.Z` → the release job attaches web bundle, Windows
   setup.exe, Linux AppImage, universal Android APK (aarch64+armv7,
   stable committed debug key), Nix/Guix tarballs, plugin wheel + sdist,
   and SHA256SUMS to the GitHub Release.
4. Verify the release assets and that the APK reports the branded
   `productName`.

## Validation rules (closed schema — the server rejects everything else)

- `appName`: 1–120 chars, no path/Windows-title-hostile characters
- `tagline`: optional, ≤ 140 chars
- `colors`: exactly primary/accent/bg/surface/text, 6-digit hex
- `radius`: CSS length (`0.75rem`, `12px`)
- `font`: plain Google Font name (letters, digits, spaces)
- `logo`/`favicon`: repo-relative paths inside the brand folder, or data
  URLs (png/jpeg/svg only, ≤ 1 MB, magic bytes verified)
- unknown keys anywhere = config error, reported, rejected

When a save fails, the response carries `errors: [...]` with one message
per problem — show them all at once, fix them all at once.

## Guardrails

- **Never** change `identifier` casually: Android treats a new
  applicationId as a different app (parallel install, data "loss").
- Release builds must never carry a demo/product name — the neutral
  default is "Admineverywhere"; user brands ride on top, in the repo's brand
  files or their backend's brand store, not in the generic source.
- Fonts must be real Google Fonts names (the CSS imports them).
- Don't fight the closed schema; it's the security posture (brand.json
  is untrusted input — path-jail + magic-byte checks live server-side).
- Keep `app/src-tauri/Cargo.lock` in sync when `Cargo.toml` changes.
- If the user wants per-user or per-tenant branding at runtime, that's
  the same runtime API — brand.json is the *deployed default*, the
  editor/API is the *live override* layer.
