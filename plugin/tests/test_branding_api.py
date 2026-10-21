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

Also carries the production-CSP / --api-host tests at the bottom of the
file — the build-time half of the branding story, moved here from
test_branding.py on the csp-1 rebase.
"""
import base64
import json
import shutil
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from rest_framework.authtoken.models import Token

from admincraft import branding

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


def test_asset_404_for_unknown_file_in_a_subdir(brand_dir):
    """A path the route CAN address must still 404 when the bytes are absent."""
    with ctx(brand_dir):
        (brand_dir / "assets").mkdir(parents=True)
        r = Client().get("/branding/asset/assets/nope.svg")
    assert r.status_code == 404


# --- subdirectory assets: the shape every SHIPPED brand.json uses ----------
# app/brands/{default,freshorama,minimal-light}/brand.json all declare
# "logo": "assets/logo.svg" and "favicon": "assets/icon.png". build_admin
# flattens those into public/, so the runtime store is the only layer where a
# subdirectory asset can break — and it did: the asset route was
# <str:name>, which cannot carry a "/", so reverse() raised NoReverseMatch,
# _asset_url() swallowed it, and the client got a URL that 404s at the router.
# Broken logo, no error anywhere. These tests are the two-sided proof.

SHIPPED_BRAND = {**VALID_BRAND, "logo": "assets/logo.svg", "favicon": "assets/icon.png"}


def seed_shipped_assets(brand_dir: Path) -> Path:
    assets = brand_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "logo.svg").write_bytes(SVG_OK)
    (assets / "icon.png").write_bytes(PNG_1PX)
    return assets


def served_asset_names(client: Client) -> dict:
    """The asset NAMES the served URLs address, whichever mount prefix the
    host project chose (sliced from /branding/asset/ onwards)."""
    brand = client.get("/branding/").json()["brand"]
    marker = "/branding/asset/"
    return {key: value.split(marker, 1)[1] for key, value in brand.items()
            if isinstance(value, str) and marker in value}


def test_put_accepts_the_shipped_subdir_asset_shape(brand_dir, staff_token):
    seed_shipped_assets(brand_dir)
    with ctx(brand_dir):
        r = put(Client(), SHIPPED_BRAND, staff_token)
        assert r.status_code == 200, r.json()


def test_served_logo_url_names_the_stored_subdir_path(brand_dir, staff_token):
    """No flattening: the URL must address assets/logo.svg, not logo.svg."""
    seed_shipped_assets(brand_dir)
    with ctx(brand_dir):
        assert put(Client(), SHIPPED_BRAND, staff_token).status_code == 200
        names = served_asset_names(Client())
    assert names["logo"] == "assets/logo.svg"
    assert names["favicon"] == "assets/icon.png"


def test_subdir_asset_url_returns_the_stored_bytes(brand_dir, staff_token):
    seed_shipped_assets(brand_dir)
    with ctx(brand_dir):
        assert put(Client(), SHIPPED_BRAND, staff_token).status_code == 200
        names = served_asset_names(Client())
        logo = Client().get(f"/branding/asset/{names['logo']}")
        icon = Client().get(f"/branding/asset/{names['favicon']}")
    assert logo.status_code == 200, "the URL the client trusts must not 404"
    assert b"".join(logo.streaming_content) == SVG_OK
    assert logo.headers["Content-Type"].startswith("image/svg+xml")
    assert icon.status_code == 200
    assert b"".join(icon.streaming_content) == PNG_1PX


SHIPPED_BRAND_DIR = Path(__file__).resolve().parents[2] / "app" / "brands" / "default"


def test_the_actual_shipped_brand_file_round_trips_over_the_runtime_api(brand_dir, staff_token):
    """app/brands/default/brand.json is what a user is handed, and it stores
    "assets/logo.svg" — so the runtime store, seeded from that same folder,
    must serve the identical bytes build_admin would have copied."""
    brand = json.loads((SHIPPED_BRAND_DIR / "brand.json").read_text())
    shutil.copytree(SHIPPED_BRAND_DIR / "assets", brand_dir / "assets")
    with ctx(brand_dir):
        r = put(Client(), brand, staff_token)
        assert r.status_code == 200, r.json()
        names = served_asset_names(Client())
        for key in ("logo", "favicon"):
            r = Client().get(f"/branding/asset/{names[key]}")
            assert r.status_code == 200, f"{key}: {names[key]} is a URL to a file that exists"
            want = (SHIPPED_BRAND_DIR / names[key]).read_bytes()
            assert b"".join(r.streaming_content) == want, f"{key} bytes differ"


@pytest.mark.parametrize(
    "name",
    [
        "../escape.svg",
        "assets/../../escape.svg",
        "..",
        ".",
        "/etc/passwd",
        "assets//logo.svg",
        "assets\\logo.svg",
    ],
)
def test_asset_route_refuses_names_that_climb_out_of_the_brand_dir(brand_dir, tmp_path, name):
    """The shape guard: no "." / ".." / empty segment, no absolute path, no
    backslash. These never reached the view under <str:name>, so the guard was
    dead code and traversal over HTTP was untested end to end.

    Pinned to the guard's OWN message on purpose: the jail behind it answers
    400 for the same requests, so an assertion on the status alone cannot tell
    which layer refused — and if the guard ever rots, the symlink case below
    is the only thing left standing.
    """
    (tmp_path / "escape.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg">SECRET</svg>')
    (brand_dir / "assets").mkdir(parents=True)
    (brand_dir / "assets" / "logo.svg").write_bytes(SVG_OK)
    with ctx(brand_dir):
        r = Client().get(f"/branding/asset/{name}")
    assert r.status_code == 400, f"{name} must be refused, not served"
    assert r.json()["errors"] == ["bad asset name"]
    assert b"SECRET" not in r.content


def test_asset_route_refuses_a_symlinked_asset_the_guard_cannot_see(brand_dir, tmp_path):
    """The jail is the authority: this name is a perfectly-shaped filename, so
    only realpath + commonpath can stop it reading a file outside the brand
    dir. Separate from the shape refusals above — each layer must be killable."""
    secret = tmp_path / "secret.svg"
    secret.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg">SECRET</svg>')
    brand_dir.mkdir(parents=True, exist_ok=True)
    (brand_dir / "logo.svg").symlink_to(secret)
    with ctx(brand_dir):
        r = Client().get("/branding/asset/logo.svg")
    assert r.status_code == 400
    assert "escapes" in r.json()["errors"][0]
    assert b"SECRET" not in r.content


def test_asset_route_refuses_a_nul_byte_instead_of_500(brand_dir):
    """_jailed()'s realpath() raises ValueError on an embedded NUL; the view
    must turn that into a refusal, not a 500 with a traceback."""
    brand_dir.mkdir(parents=True)
    (brand_dir / "logo.png").write_bytes(PNG_1PX)
    with ctx(brand_dir):
        r = Client().get("/branding/asset/log%00o.png")
    assert r.status_code in (400, 404)


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


# ---------------------------------------------------------------------------
# Production CSP + --api-host substitution. Moved here from test_branding.py
# on the csp-1 rebase (EM order: branding tests live in this file now). The
# shipped tauri.conf.json carries connect-src 'self' https://API_HOST;
# build_admin --api-host substitutes the deployed origin at build time.
# Covers normalize_api_host (closed shape: https, dotted DNS, optional port —
# localhost/loopback/wildcards/paths/userinfo fail loudly),
# substitute_api_host (idempotent, drift fails) and inject_brand(api_host=...)
# end to end.
# ---------------------------------------------------------------------------

PROD_CSP = (
    "default-src 'self'; connect-src 'self' https://API_HOST; "
    "script-src 'self'; img-src 'self' data: https:; "
    "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
    "media-src 'self'; worker-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"
)

# The app dir that actually ships (parents[2] = repo root). CI's CSP-hygiene
# grep only rejects dev origins; the tests here pin the positive side.
SHIPPED_TAURI_CONF = (
    Path(__file__).resolve().parents[2] / "app" / "src-tauri" / "tauri.conf.json"
)

GOOGLE_FONTS_CSS = "https://fonts.googleapis.com"    # serves the @import
GOOGLE_FONTS_FILES = "https://fonts.gstatic.com"    # serves the .woff2 files


def directive(csp: str, name: str) -> str:
    """One directive's full text out of a CSP string (fails if absent)."""
    for part in csp.split(";"):
        stripped = part.strip()
        if stripped.startswith(name + " "):
            return stripped
    raise AssertionError(f"{name} missing from CSP: {csp}")

