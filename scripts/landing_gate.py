#!/usr/bin/env python3
"""landing_gate.py — re-run the team's LANDING GATE in one command, honestly.

The gate (AGENTS.md "LANDING GATE", seat-boundary law 7) is three server-side
checks that finalize replays before merging a branch:

  1. python -m pytest plugin/tests -p no:cacheprovider -q
  2. demo-backend: manage.py check
  3. demo-backend: manage.py makemigrations --check

A seat running those three by hand hits two failure modes that are NOT the
seat's work being red, both measured on real turns of this repo:

  * The boot install (``pip install -e plugin --no-deps -q 2>/dev/null || true``,
    mirrored in agent-team.yml) hides its own failure, so leg 1 dies with
    INTERNALERROR ``No module named 'admincraft'`` — pytest exit code 2 — and
    reads as a red tree. Leg 0 below probes the imports first and exits 2 with
    the fix command instead of letting a launcher bug impersonate a verdict.
  * Exit code 0 is not the claim. ``manage.py check`` answers 0 for a settings
    module that never booted the rig, and ``-q`` prints a summary line this
    script parses rather than trusts, so every leg asserts the phrase or the
    count it is supposed to produce.

Exit codes follow docs/DEVGUIDE.md FIFTH law: 0 = gate green, 1 = a gate leg
is genuinely RED, 2 = the gate could not be RUN (missing interpreter deps,
missing node_modules, a tool that cannot launch). Launch failures are 2, never
1 — a check that cannot start has no opinion about your diff. ``--fe`` adds the
vitest leg (not part of the merge gate, but every seat is told to keep it
green) and refuses with 2 when ``app/node_modules`` is absent.

Usage (from the repo root):
  python3 scripts/landing_gate.py          # the three merge-gate legs
  python3 scripts/landing_gate.py --fe     # plus vitest
  python3 scripts/landing_gate.py --python /path/to/exe   # force one interpreter
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GREEN, RED, CANNOT = 0, 1, 2


class CannotRun(Exception):
    pass


class LegRed(Exception):
    pass


def launch(argv, cwd, env=None):
    try:
        return subprocess.run([str(a) for a in argv], cwd=str(cwd),
                              capture_output=True, text=True, env=env)
    except OSError as exc:
        raise CannotRun("cannot launch %r: %s" % (argv[0], exc))


def tail(text, lines=6):
    body = [ln for ln in text.strip().splitlines() if ln.strip()]
    return " | ".join(body[-lines:]) if body else "<no output>"


def require(probe, why, proc):
    if probe not in proc.stdout + proc.stderr:
        raise LegRed("%s: expected %r in its output, got: %s"
                     % (why, probe, tail(proc.stdout + "\n" + proc.stderr)))


def leg_env(py, log):
    proc = launch([py, "-c",
                   "import django, rest_framework, drf_spectacular, admincraft;"
                   " print(django.get_version())"], ROOT)
    if proc.returncode != 0:
        raise CannotRun(
            "interpreter %s cannot import the plugin+rig deps (rc %d): %s\n"
            "  fix: python3 -m pip install -e ./plugin --no-deps   "
            "(a pip failure the boot script swallows looks like a red tree)"
            % (py, proc.returncode, tail(proc.stderr)))
    log("env       deps importable on %s (django %s)"
        % (py, proc.stdout.strip()))


def leg_pytest(py, log):
    proc = launch([py, "-m", "pytest", "plugin/tests",
                   "-p", "no:cacheprovider", "-q"], ROOT)
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise LegRed("pytest rc %d: %s" % (proc.returncode, tail(out)))
    passed = re.search(r"(\d+) passed\b", out)
    broke = re.search(r"(\d+) (failed|error|errors)\b", out)
    if not passed:
        raise LegRed("pytest rc 0 but no pass count in its summary — the leg "
                     "did not run the tests it claims: %s" % tail(out))
    if broke:
        raise LegRed("pytest rc 0 while reporting %s %s — the summary and the "
                     "exit code disagree: %s" % (broke.group(1), broke.group(2),
                                                 tail(out)))
    collected = re.search(r"collected (\d+) items", out)
    if collected and int(collected.group(1)) < int(passed.group(1)):
        raise LegRed("pytest collected %s but passed %s"
                     % (collected.group(1), passed.group(1)))
    log("pytest     %s passed (plugin/tests)" % passed.group(1))


def leg_django(py, name, argv, probe, log):
    proc = launch([py, "manage.py"] + argv, ROOT / "demo-backend")
    if proc.returncode != 0:
        raise LegRed("%s rc %d: %s" % (name, proc.returncode,
                                       tail(proc.stdout + "\n" + proc.stderr)))
    require(probe, name, proc)
    log("%-10s %s" % (name, probe))


def leg_vitest(log):
    node_modules = ROOT / "app" / "node_modules"
    if not node_modules.is_dir():
        raise CannotRun("app/node_modules is absent — the vitest leg cannot run. "
                        "fix: cd app && npm ci")
    proc = launch(["npx", "vitest", "run", "--maxWorkers=1"], ROOT / "app",
                  dict(os.environ, NODE_OPTIONS="--max-old-space-size=1024"))
    if proc.returncode != 0:
        raise LegRed("vitest rc %d: %s" % (proc.returncode,
                                           tail(proc.stdout + "\n" + proc.stderr)))
    tests = re.search(r"Tests\s+(\d+) passed", proc.stdout)
    files = re.search(r"Test Files\s+(\d+) passed", proc.stdout)
    if not tests or not files:
        raise LegRed("vitest rc 0 but its passed-counts are not in the summary "
                     "- the leg did not run what it claims: %s" % tail(proc.stdout))
    log("vitest     %s passed (%s files)" % (tests.group(1), files.group(1)))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", dest="py", default=sys.executable,
                        help="interpreter to run the server legs with (default: this one)")
    parser.add_argument("--fe", action="store_true",
                        help="also run the vitest leg (not part of the merge gate)")
    opts = parser.parse_args(argv)
    py = opts.py

    def log(line):
        print(line)

    legs = [(leg_env, (py, log)), (leg_pytest, (py, log)),
            (leg_django, (py, "check", ["check"],
                          "System check identified no issues", log)),
            (leg_django, (py, "migrations",
                          ["makemigrations", "--check", "--dry-run"],
                          "No changes detected", log))]
    if opts.fe:
        legs.append((leg_vitest, (log,)))

    failures = []
    for fn, args in legs:
        try:
            fn(*args)
        except CannotRun as exc:
            print("CANNOT RUN — %s" % exc)
            return CANNOT
        except LegRed as exc:
            failures.append(str(exc))
    for f in failures:
        print("RED — %s" % f)
    if failures:
        print("GATE RED (%d leg(s))" % len(failures))
        return RED
    print("GATE GREEN — every leg above asserted its own output, exit 0 was never enough")
    return GREEN


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # a crash is not a verdict: 2, never 1
        print("CANNOT RUN — harness failure %s: %s" % (type(exc).__name__, exc))
        sys.exit(CANNOT)
