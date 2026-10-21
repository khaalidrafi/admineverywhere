"""Proof-fixture drift gate: the rig's REAL schema must equal the captured one.

The thin client's entire evidence law (transitionPath/historyPath/exportPath/
mePath binding, the hoisted ``<Model>Request`` components of
``COMPONENT_SPLIT_REQUEST``, the enum component names) is pinned by
``app/src/lib/__tests__/fixtures/openapi.json`` — a document *captured* from
this rig over HTTP. Captures rot: docs/order-lifecycle.md commands "recapture
it whenever the rig gains an endpoint — a client test that passes against a
document the server no longer answers is not proof", but until this file that
was only prose, and nothing in either suite could tell a faithful capture from
a stale one.

Why a SUBPROCESS with the rig's own ``core.settings`` and not the in-process
pattern of test_csv_export.py's schema test: conftest scopes the rig to those
modules with ``SPECTACULAR_SETTINGS`` lacking ``COMPONENT_SPLIT_REQUEST``
(which ``core/settings.py`` sets), so an in-process generation there produces
a materially different document (measured 2026-10-21: 12 of 13 paths differ
from the fixture, the ``OrderRequest``/``Patched*`` components absent). The
fixture mirrors the running rig, so the rig's real settings are the only
honest reference.

Skips only when the rig or the fixture is absent (a plugin-only or app-only
checkout). A drift is a FAILURE, never a skip — that is the whole point.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = REPO_ROOT / "demo-backend"
FIXTURE = REPO_ROOT / "app" / "src" / "lib" / "__tests__" / "fixtures" / "openapi.json"

pytestmark = pytest.mark.skipif(
    not (DEMO_ROOT / "manage.py").exists() or not FIXTURE.exists(),
    reason="demo rig or client proof fixture not present in this checkout",
)

# The halves that carry the contract are compared per test below (`paths`,
# `components.schemas`). `info` is excluded: it is title/version decoration
# the client does not bind paths from, and the test-profile title differs
# from the rig's by design.


@pytest.fixture(scope="module")
def live_schema(tmp_path_factory):
    """`manage.py spectacular` under the rig's real settings (core.settings)."""
    out = tmp_path_factory.mktemp("schema") / "live-openapi.json"
    proc = subprocess.run(
        [sys.executable, "manage.py", "spectacular", "--format", "openapi-json",
         "--file", str(out)],
        cwd=str(DEMO_ROOT),
        env={
            **os.environ,
            "PYTHONPATH": str(DEMO_ROOT),
            "DJANGO_SETTINGS_MODULE": "core.settings",
            "DEMO_DEV": "1",  # ack for the DEV-ONLY settings warning
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0 and out.exists(), (
        "the rig cannot generate its own schema — "
        f"rc={proc.returncode}\nstderr[-1500:]\n{proc.stderr[-1500:]}"
    )
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def captured_schema():
    return json.loads(FIXTURE.read_text())


def _canon(obj):
    return json.dumps(obj, sort_keys=True)


def _diff_map(live: dict, captured: dict, kind: str) -> list:
    drift = []
    for key in sorted(set(live) | set(captured)):
        if key not in live:
            drift.append(f"{kind} {key!r} is in the fixture but the rig no longer serves it")
        elif key not in captured:
            drift.append(f"{kind} {key!r} exists on the rig but was never captured into the fixture")
        elif _canon(live[key]) != _canon(captured[key]):
            drift.append(f"{kind} {key!r} differs between the rig and the fixture")
    return drift


class TestProofFixtureDrift:
    def test_live_paths_match_captured(self, live_schema, captured_schema):
        """Every documented path must be byte-identical to the capture."""
        drift = _diff_map(
            live_schema.get("paths", {}), captured_schema.get("paths", {}), "path"
        )
        assert not drift, (
            "the client proof fixture has drifted from the rig it claims to "
            f"capture ({len(drift)} finding(s)):\n  "
            + "\n  ".join(drift)
            + "\n  Recapture: boot the rig and GET /api/schema/?format=json "
            "into app/src/lib/__tests__/fixtures/openapi.json"
        )

    def test_live_components_match_captured(self, live_schema, captured_schema):
        drift = _diff_map(
            live_schema.get("components", {}).get("schemas", {}),
            captured_schema.get("components", {}).get("schemas", {}),
            "component",
        )
        assert not drift, (
            f"component schemas drifted ({len(drift)} finding(s)):\n  "
            + "\n  ".join(drift)
        )

    def test_split_request_components_survive(self, live_schema):
        """The rig still runs COMPONENT_SPLIT_REQUEST (core/settings.py) —
        the hoisted <Model>Request shapes RecordForm binds."""
        comps = live_schema.get("components", {}).get("schemas", {})
        for name in ("OrderRequest", "ProductRequest", "CustomerRequest"):
            assert name in comps, (
                f"{name!r} is gone from the rig's live schema — the split-request "
                "contract (docs/independent-enums.md, RecordForm) broke server-side"
            )

    def test_evidence_law_endpoints_documented(self, live_schema):
        """The four discovery bindings the client refuses to guess: POST
        transition, GET-only history, GET-only export, GET-only me."""
        paths = live_schema.get("paths", {})
        t = paths.get("/api/orders/{id}/transition/", {})
        assert "post" in t, "transition lost its documented POST — client must now refuse lifecycle"
        h = paths.get("/api/orders/{id}/history/", {})
        assert set(h) == {"get"}, f"history must be get-only, found {sorted(h)}"
        e = paths.get("/api/orders/export/", {})
        assert set(e) == {"get"}, f"export must be get-only, found {sorted(e)}"
        m = paths.get("/api/me/", {})
        assert set(m) == {"get"}, f"me must be get-only (a POST would hide claims-binding), found {sorted(m)}"
