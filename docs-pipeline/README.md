# docs-pipeline — offline admin docs framework (admineverywhere)

Locked owner spec (2026-11-03): this repo carries the docs **framework
only**. The Emacs Org source of the admin docs lives in the
Freshorama/website repo under `docs/admin-docs/` (`setup.org` SETUPFILE +
`index.org` INCLUDE assembly, `emacs --batch` org-html export through
org-publish, see `scripts/build_admin_docs.sh` there). **Zero `.org` files
ever enter admineverywhere.**

Flow per release:

1. Freshorama side: `scripts/build_admin_docs.py` autogenerates `api.org`
   from the live OpenAPI schema and `admin-app.org` from the admin build
   facts; generate → review → finalize, then export HTML+index.
2. Hand the exported bundle to this repo at `docs-pipeline/incoming/`
   (`index.html` required, `docs.css` optional).
3. `./docs-pipeline/build_docs.sh` validates (no `.org` allowed) and
   installs the HTML into `app/public/docs/` — Vite bundles it and every
   Tauri release (APK + EXE) ships the docs fully offline.
4. Missing `incoming/` is not an error: docs are simply not refreshed that
   release.

The pipeline is enforced in the release workflow by calling
`docs-pipeline/build_docs.sh` before `npm run tauri build`.
