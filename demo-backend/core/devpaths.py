"""Dev-rig bootstrap: the rig imports the plugin from this repo's source tree.

The documented boot is `pip install -e ../plugin`, and the CI arms run it with the
failure swallowed — so on an image without setuptools (measured on the duty-review
lane, 2026-10-24: `pip install -e /workspace/plugin --no-deps -q 2>/dev/null || true`
is a no-op there) the rig cannot import `admincraft`, which is in its INSTALLED_APPS.
That made three of the four landing-gate legs impossible to run in that lane: pytest
died with INTERNALERROR (exit 2, indistinguishable from a red tree), `manage.py check`
returned rc 1, and the two subprocess tests stayed red because they hand their
children an explicit PYTHONPATH that overwrites the inherited one.

The install is a convenience for a *server* project that pip-installs the plugin; it
was never a requirement for running this rig, whose whole purpose is to exercise the
plugin sitting one directory over. So `ensure_admincraft_on_path()` puts
`plugin/src` FIRST on sys.path and `child_pythonpath()` carries it into subprocesses.

Source-first is deliberate, not incidental: it also refuses an unrelated
`admincraft` from site-packages the role of "the app under test" in a suite that
exists to grade this tree. A lane with a real editable install resolves the same
files either way, so nothing changes there.
"""
import os
import sys
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_SRC = DEMO_ROOT.parent / "plugin" / "src"


def _source_present():
    return (PLUGIN_SRC / "admincraft" / "__init__.py").is_file()


def ensure_admincraft_on_path():
    """Make this checkout's plugin importable. Idempotent.

    Returns "inserted" when it had to bridge the lane, "already" when the source
    tree is already first, and "absent" when this checkout carries no plugin
    source (a plugin-only or packaged checkout — nothing to bridge, and the
    caller's own import decides whether that is a failure).
    """
    if not _source_present():
        return "absent"
    if sys.path and str(sys.path[0]) == str(PLUGIN_SRC):
        return "already"
    sys.path.insert(0, str(PLUGIN_SRC))
    return "inserted"


def child_pythonpath(*paths):
    """PYTHONPATH for a child interpreter: the source tree leads, then the paths
    the caller needs, then whatever the parent was already given."""
    parts = [str(PLUGIN_SRC)] if _source_present() else []
    parts += [str(p) for p in paths]
    inherited = os.environ.get("PYTHONPATH")
    if inherited:
        parts += [p for p in inherited.split(os.pathsep) if p and p not in parts]
    return os.pathsep.join(parts)
