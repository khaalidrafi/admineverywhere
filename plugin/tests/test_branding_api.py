"""Runtime branding API — the in-app rebrand surface.

Contract under test (mirrors views.py / brandstore.py):
  GET  /branding/            public → {"brand": ..., "rev": ...} or 404
  PUT  /branding/            staff  → replace brand (closed schema,
                                      logo/favicon may be data URLs)
  GET  /branding/asset/<f>   public → serve brand dir assets

Written FIRST (red), then implemented in admincraft/brandstore.py +
admincraft/views.py + admincraft/urls.py. Security posture inherits the
branding.py P0 rules: closed schema, magic-byte asset checks, path jail
on every read/write, token auth for PUT, staff-only.
"""
import base64
import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from rest_framework.authtoken.models import Token

# 1x1 transparent PNG (valid header, valid file)
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
# minimal JPEG-ish blob: SOI + APP0 marker (magic-byte check only)
JPEG_FAKE = b"\xff\xd8\xff\xe0" + b"\x00" * 16
SVG_OK = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"></svg>'


def data_url(mime: str, blob: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(blob).decode()}"


VALID_BRAND = {
    "appName": "Ledgerly",
    "tagline": "Quiet tools",
    "colors": {
        "primary": "#2563eb",
        "accent": "#059669",
        "bg": "#faf9f7",
        "surface": "#ffffff",
        "text": "#1c1917",
    },
    "radius": "0.5rem",
    "font": "Inter",
}


def put(client: Client, payload, token: str | None = None):
    headers = {}
    if token:
        headers["HTTP_AUTHORIZATION"] = f"Token {token}"
    return client.put(
        "/branding/", data=json.dumps(payload), content_type="application/json", **headers
    )


@pytest.fixture
def brand_dir(tmp_path) -> Path:
    return tmp_path / "brand"


@pytest.fixture
def staff_user():
    U = get_user_model()
    user = U.objects.create_user("staffer", password="x", is_staff=True)
    yield user
    user.delete()  # no pytest-django transactions: clean up explicitly


@pytest.fixture
def staff_token(staff_user):
    return Token.objects.create(user=staff_user).key


@pytest.fixture
def plain_user():
    U = get_user_model()
    user = U.objects.create_user("plain", password="x", is_staff=False)
    yield user
    user.delete()


@pytest.fixture
def plain_token(plain_user):
    return Token.objects.create(user=plain_user).key


def ctx(brand_dir: Path):
    return override_settings(ADMINCRAFT_BRAND_DIR=brand_dir)


# ----------------------------------------------------------------- GET ----

def test_get_404_when_no_brand_configured(brand_dir):
    with ctx(brand_dir):
        r = Client().get("/branding/")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_get_returns_public_brand_after_put(brand_dir, staff_token):
    with ctx(brand_dir):
        assert put(Client(), VALID_BRAND, staff_token).status_code == 200
        r = Client().get("/branding/")
    assert r.status_code == 200
    body = r.json()
    assert body["brand"]["appName"] == "Ledgerly"
    assert body["rev"] > 0


def test_get_broken_brand_json_falls_back_to_404(brand_dir, staff_token):
    with ctx(brand_dir):
        put(Client(), VALID_BRAND, staff_token)
        (brand_dir / "brand.json").write_text("{not json")
        r = Client().get("/branding/")
    assert r.status_code == 404


# ----------------------------------------------------------------- PUT ----

def test_put_requires_authentication(brand_dir):
    with ctx(brand_dir):
        r = put(Client(), VALID_BRAND)
    assert r.status_code == 401
    assert r.json()["errors"]


def test_put_rejects_invalid_token(brand_dir):
    with ctx(brand_dir):
        r = put(Client(), VALID_BRAND, token="not-a-real-token")
    assert r.status_code == 401


def test_put_rejects_non_staff(brand_dir, plain_token):
    with ctx(brand_dir):
        r = put(Client(), VALID_BRAND, plain_token)
    assert r.status_code == 403


def test_put_roundtrip_writes_brand_json(brand_dir, staff_token):
    with ctx(brand_dir):
        r = put(Client(), VALID_BRAND, staff_token)
    assert r.status_code == 200
    saved = json.loads((brand_dir / "brand.json").read_text())
    assert saved["appName"] == "Ledgerly"
    assert r.json()["brand"]["appName"] == "Ledgerly"


