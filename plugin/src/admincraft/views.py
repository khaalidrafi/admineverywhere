"""HTTP layer for the runtime brand store.

Routes (mounted by the host project, e.g. path("admincraft/", include("admincraft.urls"))):

  GET  branding/            public → {"brand": ..., "rev": ...} or 404
  PUT  branding/            staff  → replace the brand (body uses the
                                     brand.json closed schema; logo/favicon
                                     may be data URLs)
  GET  branding/asset/<f>   public → serve logo/favicon from the brand dir

Auth mirrors the host API: `Authorization: Token <key>` resolved through
DRF's authtoken when the host has DRF installed (the normal case — the
thin client authenticates the same way). Without DRF, PUT answers 501
with the offline alternative (edit files, run build_admin).

CSRF is exempted: this is a token-authenticated JSON API — same posture
as DRF itself. The input-trust story lives in brandstore/branding:
closed schema, magic-byte checks, size caps, jailed file access.
"""
from __future__ import annotations

import json

from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import brandstore

ASSET_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


def _resolve_user(request):
    """Return (user, None) on success or (None, (status, errors)) on failure."""
    header = request.headers.get("Authorization", "")
    if not header.strip():
        return None, (401, ["authentication required: send 'Authorization: Token <key>'"])
    scheme, _, key = header.partition(" ")
    key = key.strip()
    if scheme.lower() not in ("token", "bearer") or not key:
        return None, (400, ["malformed Authorization header (expected 'Token <key>')"])
    try:
        from rest_framework.authtoken.models import Token
    except ImportError:
        return None, (501, [
            "rest_framework is not installed on this host — change branding "
            "by editing the brand files and running manage.py build_admin"
        ])
    token = Token.objects.select_related("user").filter(key=key).first()
    if token is None:
        return None, (401, ["invalid token"])
    return token.user, None


@csrf_exempt
def branding(request):
    if request.method == "GET":
        data = brandstore.read_brand()
        if data is None:
            return JsonResponse(
                {"detail": "no brand configured — the client falls back to its bundled brand"},
                status=404,
            )
        return JsonResponse(data)

    if request.method == "PUT":
        user, failure = _resolve_user(request)
        if failure:
            return JsonResponse({"errors": failure[1]}, status=failure[0])
        if not user.is_staff:
            return JsonResponse(
                {"errors": ["only staff users may change branding"]}, status=403)
        try:
            payload = json.loads(request.body or b"")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return JsonResponse({"errors": [f"invalid JSON body: {exc}"]}, status=400)
        try:
            data = brandstore.save_brand(payload)
        except brandstore.BrandValidationError as exc:
            return JsonResponse({"errors": exc.errors}, status=400)
        return JsonResponse(data)

    return JsonResponse({"errors": [f"method {request.method} not allowed"]}, status=405)


def brand_asset(request, name: str):
    # <str:name> cannot contain "/", and we re-jail anyway — belt+suspenders.
    if "/" in name or "\\" in name or name in (".", ".."):
        return JsonResponse({"errors": ["bad asset name"]}, status=400)
    try:
        path = brandstore.asset_path(name)
    except ValueError as exc:
        return JsonResponse({"errors": [str(exc)]}, status=400)
    if not path.is_file():
        return JsonResponse({"errors": [f"asset not found: {name}"]}, status=404)
    content_type = ASSET_CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path.open("rb"), content_type=content_type)
