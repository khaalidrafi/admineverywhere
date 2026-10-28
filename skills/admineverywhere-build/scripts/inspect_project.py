#!/usr/bin/env python3
"""inspect_project.py — map a repo's admin-relevant facts onto admineverywhere.

One scan, one JSON manifest on stdout. Pure stdlib. The agent (or a
human) feeds this to decisions: what to name the app, which logo to
ship, whether the backend is DRF-ready for the thin client.

Detected:
  django     manage.py locations, settings modules, INSTALLED_APPS entries
             (tolerant regex parse), urlconfs, DRF / spectacular / authtoken
             presence, token-auth route hints
  packaging  pyproject/setup.py/setup.cfg project names
  identity   README first heading + first paragraph (name/tagline candidates)
  assets     logo/favicon candidates under common static dirs
  domain     Django apps that declare models (the admin's nav sections)

Usage:
  python inspect_project.py --root /path/to/repo [--max-files 4000]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".tox", ".mypy_cache", "target", "src-tauri", "egg-info"}

DJANGO_KNOWN_APPS = {
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
}

LOGO_RE = re.compile(r"(logo|icon|favicon|mark|brand)", re.I)
LOGO_EXT = {".svg", ".png", ".jpg", ".jpeg", ".ico", ".icns"}


def iter_files(root: Path, max_files: int):
    count = 0
    for p in root.rglob("*"):
        if count >= max_files:
            return
        if p.is_dir():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        count += 1
        yield p


def parse_installed_apps(text: str) -> list[str]:
    """Tolerant extraction of INSTALLED_APPS entries from settings source."""
    m = re.search(r"INSTALLED_APPS\s*[:=]\s*(\[[^\]]*\]|\(.*?\))", text, re.S)
    if not m:
        return []
    blob = m.group(1)
    return re.findall(r"['\"]([\w.]+)['\"]", blob)


def read_head(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return ""


def pyproject_name(root: Path) -> str | None:
    p = root / "pyproject.toml"
    if not p.is_file():
        return None
    m = re.search(r"^\s*name\s*=\s*[\"']([^\"']+)[\"']", read_head(p), re.M)
    return m.group(1) if m else None


def readme_identity(root: Path) -> tuple[str | None, str | None]:
    for name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
        p = root / name
        if not p.is_file():
            continue
        lines = read_head(p, 8000).splitlines()
        stripped = [ln.strip() for ln in lines]
        # title = first non-empty line
        idx = next((i for i, ln in enumerate(stripped) if ln), None)
        if idx is None:
            continue
        title = stripped[idx].lstrip("#= ").strip()
        # blurb = first paragraph after the title (joined across wraps,
        # stops at a blank line or the next heading)
        para: list[str] = []
        for ln in stripped[idx + 1:]:
            if not ln:
                if para:
                    break
                continue
            if ln.startswith("#") or set(ln) <= {"=", "-"}:
                break
            para.append(ln)
        return (title or None), (" ".join(para) or None)
    return None, None


def logo_candidates(files: list[Path], root: Path) -> list[str]:
    found = [str(p.relative_to(root)) for p in files]
    # prefer svg (scales, tiny), then ico, then png/jpg; shallow paths first
    def score(rel: str) -> tuple:
        ext = Path(rel).suffix.lower()
        return (0 if ext == ".svg" else 1 if ext == ".ico" else 2,
                rel.count("/"), len(rel))
    return sorted(found, key=score)[:8]


def scan(root: Path, max_files: int) -> dict:
    manage_pys: list[str] = []
    settings_files: list[str] = []
    urlconf_files: list[str] = []
    model_apps: dict[str, int] = {}
    installed: set[str] = set()
    logo_files: list[Path] = []

    for p in iter_files(root, max_files):
        rel = str(p.relative_to(root))
        if p.name == "manage.py":
            manage_pys.append(rel)
        elif p.name in ("settings.py", "base.py", "prod.py"):
            installed.update(parse_installed_apps(read_head(p)))
            if p.name == "settings.py":
                settings_files.append(rel)
        elif p.name == "urls.py":
            urlconf_files.append(rel)
        elif p.name == "models.py" and p.parent != root:
            classes = len(re.findall(r"^class\s+\w+", read_head(p), re.M))
            if classes:
                model_apps[p.parent.name] = classes
        if p.suffix.lower() in LOGO_EXT and LOGO_RE.search(p.name):
            logo_files.append(p)

    def has(*mods: str) -> bool:
        return any(mod in app for app in installed for mod in mods)

    settings_modules = sorted(
        {str(Path(s).with_suffix("")).replace("/", ".") for s in settings_files})

    return {
        "root": str(root),
        "django": {
            "is_django": bool(manage_pys or settings_files),
            "manage_py": manage_pys[:4],
            "settings_modules": settings_modules[:6],
            "installed_apps_local": sorted(a for a in installed
                                           if a not in DJANGO_KNOWN_APPS
                                           and not a.startswith("django.")),
            "has_rest_framework": has("rest_framework"),
            "has_spectacular": has("drf_spectacular"),
            "has_authtoken": has("authtoken"),
            "urlconf_files": urlconf_files[:8],
        },
        "identity": {
            "package_name": pyproject_name(root),
            "readme_title": readme_identity(root)[0],
            "readme_blurb": readme_identity(root)[1],
            "name_candidates": [c for c in
                                (pyproject_name(root), readme_identity(root)[0]) if c],
        },
        "assets": {"logo_candidates": logo_candidates(logo_files, root)},
        "domain": {"model_apps": dict(sorted(model_apps.items(),
                                             key=lambda kv: -kv[1])[:12])},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".", help="repo root to scan (default: cwd)")
    ap.add_argument("--max-files", type=int, default=4000)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 2
    print(json.dumps(scan(root, args.max_files), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
