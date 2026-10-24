"""The rig must boot the plugin WITHOUT an editable install of it.

`pip install -e ../plugin` is the documented boot (AGENTS.md *Commands*), and the
CI arms run it with the failure swallowed. Where the image carries no setuptools
that line is a silent no-op, so every check that touches the rig dies with
``ModuleNotFoundError: No module named 'admincraft'`` while wearing the tree's
exit code. Measured in this workspace on 2026-10-24, on the delivered tree:

  * ``python3 -m pytest plugin/tests`` -> INTERNALERROR, exit 2 — which a seat
    reads as "my work is red" (DEVGUIDE EIGHTH law, trap 1);
  * ``python3 demo-backend/manage.py check`` -> rc 1;
  * with only the in-process import patched by hand -> ``5 failed, 290 passed,
    5 errors``: the two subprocess legs stayed red because a ``python -c`` boot
    probe gets an explicit PYTHONPATH (below) that overwrites the inherited one.

Those are the numbers the Lead recorded for the duty-review lane (LANE NOTES:
"preflight PYTHONPATH=plugin/src or install setuptools in the review arm brief").
The arm brief is Lead-owned; the preflight, the rig and this suite are seat-owned,
so the fix lands here: the plugin's source tree is a sibling of this rig and
nothing about running the rig needs an install.

The priority rule is the second half of the contract. ``core.devpaths`` puts
``plugin/src`` FIRST on sys.path, so an unrelated ``admincraft`` from
site-packages can never be what the rig and this suite are actually exercising.
Every test below simulates a no-install lane with a meta-path blocker, which
makes them answer the same way whether or not the plugin happens to be installed.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = ROOT / "demo-backend"
PLUGIN_SRC = ROOT / "plugin" / "src"

# Installed in a child interpreter before anything imports the plugin: `admincraft`
# stays unresolvable until the rig's own bootstrap puts the source tree on sys.path.
# Resolving through a real editable install is the same tree, so without this the
# test would pass in an installed lane and could not see the bug at all.
BLOCKER = """
import sys
from pathlib import Path

SRC = {src!r}

class HideInstalled:
    def find_spec(self, name, path=None, target=None):
        if name != "admincraft":
            return None
        resolved = {{str(Path(p).resolve()) for p in sys.path if p}}
        if SRC in resolved:
            return None
        raise ImportError("simulated lane: admincraft is not installed")

sys.path = [p for p in sys.path if Path(p or ".").resolve() != Path(SRC)]
sys.meta_path.insert(0, HideInstalled())
"""


def child(script, cwd=None, env=None):
    return subprocess.run(
        [sys.executable, "-c", BLOCKER.format(src=str(PLUGIN_SRC)) + script],
        cwd=str(cwd or ROOT), env=env or {**os.environ, "PYTHONPATH": ""},
        capture_output=True, text=True, timeout=180,
    )


def out_and_err(proc):
    return "%s\n--- stderr ---\n%s" % (proc.stdout, proc.stderr[-2000:])


class TestPluginBootstrapsFromSource:
    def test_bootstrap_makes_the_plugin_importable(self):
        """Red before the fix: `core.devpaths` does not exist, so nothing bridges
        a no-install lane to the plugin and the import below stays refused."""
        proc = child("""
import sys
from pathlib import Path
sys.path.insert(0, {demo!r})
try:
    import admincraft
    print("IMPORTED-WITHOUT-BOOTSTRAP")
    raise SystemExit(3)
except ImportError:
    pass
from core.devpaths import ensure_admincraft_on_path, PLUGIN_SRC
label = ensure_admincraft_on_path()
import admincraft
print("label=%s" % label)
print("file=%s" % Path(admincraft.__file__).resolve())
""".format(demo=str(DEMO_ROOT)))
        assert proc.returncode == 0, out_and_err(proc)
        assert "IMPORTED-WITHOUT-BOOTSTRAP" not in proc.stdout
        assert "label=inserted" in proc.stdout, out_and_err(proc)
        loaded = [ln for ln in proc.stdout.splitlines() if ln.startswith("file=")][0]
        assert str(PLUGIN_SRC.resolve()) in loaded, loaded

    def test_bootstrap_defers_to_a_tree_already_first(self):
        """Idempotence, graded: a second call must not stack duplicate path entries."""
        proc = child("""