def test_put_collects_all_validation_errors(brand_dir, staff_token):
    bad = {
        "appName": "",
        "unknownKey": 1,
        "colors": {"primary": "nope", "accent": "#06b6d4", "bg": "#0f172a",
                   "surface": "#1e293b", "text": "#f1f5f9"},
        "radius": "huge",
        "font": "Inter<script>",
    }
    with ctx(brand_dir):
        r = put(Client(), bad, staff_token)
    assert r.status_code == 400
    errors = r.json()["errors"]
    assert len(errors) >= 4  # appName, unknown key, color, radius, font
    assert not (brand_dir / "brand.json").exists()  # nothing written on failure


def test_rev_advances_on_second_save(brand_dir, staff_token):
    with ctx(brand_dir):
        r1 = put(Client(), VALID_BRAND, staff_token).json()
        r2 = put(Client(), {**VALID_BRAND, "appName": "Ledgerly 2"}, staff_token).json()
    assert r2["rev"] >= r1["rev"]
    assert r2["brand"]["appName"] == "Ledgerly 2"


# --------------------------------------------------------------- assets ----

@pytest.mark.parametrize(
    "mime,blob,name",
    [
        ("image/png", PNG_1PX, "logo.png"),
        ("image/jpeg", JPEG_FAKE, "logo.jpg"),
        ("image/svg+xml", SVG_OK, "logo.svg"),
    ],
)
def test_put_accepts_data_url_assets(brand_dir, staff_token, mime, blob, name):
    payload = {**VALID_BRAND, "logo": data_url(mime, blob)}
    with ctx(brand_dir):
        r = put(Client(), payload, staff_token)
        assert r.status_code == 200
        assert (brand_dir / name).read_bytes() == blob
        assert r.json()["brand"]["logo"].endswith(f"/{name}")
        # asset route serves it back
        r = Client().get(f"/branding/asset/{name}")
        assert r.status_code == 200
        assert b"".join(r.streaming_content) == blob


def test_put_favicon_data_url(brand_dir, staff_token):
    payload = {**VALID_BRAND, "favicon": data_url("image/png", PNG_1PX)}
    with ctx(brand_dir):
        r = put(Client(), payload, staff_token)
    assert r.status_code == 200
    assert (brand_dir / "favicon.png").exists()
    assert r.json()["brand"]["favicon"].endswith("/favicon.png")


def test_asset_content_types(brand_dir, staff_token):
    with ctx(brand_dir):
        put(Client(), {**VALID_BRAND, "logo": data_url("image/svg+xml", SVG_OK)}, staff_token)
        a = Client().get("/branding/asset/logo.svg")
    assert a.status_code == 200
    assert a.headers["Content-Type"].startswith("image/svg+xml")


def test_put_rejects_wrong_magic_bytes(brand_dir, staff_token):
    payload = {**VALID_BRAND, "logo": data_url("image/png", JPEG_FAKE)}
    with ctx(brand_dir):
        r = put(Client(), payload, staff_token)
    assert r.status_code == 400
    assert not (brand_dir / "logo.png").exists()


def test_put_rejects_unsupported_mime(brand_dir, staff_token):
    payload = {**VALID_BRAND, "logo": data_url("image/webp", PNG_1PX)}
    with ctx(brand_dir):
        r = put(Client(), payload, staff_token)
    assert r.status_code == 400


def test_put_rejects_oversized_asset(brand_dir, staff_token):
    blob = PNG_1PX + b"\x00" * 1_100_000  # magic ok, over the 1 MB cap
    payload = {**VALID_BRAND, "logo": data_url("image/png", blob)}
    with ctx(brand_dir):
        r = put(Client(), payload, staff_token)
    assert r.status_code == 400


def test_put_rejects_traversal_asset_path(brand_dir, staff_token):
    payload = {**VALID_BRAND, "logo": "../../etc/passwd"}
    with ctx(brand_dir):
        r = put(Client(), payload, staff_token)
    assert r.status_code == 400


def test_put_rejects_missing_relative_asset(brand_dir, staff_token):
    payload = {**VALID_BRAND, "logo": "ghost.svg"}
    with ctx(brand_dir):
        r = put(Client(), payload, staff_token)
    assert r.status_code == 400


def test_asset_404_for_unknown_file(brand_dir):
    with ctx(brand_dir):
        r = Client().get("/branding/asset/nope.png")
    assert r.status_code == 404


def test_put_rejects_non_json_body(brand_dir, staff_token):
    with ctx(brand_dir):
        r = Client().put("/branding/", data=b"{broken",
                         content_type="application/json",
                         HTTP_AUTHORIZATION=f"Token {staff_token}")
    assert r.status_code == 400


def test_method_not_allowed(brand_dir):
    with ctx(brand_dir):
        r = Client().post("/branding/", data="{}",
                          content_type="application/json")
    assert r.status_code == 405
