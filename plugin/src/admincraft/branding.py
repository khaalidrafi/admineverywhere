"""Branding engine — pure functions, no Django, fully unit-tested.

The promise: `build_admin --brand path/brand.json` rebrands the whole app
in <30s. Everything visual in the thin client reads CSS variables
(--brand-*) emitted here, so this is the ONLY file that decides what the
app looks like.

Public API (imported by the management commands):
    load_brand(path) -> dict
    validate_brand(brand) -> list[str]      # empty list = valid
    render_css(brand) -> str
    inject_brand(app_dir, brand_path) -> dict   # summary of written files

Security posture (P0): brand.json is UNTRUSTED input. validate_brand
enforces a closed schema (unknown keys/types/values rejected with clear
errors) and inject_brand jails every read and write with realpath()+
commonpath() so "../" chains, absolute-path injection and symlink escapes
cannot leave the brand or app directories.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen  # noqa: F401 (dump_schema monkeypatches urlopen)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
RADIUS_RE = re.compile(r"^\d+(\.\d+)?(px|rem|em)$")
# appName goes into window titles / file paths downstream: keep it boring
SAFE_NAME_RE = re.compile(r"^[^/\\<>:\"|?*\x00-\x1f]{1,120}$")

REQUIRED_KEYS = ["appName", "colors", "radius", "font"]
REQUIRED_COLORS = ["primary", "accent", "bg", "surface", "text"]

# Font names are interpolated into a URL + CSS string: strip anything
# that could break out of the quotes/url.
SAFE_FONT_RE = re.compile(r"^[A-Za-z0-9 ]{1,60}$")

# P0: brand.json is untrusted input (shared/downloaded/dropped in) — the
# schema is CLOSED. Every key must be known and correctly typed; anything
# else is a config error and must fail loudly, not be silently ignored.
ALLOWED_KEYS = frozenset(REQUIRED_KEYS + ["tagline", "logo", "favicon"])
ALLOWED_COLOR_KEYS = frozenset(REQUIRED_COLORS)
TAGLINE_MAX = 140      # tagline is UI chrome, not a paragraph
ASSET_PATH_MAX = 200   # logo/favicon live next to brand.json in the repo


def load_brand(path: str | Path) -> dict:
    """Read brand.json; raise FileNotFoundError / ValueError with clear text."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"brand file not found: {p}")
    try:
        brand = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {p}: {exc}") from exc
    if not isinstance(brand, dict):
        raise ValueError(f"{p} must contain a JSON object")
    return brand


def _escapes_brand_folder(rel: str) -> bool:
    """True when an asset path is absolute or climbs out of the brand folder.

    PurePosixPath judges the JSON spelling ('/'-separated), not the host OS;
    backslashes are rejected outright — Windows-style traversal has no
    legitimate use in a brand.json.
    """
    p = PurePosixPath(rel)
    return p.is_absolute() or ".." in p.parts or "\\" in rel


# ---------------------------------------------------------------------------
# P0: path jail. Every file read/write in this module resolves its target
# through realpath() (symlinks included) and verifies with commonpath()
# that it stays inside the intended directory. Blocks:
#   - "../" chains hidden in brand.json asset paths
#   - absolute-path injection ("logo": "/etc/passwd")
#   - symlink escapes (a planted public/brand.css -> ~/.bashrc would
#     otherwise be clobbered through the link; an asset symlinking to
#     files outside the brand folder would otherwise be exfiltrated)
# Callers MUST use the returned (resolved) path for the actual operation,
# so what was validated is exactly what gets read/written.
# ---------------------------------------------------------------------------

def _jailed(base: str | Path, rel: str | Path, what: str) -> Path:
    """Resolve ``base / rel`` and guarantee the result stays under ``base``.

    Raises ValueError with a clear message on any escape. ``rel`` may be
    absolute — it only survives if it already resolves inside ``base``.
    """
    base_real = Path(os.path.realpath(base))
    candidate = Path(rel)
    joined = candidate if candidate.is_absolute() else base_real / candidate
    target_real = Path(os.path.realpath(joined))
    try:
        inside = os.path.commonpath([str(base_real), str(target_real)]) == str(base_real)
    except ValueError:  # mixed forms / different drives — treat as escape
        inside = False
    if not inside or target_real == base_real:
        raise ValueError(
            f"{what}: path escapes {base_real} ({str(rel)!r}) — "
            "refusing to read/write outside the intended directory"
        )
    return target_real


