"""Runtime brand store — the server-side source of truth for in-app branding.

Storage: ONE directory (settings.ADMINCRAFT_BRAND_DIR, default
``<BASE_DIR>/admincraft_brand``) holding ``brand.json`` plus the
logo/favicon files it references. Host projects wire it via urls.py::

    path("admincraft/", include("admincraft.urls"))

and the thin client can then read/patch branding over HTTP (views.py)
instead of shipping a rebuilt bundle per brand.

Trust posture (inherited from branding.py, P0):
- payload goes through the SAME closed schema (validate_brand);
- data-URL assets survive only as png/jpeg/svg, verified by magic
  bytes, capped at MAX_ASSET_BYTES;
- every file read/write is jailed (realpath + commonpath) inside the
  brand dir — no "../" chains, absolute paths or symlink escapes.

Public API (used by views.py):
    read_brand() -> {"brand": ..., "rev": ...} | None
    save_brand(payload) -> {"brand": ..., "rev": ...}
    asset_path(name) -> Path            # jailed, for the asset view
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import time
from pathlib import Path

from django.conf import settings

from .branding import _jailed as jailed, validate_brand

MAX_ASSET_BYTES = 1_000_000

DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$", re.DOTALL)

FALLBACK_ASSET_URL = "/admincraft/branding/asset/{name}"


class BrandValidationError(Exception):
    """All problems at once (same contract as validate_brand)."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# ------------------------------------------------------------- paths ----

def brand_dir() -> Path:
    configured = getattr(settings, "ADMINCRAFT_BRAND_DIR", None)
    if configured:
        return Path(configured)
    base = getattr(settings, "BASE_DIR", None)
    return Path(base or ".") / "admincraft_brand"


def _asset_url(name: str) -> str:
    try:
        from django.urls import NoReverseMatch, reverse
        return reverse("admincraft:brand-asset", args=[name])
    except Exception:  # NoReverseMatch, urlconf not loaded, no namespace...
        return FALLBACK_ASSET_URL.format(name=name)


def asset_path(name: str) -> Path:
    """Jailed path for a brand-dir asset (raises ValueError on escape)."""
    return jailed(brand_dir(), name, "asset")


# ------------------------------------------------------------ decoding ----

def _is_png(b: bytes) -> bool:
    return b.startswith(b"\x89PNG\r\n\x1a\n")


def _is_jpeg(b: bytes) -> bool:
    return len(b) > 3 and b[:3] == b"\xff\xd8\xff"


def _is_svg(b: bytes) -> bool:
    try:
        text = b.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    head = text.lstrip()[:1000].lower()
    return head.startswith("<") and "<svg" in head


ASSET_TYPES = {
    "image/png": (_is_png, ".png"),
    "image/jpeg": (_is_jpeg, ".jpg"),
    "image/svg+xml": (_is_svg, ".svg"),
}


def _decode_data_url(key: str, value: str) -> tuple[str, bytes]:
    match = DATA_URL_RE.match(value.strip())
    if not match:
        raise BrandValidationError(
            [f"{key}: malformed data URL (expected data:<mime>;base64,<payload>)"])
    mime = match.group("mime").lower()
    spec = ASSET_TYPES.get(mime)
    if spec is None:
        raise BrandValidationError(
            [f"{key}: unsupported image type {mime!r} "
             f"(allowed: {', '.join(sorted(ASSET_TYPES))})"])
    check, ext = spec
    try:
        blob = base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError):
        raise BrandValidationError([f"{key}: invalid base64 payload"]) from None
    if len(blob) > MAX_ASSET_BYTES:
        raise BrandValidationError(
            [f"{key}: larger than {MAX_ASSET_BYTES} bytes (got {len(blob)})"])
    if not check(blob):
        raise BrandValidationError(
            [f"{key}: payload does not look like {mime} (magic-byte check failed)"])
    return ext, blob


# ------------------------------------------------------------- public ----

def _public(brand: dict) -> dict:
    """Client-facing form: asset keys become API-relative asset URLs."""
    out = dict(brand)
    for key in ("logo", "favicon"):
        rel = out.get(key)
        if rel:
            out[key] = _asset_url(Path(rel).name)
    return out


def read_brand() -> dict | None:
    """Current brand + revision counter, or None when not configured.

    A broken/unparseable brand.json also returns None: the client then
    falls back to its bundled static brand instead of rendering garbage.
    """
    brand_json = brand_dir() / "brand.json"
    if not brand_json.is_file():
        return None
    try:
        raw = json.loads(brand_json.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict) or not raw.get("appName"):
        return None
    return {"brand": _public(raw), "rev": int(brand_json.stat().st_mtime)}


def save_brand(payload: dict) -> dict:
    """Validate + persist a full brand replacement; returns read_brand() shape.

    ``logo``/``favicon`` accept either a relative path (file must already
    exist in the brand dir) or a data URL (decoded, magic-checked, written
    as ``logo.<ext>`` / ``favicon.<ext>``).
    """
    if not isinstance(payload, dict):
        raise BrandValidationError(["body: must be a JSON object"])

    payload = dict(payload)
    pending: dict[str, tuple[str, bytes]] = {}
    for key in ("logo", "favicon"):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.startswith("data:"):
            ext, blob = _decode_data_url(key, value)
            pending[key] = (ext, blob)
            payload[key] = f"{key}{ext}"  # placeholder passes validate_brand

    errors = validate_brand(payload)

    # Pre-declared relative assets must exist server-side.
    directory = brand_dir()
    for key in ("logo", "favicon"):
        rel = payload.get(key)
        if rel and key not in pending and not (directory / rel).is_file():
            errors.append(f"{key}: file not found in brand dir ({rel})")

    if errors:
        raise BrandValidationError(errors)

    directory.mkdir(parents=True, exist_ok=True)
    for key, (ext, blob) in pending.items():
        target = jailed(directory, f"{key}{ext}", f"{key} write")
        target.write_bytes(blob)

    brand_json = jailed(directory, "brand.json", "brand.json write")
    brand_json.write_text(json.dumps(payload, indent=2) + "\n")

    # Touch mtime so rev strictly advances even within one clock second.
    stamp = int(time.time()) + 1
    import os

    os.utime(brand_json, (stamp, stamp))
    return {"brand": _public(payload), "rev": stamp}
