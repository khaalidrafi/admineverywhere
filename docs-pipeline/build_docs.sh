#!/usr/bin/env bash
# build_docs.sh — admineverywhere docs pipeline (FRAMEWORK ONLY).
#
# CONTRACT (owner-locked 2026-11-03):
#   - The Emacs Org SOURCE of the admin docs lives in the Freshorama/website
#     repo (docs/admin-docs/*.org). THIS REPO NEVER STORES .org FILES.
#   - The Freshorama side exports HTML+index (emacs --batch org-html via
#     org-publish; scripts/build_admin_docs.sh there) and hands the exported
#     bundle to this repo at docs-pipeline/incoming/.
#   - This script validates the incoming bundle and copies it into
#     app/public/docs/ so Vite bundles it and every Tauri release (APK/EXE)
#     ships the docs offline. Run it BEFORE `npm run tauri build`.
#   - If docs-pipeline/incoming/ is absent, the app still builds; docs are
#     simply not refreshed this release.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$(cd "$HERE/../app" && pwd)"
INCOMING="$HERE/incoming"
DEST="$APP/public/docs"

if [ ! -s "$INCOMING/index.html" ]; then
  echo "[docs-pipeline] no incoming docs bundle — skipping (docs unchanged)"
  exit 0
fi

python3 - "$INCOMING" <<'EOF'
import json, os, sys
incoming = sys.argv[1]
manifest_path = os.path.join(os.path.dirname(incoming), "manifest.json")
required, optional = ["index.html"], []
if os.path.exists(manifest_path):
    m = json.load(open(manifest_path))
    required = m.get("required_files", required)
    optional = m.get("optional_files", [])
missing = [f for f in required if not os.path.exists(os.path.join(incoming, f))]
if missing:
    sys.exit(f"[docs-pipeline] FAIL: incoming bundle missing {missing}")
for f in optional:
    if not os.path.exists(os.path.join(incoming, f)):
        print(f"[docs-pipeline] note: optional file absent: {f}")
bad = [f for f in os.listdir(incoming) if f.endswith(".org")]
if bad:
    sys.exit(f"[docs-pipeline] FAIL: .org files must never cross into AE: {bad}")
print("[docs-pipeline] incoming bundle valid:", os.listdir(incoming))
EOF

mkdir -p "$DEST"
cp -f "$INCOMING/"*.html "$DEST/"
if [ -f "$INCOMING/docs.css" ]; then cp -f "$INCOMING/docs.css" "$DEST/"; fi
echo "[docs-pipeline] docs installed -> $DEST ($(ls "$DEST" | tr '\n' ' '))"
