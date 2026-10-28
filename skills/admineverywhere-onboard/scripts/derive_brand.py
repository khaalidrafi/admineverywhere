#!/usr/bin/env python3
"""derive_brand.py — turn a project's own source data into a brand kit.

AUTO mode engine for the admineverywhere skills: reads the repo (directly or
via an inspect_project.py manifest) and writes a complete brand folder:

    <out>/
      brand.json          — passes admineverywhere's closed schema exactly
      assets/logo.svg|png — copied from the project (or generated)
      assets/icon.png     — 512px favicon / fallback
      assets/icon-1024.png— source for `npx tauri icon` (launcher icons)

Decision order (first match wins):
  name     --name  >  pyproject/setup name  >  README first heading  >  Admineverywhere
  tagline  --tagline >  README first sentence (<= 140 chars)         >  omitted
  logo     --logo (path, repo-relative) >  first detected candidate  >  generated
  colors   --primary/--accent >  hex colors found in an SVG logo     >  palette
  palette  --palette dark|light (default dark)

Generic names (backend, api, core, config…) are skipped when better
candidates exist. Pure stdlib. Every output is validated locally with
the same rules the server enforces — fail fast, fail loud.

Usage:
  python derive_brand.py --root /repo --out /repo/brand [--name X]
  python derive_brand.py --manifest manifest.json --out /repo/brand
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path

# ---------------------------------------------------------------- palettes --

PALETTES = {
    "dark": {"primary": "#4f46e5", "accent": "#06b6d4", "bg": "#0f172a",
             "surface": "#1e293b", "text": "#f1f5f9"},
    "light": {"primary": "#2563eb", "accent": "#059669", "bg": "#faf9f7",
               "surface": "#ffffff", "text": "#1c1917"},
}

GENERIC_NAMES = {
    "app", "api", "backend", "core", "config", "server", "main", "project",
    "src", "django", "admin", "web", "service", "mysite", "settings",
    "django-api", "django-project", "backend-api",
}

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
RADIUS_RE = re.compile(r"^\d+(\.\d+)?(px|rem|em)$")
FONT_RE = re.compile(r"^[A-Za-z0-9 ]{1,60}$")
NAME_RE = re.compile(r"^[^/\\<>:\"|?*\x00-\x1f]{1,120}$")

# ------------------------------------------------------- stdlib PNG engine --

def png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: Path, size: int, rgb_fn):
    rows = []
    for y in range(size):
        row = bytearray(b"\x00")
        for x in range(size):
            row += bytes(rgb_fn(x, y))
        rows.append(row)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr)
                     + png_chunk(b"IDAT", zlib.compress(
                         b"".join(bytes(r) for r in rows), 9))
                     + png_chunk(b"IEND", b""))


def rounded_inside(x, y, cx, cy, half, radius):
    if abs(x - cx) > half or abs(y - cy) > half:
        return False
    dx, dy = abs(x - cx) - (half - radius), abs(y - cy) - (half - radius)
    if dx > 0 and dy > 0:
        return math.sqrt(dx * dx + dy * dy) <= radius
    return True


def generate_icons(out_dir: Path, primary: str, accent: str) -> list[str]:
    """Neutral 2x2 grid mark (no letters) — a valid identity for any product."""
    pr = tuple(int(primary.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    ac = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    centers, cell_half, cell_r = (0.355, 0.645), 0.117, 0.05

    def px_factory(size):
        radius, cx = size * 0.18, size / 2

        def px(x, y):
            t = (x + y) / (2 * size)
            color = tuple(int(pr[i] + (ac[i] - pr[i]) * t) for i in range(3))
            alpha = 255
            dx, dy = abs(x - cx) - (cx - radius), abs(y - cx) - (cx - radius)
            if dx > 0 and dy > 0 and math.sqrt(dx * dx + dy * dy) > radius:
                alpha = 0
            for iy, cyf in enumerate(centers):
                for ix, cxf in enumerate(centers):
                    if rounded_inside(x, y, cxf * size, cyf * size,
                                      cell_half * size, cell_r * size):
                        op = 0.95 if (ix + iy) % 2 == 0 else 0.55
                        color = tuple(int(255 * op + color[i] * (1 - op))
                                      for i in range(3))
            return (*color, alpha)
        return px

    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    write_png(assets / "icon.png", 512, px_factory(512))
    write_png(assets / "icon-1024.png", 1024, px_factory(1024))
    return ["assets/icon.png", "assets/icon-1024.png"]


# ----------------------------------------------------------------- naming --

def humanize(name: str) -> str:
    name = name.strip().lstrip("#").strip()
    name = re.sub(r"[-_]+", " ", name)
    words = [w for w in name.split() if w]
    return " ".join(w[0].upper() + w[1:] for w in words if w).strip()


def pick_name(manifest: dict, explicit: str | None) -> str:
    if explicit:
        return explicit
    candidates: list[str] = list(manifest.get("identity", {}).get("name_candidates", []))
    readme = manifest.get("identity", {}).get("readme_title")
    if readme and readme not in candidates:
        candidates.append(readme)
    cleaned = [humanize(c) for c in candidates if c]
    for c in cleaned:
        if c.lower() not in GENERIC_NAMES:
            return c
    return cleaned[0] if cleaned else "Admineverywhere"


def pick_tagline(manifest: dict, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    blurb = manifest.get("identity", {}).get("readme_blurb") or ""
    # first sentence, trimmed, tags/links stripped
    sentence = re.split(r"(?<=[.!?])\s", blurb.strip(), maxsplit=1)[0]
    sentence = re.sub(r"[*_`[\]()>#]", "", sentence).strip()
    if len(sentence) > 140:  # cut on a word boundary, never mid-word
        cut = sentence[:140].rsplit(" ", 1)[0]
        sentence = cut.rstrip(",;:-( ") or sentence[:140]
    return sentence


def svg_colors(path: Path) -> list[str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    return [c.lower() for c in HEX_RE.findall(text)][:6]


# -------------------------------------------------------------- validation --

def validate_brand(brand: dict) -> list[str]:
    errors: list[str] = []
    name = brand.get("appName")
    if not isinstance(name, str) or not name.strip():
        errors.append("appName: must be a non-empty string")
    elif not NAME_RE.match(name.strip()):
        errors.append(f"appName: characters not safe for window titles ({name!r})")
    for key in ("tagline",):
        v = brand.get(key)
        if v is not None and (not isinstance(v, str) or len(v) > 140):
            errors.append(f"{key}: must be a string of <= 140 chars")
    colors = brand.get("colors", {})
    for key in ("primary", "accent", "bg", "surface", "text"):
        if not isinstance(colors.get(key), str) or not HEX_RE.fullmatch(colors.get(key, "")):
            errors.append(f"colors.{key}: must be a 6-digit hex like #7c3aed")
    if not RADIUS_RE.match(brand.get("radius", "")):
        errors.append("radius: must be a CSS length like '0.75rem'")
    if not FONT_RE.match(brand.get("font", "").strip()):
        errors.append("font: plain Google Font name like 'Inter'")
    for key in ("logo", "favicon"):
        rel = brand.get(key)
        if rel is not None and (rel.startswith(("/", "\\")) or ".." in rel):
            errors.append(f"{key}: must stay inside the brand folder")
    return errors


# -------------------------------------------------------------------- main --

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", help="repo to derive from (default: cwd)")
    ap.add_argument("--manifest", help="inspect_project.py JSON instead of --root")
    ap.add_argument("--out", required=True, help="brand dir to write (created)")
    ap.add_argument("--name", help="explicit app name (overrides derivation)")
    ap.add_argument("--tagline", help="explicit tagline ('' to omit)")
    ap.add_argument("--logo", help="repo-relative logo file to use")
    ap.add_argument("--font", default="Inter")
    ap.add_argument("--radius", default="0.75rem")
    ap.add_argument("--palette", choices=["dark", "light"], default="dark")
    ap.add_argument("--primary", help="override primary hex (with --accent)")
    ap.add_argument("--accent", help="override accent hex (with --primary)")
    args = ap.parse_args(argv)

    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    from inspect_project import scan  # sibling script

    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text())
        root = Path(manifest.get("root") or args.root or ".").resolve()
    else:
        root = Path(args.root or ".").resolve()
        manifest = scan(root, 4000)

    out_dir = Path(args.out).resolve()
    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    # -- name / tagline ----------------------------------------------------
    name = pick_name(manifest, args.name)
    tagline = pick_tagline(manifest, args.tagline)

    # -- logo ---------------------------------------------------------------
    logo_rel: str | None = None
    logo_src: Path | None = None
    if args.logo:
        logo_src = (root / args.logo)
        if not logo_src.is_file():
            print(f"error: --logo not found: {logo_src}", file=sys.stderr)
            return 2
    else:
        candidates = manifest.get("assets", {}).get("logo_candidates", [])
        if candidates:
            logo_src = root / candidates[0]
    written: list[str] = []
    if logo_src and logo_src.is_file():
        dest_name = "logo" + logo_src.suffix.lower()
        dest = assets / dest_name
        dest.write_bytes(logo_src.read_bytes())
        logo_rel = f"assets/{dest_name}"
        written.append(logo_rel)

    # -- colors ---------------------------------------------------------------
    colors = dict(PALETTES[args.palette])
    found = svg_colors(logo_src) if logo_src and logo_src.suffix.lower() == ".svg" else []
    if found:
        colors["primary"] = found[0]
        if len(found) > 1 and found[1] != found[0]:
            colors["accent"] = found[1]
    if args.primary:
        colors["primary"] = args.primary if args.primary.startswith("#") else "#" + args.primary
    if args.accent:
        colors["accent"] = args.accent if args.accent.startswith("#") else "#" + args.accent

    # -- icons (always ship a valid favicon) ----------------------------------
    favicon_rel = logo_rel if (logo_rel and logo_rel.endswith(".png")) else None
    if not favicon_rel:
        gen = generate_icons(out_dir, colors["primary"], colors["accent"])
        written.extend(gen)
        favicon_rel = "assets/icon.png"
        if not logo_rel:
            logo_rel = "assets/icon.png"  # generated mark doubles as logo

    brand = {
        "appName": name,
        "tagline": tagline,
        "logo": logo_rel,
        "favicon": favicon_rel,
        "colors": colors,
        "radius": args.radius,
        "font": args.font,
    }
    if not brand["tagline"]:
        del brand["tagline"]

    errors = validate_brand(brand)
    if errors:
        print("derived brand is INVALID (the server would reject it too):",
              file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    (out_dir / "brand.json").write_text(json.dumps(brand, indent=2) + "\n")
    written.append("brand.json")

    print(f"brand dir ready: {out_dir}")
    print(f"  name:    {name}")
    print(f"  tagline: {tagline or '(none)'}")
    print(f"  logo:    {logo_rel}")
    print(f"  favicon: {favicon_rel}")
    print(f"  colors:  {colors['primary']} / {colors['accent']} ({args.palette})")
    print("next: python manage.py build_admin --brand "
          f"{out_dir / 'brand.json'} --app <client dir>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
