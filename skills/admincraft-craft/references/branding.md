# branding.md — brand.json schema, runtime API contract, launcher matrix

Deep reference for the craft skill. Read when a branding task needs the
exact contract, the launcher/platform matrix, or the release checklist.

## brand.json — closed schema (validated identically client-side, CLI-side and server-side)

```json
{
  "appName": "Freshorama Admin",     // 1–120 chars, title-safe charset
  "tagline": "Manage everything, beautifully",   // optional, <= 140 chars
  "logo": "assets/logo.svg",         // optional; relative to the brand dir
  "favicon": "assets/icon.png",      // optional; relative to the brand dir
  "colors": {
    "primary": "#7c3aed",            // buttons, links, active nav
    "accent":  "#06b6d4",            // highlights, charts
    "bg":      "#0f172a",            // app background
    "surface": "#1e293b",            // cards, sidebar, tables
    "text":    "#f1f5f9"             // all text
  },
  "radius": "0.75rem",               // CSS length (px|rem|em)
  "font": "Inter"                    // a REAL Google Font name
}
```

Unknown top-level or colors keys are REJECTED (closed schema — typos and
config drift fail loudly). Asset paths must stay inside the brand folder
(`../`, absolute paths, backslashes rejected; symlink escapes blocked by
realpath+commonpath jailing on every read/write).

## How the identity flows

```
brand.json ──manage.py build_admin──> app/public/brand.css + brand.json + assets
                │                        (bundled static: first paint, no FOUC)
                └──patches──>         src-tauri/tauri.conf.json productName/title
                                            (launcher identity for builds)

backend brand dir (ADMINCRAFT_BRAND_DIR)
   └──GET/PUT /admincraft/branding/  (staff for PUT)
          └── client applies live: --brand-* CSS vars, titles, favicon,
              logos, native window title (Tauri setTitle)
```

The client boots with the bundled static brand, then (if the API runs
the admincraft plugin) the server brand replaces it. A plain DRF backend
without the plugin keeps the bundled brand — degrades silently.

## Runtime API contract

```
GET  <api>/admincraft/branding/
     → 200 {"brand": {...same schema, logo/favicon as API-relative
                      /admincraft/branding/asset/<relative-path> URLs...}, "rev": <int>}
     → 404 {"detail": "no brand configured — ..."}      # use bundled brand

PUT  <api>/admincraft/branding/      Authorization: Token <staff token>
     body: the brand object; logo/favicon may be
       "data:image/png;base64,..." | "data:image/jpeg;base64,..." |
       "data:image/svg+xml;base64,..." | a relative asset path already on the
       server (directory included — the SAME string the GET handed back)
     → 200 same shape as GET     400 {"errors": ["field: problem", ...]}
     401 no/bad token            403 non-staff        501 host has no DRF

GET  <api>/admincraft/branding/asset/<relative-path>
     → the logo/favicon bytes
     (png/jpeg/svg content-types; the path is exactly what brand.json
      stores — "assets/logo.svg" keeps its directory — and only files
      inside the brand dir are ever served)
```

Upload limits: 1 MB per asset, magic-byte verification (a PNG must
actually start with the PNG signature, etc.). `rev` advances on every
save (mtime+1) — clients can poll to detect remote rebrands.

## Launcher / platform matrix (build-time)

| platform | name shown | icons | where it comes from |
| --- | --- | --- | --- |
| Windows (NSIS exe) | productName | `icons/icon.ico` + Square*.png | tauri.conf.json + icons/ |
| Linux (AppImage) | productName + .desktop Name | 128x128 etc. | same |
| Android (APK) | app label (launcher, settings) | mipmap-* ic_launcher* | productName at build; icons regenerated via `npx tauri icon` |
| macOS | dock/menu name | icns | same (identifier = stable identity) |
| Web bundle | `<title>` + favicon | public/icon.png | runtime brand overrides live |

Key facts:

- The Android **label is static per build** — runtime rebrands change
  everything inside the app but not the home-screen label; the next
  built release picks up the new productName automatically.
- `identifier` (e.g. `com.example.admin`) is the app's permanent identity
  — Android treats a change as a different app (parallel install, no
  data migration). Choose once, keep forever.
- The admincraft release pipeline signs the universal APK with a stable
  committed debug key so successive releases install over each other.
  A locally-built APK (random debug keystore) will NOT install over a
  release APK — "app not installed" on Android is almost always this
  (signature mismatch), or a versionCode downgrade. Fix: uninstall the
  old one, or build with the same key.

## Icon regeneration

```bash
# from app/ — one source to rule them all (writes every platform icon):
npx tauri icon brand/assets/icon-1024.png

# no logo yet? generate a neutral 2x2 grid mark in the brand's colors:
python skills/admincraft-craft/scripts/derive_brand.py --root . --out brand
```

Source requirements: square PNG, >= 512px (1024 recommended),
transparent background works.

## Release checklist (admincraft repo)

1. Gates green locally: `pytest plugin/tests` (from demo-backend venv),
   `vitest run` in app/.
2. Bump BOTH versions: `app/src-tauri/tauri.conf.json` → `version`,
   `plugin/pyproject.toml` → `version`. Keep them equal to the tag.
3. Commit/merge to the default branch — CI runs the test gate before
   any build leg spends minutes.
4. Tag `vX.Y.Z` and push — the release job attaches: web tarball,
   x64-setup.exe, amd64 AppImage, universal Android APK, nix/guix
   tarballs, plugin wheel + sdist, SHA256SUMS.
5. Post-verify: release assets present; APK filename + installed label
   carry the branded productName; SHA256SUMS match.

## Design guidance for ASK mode

- Dark palette (bg `#0f172a`-ish) reads "ops console"; light
  (`#faf9f7`-ish) reads "team tool". Match the user's existing site.
- primary = interactive color (buttons/links); accent = data/charts.
  Keep 4.5:1 contrast of text on bg — the editor's swatch row previews it.
- The generated grid mark is deliberately generic — encourage a real
  logo when the project has one; SVG is preferred (scales, tiny, and
  derive_brand.py can lift its colors automatically).
