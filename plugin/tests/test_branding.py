"""Tests for ai_dashboard.branding — the pure branding engine.

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

from ai_dashboard import branding

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