def validate_brand(brand: dict) -> list[str]:
    """Collect ALL problems (never early-return) so clients fix in one pass."""
    errors: list[str] = []

    app_name = brand.get("appName")
    if not isinstance(app_name, str) or not app_name.strip():
        errors.append("appName: must be a non-empty string")
    elif not SAFE_NAME_RE.match(app_name.strip()):
        errors.append("appName: contains characters not safe for window titles")

    # P0: closed schema — unknown keys are typos/config drift; fail loudly
    # instead of silently ignoring them.
    unknown = sorted(set(brand) - ALLOWED_KEYS)
    if unknown:
        errors.append(
            f"unknown keys: {', '.join(unknown)} (allowed: {', '.join(sorted(ALLOWED_KEYS))})"
        )

    # tagline: optional, but must be a short sane string when present.
    tagline = brand.get("tagline")
    if tagline is not None:
        if not isinstance(tagline, str) or not tagline.strip():
            errors.append(f"tagline: must be a non-empty string (got {tagline!r})")
        elif len(tagline) > TAGLINE_MAX:
            errors.append(f"tagline: longer than {TAGLINE_MAX} characters (got {len(tagline)})")

    # logo/favicon: relative asset paths only. Absolute paths and ".."
    # components are rejected here, and re-checked with realpath at copy
    # time (see _jailed) — belt and suspenders.
    for key in ("logo", "favicon"):
        rel = brand.get(key)
        if rel is None:
            continue
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"{key}: must be a relative path string like 'assets/logo.svg' (got {rel!r})")
        elif len(rel) > ASSET_PATH_MAX:
            errors.append(f"{key}: path longer than {ASSET_PATH_MAX} characters")
        elif _escapes_brand_folder(rel):
            errors.append(f"{key}: must stay inside the brand folder — no absolute paths or '..' (got {rel!r})")

    colors = brand.get("colors")
    if not isinstance(colors, dict):
        errors.append("colors: must be an object")
        colors = {}
    else:
        # P0: closed schema for colors too — unknown keys are drift.
        unknown_colors = sorted(set(colors) - ALLOWED_COLOR_KEYS)
        if unknown_colors:
            errors.append(
                f"colors: unknown keys {', '.join(unknown_colors)} "
                f"(allowed: {', '.join(sorted(ALLOWED_COLOR_KEYS))})"
            )
    for key in REQUIRED_COLORS:
        val = colors.get(key)
        if not isinstance(val, str) or not HEX_RE.match(val):
            errors.append(f"colors.{key}: must be a 6-digit hex color like #7c3aed (got {val!r})")

    radius = brand.get("radius")
    if not isinstance(radius, str) or not RADIUS_RE.match(radius):
        errors.append(f"radius: must be a CSS length like '0.75rem' or '12px' (got {radius!r})")

    font = brand.get("font")
    if not isinstance(font, str) or not SAFE_FONT_RE.match(font.strip()):
        errors.append(f"font: must be a plain Google Font name like 'Inter' (got {font!r})")

    return errors


def render_css(brand: dict) -> str:
    """brand.json -> CSS custom properties on :root (+ Google Font import)."""
    colors = brand["colors"]
    font = brand["font"].strip()
    import_name = font.replace(" ", "+")
    return f"""/* GENERATED by admincraft build_admin — do not edit by hand.
 * Regenerate with: python manage.py build_admin --brand <brand.json>
 */
@import url('https://fonts.googleapis.com/css2?family={import_name}:wght@400;500;600;700&display=swap');

:root {{
  --brand-primary: {colors['primary']};
  --brand-accent: {colors['accent']};
  --brand-bg: {colors['bg']};
  --brand-surface: {colors['surface']};
  --brand-text: {colors['text']};
  --brand-radius: {brand['radius']};
  --brand-font: '{font}', ui-sans-serif, system-ui, sans-serif;
}}
"""


def inject_brand(app_dir: str | Path, brand_path: str | Path) -> dict:
    """Apply a brand to the thin-client app directory.

    Writes:  public/brand.css, public/brand.json (normalized asset paths)
    Copies:  logo + favicon -> public/
    Patches: src-tauri/tauri.conf.json (productName, window title) if present

    P0: brand.json is untrusted — every source and destination below goes
    through _jailed() (realpath + commonpath), so neither hostile asset
    references nor symlinks planted inside the app can read or write
    outside the intended directories.

    Returns a summary {"written": [...], "copied": [...], "patched": [...]}
    that the build_admin command prints.
    """
    app = Path(app_dir)
    brand_file = Path(brand_path)
    brand = load_brand(brand_file)
    errors = validate_brand(brand)
    if errors:
        raise ValueError("invalid brand.json:\n  - " + "\n  - ".join(errors))

    pub = app / "public"
    pub.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    copied: list[str] = []

    # 1. CSS variables. Jailed: a pre-existing public/brand.css symlink
    #    pointing outside the app must be refused, not written through.
    css_path = _jailed(pub, "brand.css", "brand.css")
    css_path.write_text(render_css(brand))
    written.append(str((pub / "brand.css").relative_to(app)))

    # 2. Assets (paths are relative to the brand.json's own folder).
    #    Source is jailed to the brand folder (blocks ../ chains,
    #    absolute-path injection and symlinked assets reaching outside —
    #    an untrusted brand.json must not exfiltrate arbitrary files into
    #    the shipped app); destination is jailed to public/.
    out_brand = dict(brand)
    for key, fallback_ext in (("logo", "svg"), ("favicon", "png")):
        rel = brand.get(key)
        if not rel:
            continue
        src = _jailed(brand_file.parent, rel, f"{key} source")
        if not src.is_file():
            raise FileNotFoundError(f"{key} file not found: {src}")
        dest_name = Path(rel).name
        dest = _jailed(pub, dest_name, f"{key} destination")
        shutil.copy2(src, dest)
        copied.append(str((pub / dest_name).relative_to(app)))
        out_brand[key] = dest_name  # normalized: served from public/ root

    # 3. brand.json for runtime reads (appName, tagline, logo path, font)
    brand_json_path = _jailed(pub, "brand.json", "brand.json")
    brand_json_path.write_text(json.dumps(out_brand, indent=2) + "\n")
    written.append(str((pub / "brand.json").relative_to(app)))

    # 4. Patch Tauri config (window title, product name) — best effort.
    #    Jailed like every other write: a symlinked tauri.conf.json that
    #    resolves outside src-tauri/ is refused instead of patched.
    patched: list[str] = []
    tauri_conf = app / "src-tauri" / "tauri.conf.json"
    if tauri_conf.is_file():
        conf_target = _jailed(app / "src-tauri", "tauri.conf.json", "tauri.conf.json")
        conf = json.loads(conf_target.read_text())
        conf["productName"] = brand["appName"]
        windows = conf.get("app", {}).get("windows", [])
        if windows:
            windows[0]["title"] = brand["appName"]
        conf_target.write_text(json.dumps(conf, indent=2) + "\n")
        patched.append(str(tauri_conf.relative_to(app)))

    return {"written": written, "copied": copied, "patched": patched}
