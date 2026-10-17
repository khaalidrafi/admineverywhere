"""Tests for admincraft.branding — the pure branding engine.

Rule: written BEFORE implementation (red -> green).
Contract under test (the "30-second rebrand" promise):
- load_brand: JSON in, dict out; FileNotFoundError on missing path
- validate_brand: collect ALL problems (not first-only) for: missing keys,
  bad hex colors, bad radius, bad appName
- render_css: every brand var present + Google Font import + sanitized font
- inject_brand: writes public/brand.css + public/brand.json, copies logo &
  favicon into public/, patches src-tauri/tauri.conf.json title/productName
"""
import json
from pathlib import Path

import pytest

from admincraft import branding

VALID_BRAND = {
    "appName": "Freshorama Admin",
    "tagline": "Manage everything, beautifully",
    "logo": "assets/logo.svg",
    "favicon": "assets/icon.png",
    "colors": {
        "primary": "#7c3aed",
        "accent": "#06b6d4",
        "bg": "#0f172a",
        "surface": "#1e293b",
        "text": "#f1f5f9",
    },
    "radius": "0.75rem",
    "font": "Inter",
}

# 1x1 transparent PNG (valid file so copy() has real content to work with)
import base64
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
TINY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"/>'


@pytest.fixture
def brand_dir(tmp_path):
    """A brand.json + its assets, as a client would ship them."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/logo.svg").write_bytes(TINY_SVG)
    (tmp_path / "assets/icon.png").write_bytes(TINY_PNG)
    (tmp_path / "brand.json").write_text(json.dumps(VALID_BRAND))
    return tmp_path


@pytest.fixture
def app_dir(tmp_path):
    """Minimal thin-client app skeleton (only what inject touches)."""
    app = tmp_path / "app"
    (app / "public").mkdir(parents=True)
    tauri = app / "src-tauri"
    tauri.mkdir()
    (tauri / "tauri.conf.json").write_text(json.dumps({
        "productName": "Old Name",
        "app": {"windows": [{"title": "Old Name"}]},
    }))
    return app


class TestLoadBrand:
    def test_loads_json(self, brand_dir):
        brand = branding.load_brand(brand_dir / "brand.json")
        assert brand["appName"] == "Freshorama Admin"
        assert brand["colors"]["primary"] == "#7c3aed"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            branding.load_brand(tmp_path / "nope.json")

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json")
        with pytest.raises(ValueError):
            branding.load_brand(p)


class TestValidateBrand:
    def test_valid_brand_has_no_errors(self, brand_dir):
        brand = branding.load_brand(brand_dir / "brand.json")
        assert branding.validate_brand(brand) == []

    def test_missing_keys_all_reported(self):
        # appName, colors.primary, radius all missing -> 3+ errors, not 1
        errors = branding.validate_brand({})
        keys = {e for e in errors}
        assert any("appName" in e for e in errors)
        assert any("colors.primary" in e for e in errors)
        assert any("radius" in e for e in errors)

    @pytest.mark.parametrize("bad", ["red", "#12", "#12345", 7, "#GGGGGG"])
    def test_bad_colors_rejected(self, bad):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["colors"]["primary"] = bad
        errors = branding.validate_brand(brand)
        assert any("primary" in e for e in errors)

    @pytest.mark.parametrize("bad", ["twelve", "1.5", "-3px", {}])
    def test_bad_radius_rejected(self, bad):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["radius"] = bad
        assert any("radius" in e for e in branding.validate_brand(brand))

    def test_bad_appname_rejected(self):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["appName"] = 123
        assert any("appName" in e for e in branding.validate_brand(brand))


class TestRenderCss:
    def test_contains_all_vars(self, brand_dir):
        brand = branding.load_brand(brand_dir / "brand.json")
        css = branding.render_css(brand)
        for var in ("--brand-primary", "--brand-accent", "--brand-bg",
                    "--brand-surface", "--brand-text", "--brand-radius",
                    "--brand-font"):
            assert var in css, f"missing {var}"
        assert "#7c3aed" in css
        assert "0.75rem" in css

    def test_google_font_import_with_sanitized_name(self):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["font"] = "Roboto Slab"
        css = branding.render_css(brand)
        assert "Roboto+Slab" in css          # space -> + in the import URL
        assert "'Roboto Slab'" in css        # quoted in the font stack

    def test_generated_marker(self, brand_dir):
        brand = branding.load_brand(brand_dir / "brand.json")
        assert "generated" in branding.render_css(brand).lower()


class TestInjectBrand:
    def test_writes_public_files_and_assets(self, brand_dir, app_dir):
        branding.inject_brand(app_dir, brand_dir / "brand.json")
        pub = app_dir / "public"
        assert (pub / "brand.css").exists()
        assert (pub / "brand.json").exists()
        assert (pub / "logo.svg").read_bytes() == TINY_SVG
        assert (pub / "icon.png").read_bytes() == TINY_PNG

    def test_brand_json_normalizes_asset_paths(self, brand_dir, app_dir):
        branding.inject_brand(app_dir, brand_dir / "brand.json")
        on_disk = json.loads((app_dir / "public" / "brand.json").read_text())
        assert on_disk["logo"] == "logo.svg"      # was "assets/logo.svg"
        assert on_disk["favicon"] == "icon.png"   # was "assets/icon.png"
        assert on_disk["appName"] == "Freshorama Admin"

    def test_patches_tauri_conf(self, brand_dir, app_dir):
        branding.inject_brand(app_dir, brand_dir / "brand.json")
        conf = json.loads((app_dir / "src-tauri" / "tauri.conf.json").read_text())
        assert conf["productName"] == "Freshorama Admin"
        assert conf["app"]["windows"][0]["title"] == "Freshorama Admin"

    def test_tolerates_missing_tauri_conf(self, brand_dir, app_dir):
        import shutil
        shutil.rmtree(app_dir / "src-tauri")  # no tauri dir at all
        branding.inject_brand(app_dir, brand_dir / "brand.json")  # must not raise

    def test_idempotent(self, brand_dir, app_dir):
        branding.inject_brand(app_dir, brand_dir / "brand.json")
        branding.inject_brand(app_dir, brand_dir / "brand.json")  # second run OK
        assert (app_dir / "public" / "brand.css").exists()

    def test_missing_asset_file_raises(self, tmp_path, app_dir):
        (tmp_path / "brand.json").write_text(json.dumps(VALID_BRAND))
        with pytest.raises(FileNotFoundError):
            branding.inject_brand(app_dir, tmp_path / "brand.json")


# ---------------------------------------------------------------------------
# P0 hardening: strict (closed) brand.json schema + path jail on every
# write/copy. Written BEFORE the fix — these are red against the lenient
# implementation (see commit history).
# ---------------------------------------------------------------------------
import os  # noqa: E402 (kept next to the jail tests that use realpath)


class TestValidateBrandStrictSchema:
    def test_unknown_top_level_key_rejected(self):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["primaryColour"] = "#000000"  # typo'd key: dead config, must be loud
        errors = branding.validate_brand(brand)
        assert any("unknown keys" in e and "primaryColour" in e for e in errors)

    def test_unknown_color_key_rejected(self):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["colors"]["outline"] = "#000000"
        errors = branding.validate_brand(brand)
        assert any("unknown" in e and "outline" in e for e in errors)

    def test_tagline_wrong_type_rejected(self):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["tagline"] = ["manage", "things"]
        assert any("tagline" in e for e in branding.validate_brand(brand))

    def test_tagline_too_long_rejected(self):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["tagline"] = "x" * 141
        assert any("tagline" in e for e in branding.validate_brand(brand))

    def test_asset_wrong_type_rejected(self):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["logo"] = 42
        assert any("logo" in e for e in branding.validate_brand(brand))

    @pytest.mark.parametrize("bad", [
        "/etc/passwd",               # absolute-path injection
        "../../secret.svg",          # ../ chain out of the brand folder
        "assets/../../secret.svg",   # ../ buried mid-path
        "C:\\x\\logo.svg",           # windows-style absolute
    ])
    def test_escaping_asset_paths_rejected(self, bad):
        brand = json.loads(json.dumps(VALID_BRAND))
        brand["logo"] = bad
        assert any("logo" in e for e in branding.validate_brand(brand))


class TestJail:
    """_jailed(): the realpath + commonpath guard behind every read/write."""

    def test_absolute_path_outside_refused(self, tmp_path):
        with pytest.raises(ValueError, match="escape"):
            branding._jailed(tmp_path, "/etc/passwd", "test")

    def test_dotdot_chain_refused(self, tmp_path):
        with pytest.raises(ValueError, match="escape"):
            branding._jailed(tmp_path, "../evil.css", "test")

    def test_legal_absolute_spelling_allowed(self, tmp_path):
        # absolute path that already resolves INSIDE the base is accepted
        target = branding._jailed(tmp_path, str(tmp_path / "ok.css"), "test")
        assert target == Path(os.path.realpath(tmp_path / "ok.css"))


class TestInjectBrandTraversal:
    """Hostile brand.json / planted symlinks must not read or write outside."""

    @staticmethod
    def _brand_with_assets(tmp_path, **overrides):
        brand_dir = tmp_path / "brand"
        (brand_dir / "assets").mkdir(parents=True)
        (brand_dir / "assets" / "logo.svg").write_bytes(TINY_SVG)
        (brand_dir / "assets" / "icon.png").write_bytes(TINY_PNG)
        brand = json.loads(json.dumps(VALID_BRAND))
        brand.update(overrides)
        (brand_dir / "brand.json").write_text(json.dumps(brand))
        return brand_dir / "brand.json"

    def test_dotdot_logo_source_refused(self, tmp_path, app_dir):
        # "../secret.svg" would copy a file from OUTSIDE the brand folder
        # into the shipped app (exfiltration) — must be refused
        secret = tmp_path / "secret.svg"
        secret.write_bytes(TINY_SVG)
        brand_path = self._brand_with_assets(tmp_path, logo="../secret.svg")
        with pytest.raises(ValueError, match="logo"):
            branding.inject_brand(app_dir, brand_path)
        assert not (app_dir / "public" / "secret.svg").exists()

    def test_symlinked_asset_source_refused(self, tmp_path, app_dir):
        # brand.json is clean; the asset itself symlinks outside the brand folder
        secret = tmp_path / "id_rsa"
        secret.write_bytes(b"PRIVATE")
        brand_path = self._brand_with_assets(tmp_path)
        (brand_path.parent / "assets" / "logo.svg").unlink()
        (brand_path.parent / "assets" / "logo.svg").symlink_to(secret)
        with pytest.raises(ValueError, match="logo"):
            branding.inject_brand(app_dir, brand_path)
        assert not (app_dir / "public" / "logo.svg").exists()

    def test_symlinked_css_destination_refused(self, tmp_path, app_dir):
        # planted symlink: public/brand.css -> file outside the app
        victim = tmp_path / "stolen.txt"
        victim.write_text("KEEP ME")
        (app_dir / "public" / "brand.css").symlink_to(victim)
        brand_path = self._brand_with_assets(tmp_path)
        with pytest.raises(ValueError, match="brand.css"):
            branding.inject_brand(app_dir, brand_path)
        assert victim.read_text() == "KEEP ME"  # not clobbered through the link

    def test_symlinked_logo_destination_refused(self, tmp_path, app_dir):
        # shutil.copy2 follows a planted destination symlink — must be refused
        victim = tmp_path / "stolen.png"
        victim.write_bytes(b"KEEP ME")
        (app_dir / "public" / "logo.svg").symlink_to(victim)
        brand_path = self._brand_with_assets(tmp_path)
        with pytest.raises(ValueError, match="logo"):
            branding.inject_brand(app_dir, brand_path)
        assert victim.read_bytes() == b"KEEP ME"

    def test_symlinked_tauri_conf_refused(self, tmp_path, app_dir):
        # tauri.conf.json symlinked outside src-tauri/ must not be patched
        victim = tmp_path / "tauri.victim.json"
        victim.write_text("{}")
        conf = app_dir / "src-tauri" / "tauri.conf.json"
        conf.unlink()
        conf.symlink_to(victim)
        brand_path = self._brand_with_assets(tmp_path)
        with pytest.raises(ValueError, match="tauri.conf.json"):
            branding.inject_brand(app_dir, brand_path)
        assert victim.read_text() == "{}"


# ---------------------------------------------------------------------------
# Production CSP: the shipped tauri.conf.json carries connect-src
# 'self' https://API_HOST; build_admin --api-host substitutes the deployed
# origin at build time. Covers normalize_api_host (closed shape: https,
# dotted DNS, optional port — localhost/loopback/wildcards/paths/userinfo
# fail loudly), substitute_api_host (idempotent, drift fails) and
# inject_brand(api_host=...) end to end.
# ---------------------------------------------------------------------------

PROD_CSP = (
    "default-src 'self'; connect-src 'self' https://API_HOST; "
    "script-src 'self'; img-src 'self'; font-src 'self'; "
    "media-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'"
)


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
    def test_without_api_host_placeholder_stays(self, brand_dir, app_dir_csp):
        branding.inject_brand(app_dir_csp, brand_dir / "brand.json")
        conf = json.loads((app_dir_csp / "src-tauri" / "tauri.conf.json").read_text())
        assert "https://API_HOST" in conf["app"]["security"]["csp"]
        assert conf["productName"] == "Freshorama Admin"   # other patching intact

    def test_with_api_host_substitutes_in_written_conf(self, brand_dir, app_dir_csp):
        summary = branding.inject_brand(app_dir_csp, brand_dir / "brand.json",
                                        api_host="https://admin.freshorama.com")
        conf = json.loads((app_dir_csp / "src-tauri" / "tauri.conf.json").read_text())
        csp = conf["app"]["security"]["csp"]
        assert "https://admin.freshorama.com" in csp
        assert "API_HOST" not in csp
        assert "localhost" not in csp and "*" not in csp
        assert summary["csp_api_host"] == "https://admin.freshorama.com"

    def test_invalid_api_host_fails_before_any_write(self, brand_dir, app_dir_csp):
        with pytest.raises(ValueError, match="localhost"):
            branding.inject_brand(app_dir_csp, brand_dir / "brand.json",
                                  api_host="https://localhost")
        assert not (app_dir_csp / "public" / "brand.css").exists()  # nothing written

    def test_summary_reports_no_substitution_without_api_host(self, brand_dir, app_dir_csp):
        summary = branding.inject_brand(app_dir_csp, brand_dir / "brand.json")
        assert summary["csp_api_host"] is None