# inject_brand reads logo/favicon paths out of brand.json, so a shipped
# (build-time) brand needs real asset files — unlike VALID_BRAND above, which
# is an API payload.
SHIP_BRAND = {**VALID_BRAND, "appName": "Freshorama Admin",
              "logo": "assets/logo.svg", "favicon": "assets/icon.png"}


@pytest.fixture
def app_dir(tmp_path):
    """Minimal thin-client app skeleton (only what inject_brand touches)."""
    app = tmp_path / "app"
    (app / "public").mkdir(parents=True)
    tauri = app / "src-tauri"
    tauri.mkdir()
    (tauri / "tauri.conf.json").write_text(json.dumps({
        "productName": "Old Name",
        "app": {"windows": [{"title": "Old Name"}]},
    }))
    return app


@pytest.fixture
def ship_brand_dir(tmp_path):
    """A brand.json + its assets, as a client would ship them."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/logo.svg").write_bytes(SVG_OK)
    (tmp_path / "assets/icon.png").write_bytes(PNG_1PX)
    (tmp_path / "brand.json").write_text(json.dumps(SHIP_BRAND))
    return tmp_path


@pytest.fixture
def app_dir_csp(app_dir):
    """app_dir whose tauri.conf.json ships the production CSP placeholder."""
    conf_path = app_dir / "src-tauri" / "tauri.conf.json"
    conf = json.loads(conf_path.read_text())
    conf["app"]["security"] = {"csp": PROD_CSP}
    conf_path.write_text(json.dumps(conf))
    return app_dir


class TestNormalizeApiHost:
    @pytest.mark.parametrize("raw, want", [
        ("admin.example.com", "https://admin.example.com"),
        ("https://admin.example.com", "https://admin.example.com"),
        ("https://admin.example.com/", "https://admin.example.com"),
        ("HTTPS://Admin.Example.COM", "https://admin.example.com"),
        ("https://admin.example.com:8443", "https://admin.example.com:8443"),
        ("https://my-api.example.co.uk", "https://my-api.example.co.uk"),
    ])
    def test_accepts_and_normalizes(self, raw, want):
        assert branding.normalize_api_host(raw) == want

    @pytest.mark.parametrize("bad", [
        "", "   ", None,
        "http://admin.example.com",        # not https
        "ftp://admin.example.com",         # not https
        "https://localhost",               # loopback host
        "https://api.localhost",           # *.localhost
        "https://127.0.0.1",               # loopback ip
        "https://0.0.0.0",                 # loopback ip
        "https://*.example.com",           # wildcard
        "https://api",                     # single-label host
        "https://admin.example.com/api",   # path
        "https://u:p@admin.example.com",   # userinfo
        "https://admin .example.com",      # inner whitespace
    ])
    def test_rejects_what_must_never_ship(self, bad):
        with pytest.raises(ValueError):
            branding.normalize_api_host(bad)


class TestSubstituteApiHost:
    @staticmethod
    def _conf():
        return {"app": {"security": {"csp": PROD_CSP}}}

    def test_replaces_placeholder(self):
        conf = self._conf()
        origin = branding.substitute_api_host(conf, "admin.example.com")
        assert origin == "https://admin.example.com"
        csp = conf["app"]["security"]["csp"]
        assert "https://admin.example.com" in csp
        assert "API_HOST" not in csp

    def test_idempotent_same_origin(self):
        conf = self._conf()
        branding.substitute_api_host(conf, "https://admin.example.com")
        assert branding.substitute_api_host(conf, "https://admin.example.com") is None
        assert conf["app"]["security"]["csp"].count("https://admin.example.com") == 1

    def test_different_origin_after_substitution_raises(self):
        conf = self._conf()
        branding.substitute_api_host(conf, "https://admin.example.com")
        with pytest.raises(ValueError, match="drift"):
            branding.substitute_api_host(conf, "https://other.example.com")

    def test_missing_csp_raises(self):
        with pytest.raises(ValueError, match="csp missing"):
            branding.substitute_api_host({"app": {}}, "https://admin.example.com")

    def test_localhost_rejected_before_any_substitution(self):
        conf = self._conf()
        with pytest.raises(ValueError, match="localhost"):
            branding.substitute_api_host(conf, "https://localhost")
        assert "https://localhost" not in conf["app"]["security"]["csp"]


class TestInjectBrandCsp:
    def test_without_api_host_placeholder_stays(self, ship_brand_dir, app_dir_csp):
        branding.inject_brand(app_dir_csp, ship_brand_dir / "brand.json")
        conf = json.loads((app_dir_csp / "src-tauri" / "tauri.conf.json").read_text())
        assert "https://API_HOST" in conf["app"]["security"]["csp"]
        assert conf["productName"] == "Freshorama Admin"   # other patching intact

    def test_with_api_host_substitutes_in_written_conf(self, ship_brand_dir, app_dir_csp):
        summary = branding.inject_brand(app_dir_csp, ship_brand_dir / "brand.json",
                                        api_host="https://admin.freshorama.com")
        conf = json.loads((app_dir_csp / "src-tauri" / "tauri.conf.json").read_text())
        csp = conf["app"]["security"]["csp"]
        assert "https://admin.freshorama.com" in csp
        assert "API_HOST" not in csp
        assert "localhost" not in csp and "*" not in csp
        assert summary["csp_api_host"] == "https://admin.freshorama.com"

    def test_invalid_api_host_fails_before_any_write(self, ship_brand_dir, app_dir_csp):
        with pytest.raises(ValueError, match="localhost"):
            branding.inject_brand(app_dir_csp, ship_brand_dir / "brand.json",
                                  api_host="https://localhost")
        assert not (app_dir_csp / "public" / "brand.css").exists()  # nothing written

    def test_summary_reports_no_substitution_without_api_host(self, ship_brand_dir, app_dir_csp):
        summary = branding.inject_brand(app_dir_csp, ship_brand_dir / "brand.json")
        assert summary["csp_api_host"] is None


class TestProdCspBrandOrigins:
    """BRE Finding 2: self-only img-src/font-src silently breaks two product
    promises — a brand.json webfont (render_css / brandToCss emit a Google
    Fonts @import) and a hosted logo URL. Pinned here because CI's hygiene
    grep only rejects dev origins, never asserts these.
    """

    def test_img_src_allows_hosted_logos(self):
        # data: stays for the runtime branding API's data-URL uploads
        assert directive(PROD_CSP, "img-src") == "img-src 'self' data: https:"

    def test_font_src_allows_google_fonts(self):
        font_src = directive(PROD_CSP, "font-src")
        assert GOOGLE_FONTS_CSS in font_src
        assert GOOGLE_FONTS_FILES in font_src

    def test_style_src_allows_the_fonts_import(self):
        # An @import inside a <style> block is gated by style-src, not
        # font-src: font-src alone covers only the font FILES, so without
        # this the app still falls back to the system font.
        assert GOOGLE_FONTS_CSS in directive(PROD_CSP, "style-src")

    def test_shipped_conf_carries_exactly_the_prod_csp(self):
        csp = json.loads(SHIPPED_TAURI_CONF.read_text())["app"]["security"]["csp"]
        assert csp == PROD_CSP

    def test_no_dev_origins_anywhere_in_the_prod_csp(self):
        # mirrors the CI hygiene gate, so a local run catches a leak first
        for token in ("localhost", "http://", "ws://", "wss://", "*"):
            assert token not in PROD_CSP, token

    def test_substitution_keeps_the_brand_origins(self):
        """The generated (deployed) CSP is the one that ships — substituting
        the API_HOST placeholder must not drop the brand directives."""
        conf = {"app": {"security": {"csp": PROD_CSP}}}
        branding.substitute_api_host(conf, "https://admin.example.com")
        csp = conf["app"]["security"]["csp"]
        assert directive(csp, "img-src") == "img-src 'self' data: https:"
        assert directive(csp, "font-src") == (
            f"font-src 'self' {GOOGLE_FONTS_CSS} {GOOGLE_FONTS_FILES}")
        assert directive(csp, "connect-src") == (
            "connect-src 'self' https://admin.example.com")