import sys
sys.path.insert(0, {demo!r})
from core.devpaths import ensure_admincraft_on_path, PLUGIN_SRC
sys.path.insert(0, str(PLUGIN_SRC))
print("label=%s" % ensure_admincraft_on_path())
print("count=%d" % [str(p) for p in sys.path].count(str(PLUGIN_SRC)))
""".format(demo=str(DEMO_ROOT)))
        assert proc.returncode == 0, out_and_err(proc)
        assert "label=already" in proc.stdout, out_and_err(proc)
        assert "count=1" in proc.stdout, out_and_err(proc)

    def test_child_pythonpath_carries_the_source_first(self):
        """The env the subprocess legs hand their children: the source tree must
        lead, the caller's own paths must survive, and the inherited PYTHONPATH —
        which these children overwrite by design — must not be lost."""
        proc = child("""
import sys
sys.path.insert(0, {demo!r})
from core.devpaths import child_pythonpath, PLUGIN_SRC
print(child_pythonpath({demo!r}))
""".format(demo=str(DEMO_ROOT)))
        assert proc.returncode == 0, out_and_err(proc)
        parts = [ln for ln in proc.stdout.splitlines() if os.pathsep in ln][-1].split(os.pathsep)
        assert parts[0] == str(PLUGIN_SRC), parts
        assert str(DEMO_ROOT) in parts, parts


class TestRigLauncherBootsWithoutAnInstall:
    def test_manage_py_check_runs(self, tmp_path):
        """`manage.py check` is a merge-gate leg; it must boot on a lane where the
        install is impossible, and the app it boots must be THIS tree's plugin."""
        proc = child("""
import os, runpy, sys
sys.path.insert(0, {demo!r})
from core.devpaths import ensure_admincraft_on_path
ensure_admincraft_on_path()
import admincraft
from pathlib import Path
assert str(Path(admincraft.__file__).resolve()).startswith({src!r}), admincraft.__file__
os.environ["DJANGO_SETTINGS_MODULE"] = "core.settings"
os.environ["DEMO_DEV"] = "1"
os.chdir({demo!r})
sys.argv = ["manage.py", "check"]
runpy.run_path("manage.py", run_name="__main__")
""".format(demo=str(DEMO_ROOT), src=str(PLUGIN_SRC) + os.sep))
        assert proc.returncode == 0, out_and_err(proc)
        assert "System check identified no issues" in proc.stdout + proc.stderr, out_and_err(proc)

    def test_landing_gate_env_leg_accepts_the_fallback(self, monkeypatch):
        """The gate's own preflight (DEVGUIDE EIGHTH law) refused a lane that could
        not install, so it blocked the merge gate before it could grade anything.
        It still refuses when the deps are genuinely absent — that half is the next
        test, because a preflight that never says no is not a preflight."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import landing_gate

        # The probe inherits this process's env; a launcher that exported the source
        # tree would hand the preflight the answer it is supposed to derive.
        monkeypatch.delenv("PYTHONPATH", raising=False)
        lines = []
        landing_gate.leg_env(sys.executable, lines.append)
        assert lines, "leg_env passed without logging what it probed"


    def test_landing_gate_env_leg_still_refuses_a_dead_interpreter(self, tmp_path):
        sys.path.insert(0, str(ROOT / "scripts"))
        import landing_gate

        shim = tmp_path / "no-python"
        shim.write_text("#!/bin/sh\nexit 1\n")
        shim.chmod(0o755)
        with pytest.raises(landing_gate.CannotRun):
            landing_gate.leg_env(str(shim), lambda line: None)
