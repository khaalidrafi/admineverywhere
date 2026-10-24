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
    count it is supposed to produce — and since the population pin below, the
    count is compared against a literal, not merely printed. That pin exists
    because the sentence was a lie until it was measured: one test file removed
    made this gate answer ``297 passed`` and GATE GREEN, rc 0 (measured on the
    delivered tree; DEVGUIDE ELEVENTH law).

Exit codes follow docs/DEVGUIDE.md FIFTH law: 0 = gate green, 1 = a gate leg
is genuinely RED, 2 = the gate could not be RUN (missing interpreter deps,
missing node_modules, a tool that cannot launch). Launch failures are 2, never
1 — a check that cannot start has no opinion about your diff. ``--fe`` adds the
vitest leg (not part of the merge gate, but every seat is told to keep it
green) plus the five twin harnesses (csv/brand/parity byte identity, the
machine-gate roster and the drop-in registry roster — the claims NO single suite
can see, since each writer is green against its own fixture) and refuses with 2
when ``app/node_modules`` is absent.

Usage (from the repo root):
  python3 scripts/landing_gate.py          # the three merge-gate legs
  python3 scripts/landing_gate.py --fe     # plus vitest and the twin harnesses
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

# POPULATION PIN (DEVGUIDE ELEVENTH law). A leg that prints a count must be
# graded against the count it OWES, not against "a count was printed". Measured
# pre-fix on this very file, on the delivered tree: one pytest test file removed
# answered `pytest 297 passed` and GATE GREEN rc 0; one vitest file removed
# answered 411 tests over 30 files, rc 0. Neither writer was asked about the
# coverage that had vanished — the same hole the three twin harnesses were fixed
# for, surviving in the one parent gate every merge replays, while the docstring
# above already promised "the count it is supposed to produce".
# When a suite legitimately changes, bump these literals IN THE SAME COMMIT as
# the diff — the ritual, not an obstacle: these numbers are also quoted in
# AGENTS.md and the CI header, and an unpinned drift silently rewrites every
# report that cites them. The direction of the mismatch is named in the verdict:
# shrank = coverage lost, grew = the pin went stale, both must be red until the
# tree and its claimed population agree.
EXPECTED_PYTEST = 300
EXPECTED_VITEST = 467
EXPECTED_VITEST_FILES = 37

# THE SAME LAW, APPLIED TO THE ROSTER ITSELF. The pin above grades the COUNTS the
# legs print; it said nothing about which LEGS run, so the parent gate could pass a
# merge while silently not running one of the three checks AGENTS.md defines.
# Measured pre-fix on the delivered tree, both rc 0 / GATE GREEN:
#   * the `migrations` leg deleted from the roster -> the gate ran 2 verdict legs
#     and closed with "every leg above asserted its own output" — a sentence that is
#     true of the legs that ran and blind to the one that did not;
#   * `parity-twin` deleted from TWINS -> `--fe` compared two of the three twin
#     pairs and called the byte-identity claim proven.
# So the roster is pinned by ORDERED LABELS (identity, population and order at once:
# `env` must stay first because it exists to stop a swallowed install from wearing
# pytest's exit 2 as a red tree). Edit the roster without editing the expectation and
# the gate refuses to run — which, unlike the counts above, is CANNOT RUN and not RED:
# a wrong roster means this file is no longer the gate finalize replays, so it has no
# opinion about the diff in front of it.
MERGE_ROSTER = ("env", "pytest", "check", "migrations")
FE_ROSTER = ("vitest", "csv-twin", "brand-twin", "parity-twin", "gate-twin", "registry-twin", "doc-twin")
# Third, INDEPENDENT source for the twin legs: the harnesses that exist on disk. The
# roster and a literal are two copies of one intent (the weakest pin the twins were
# fixed for); the filesystem is not, so an extra *_diff.py harness written and never
# wired into the gate, or a roster naming a script that is gone, both fire here.
EXPECTED_TWINS = 6

# WHAT EACH MERGE LEG ACTUALLY RUNS — the contract in one place, and EXECUTED by the
# legs, not described beside them. This exists because of a fourth member of the same
# family: the gate the machine replays on every merge is .github/scripts/gate.sh
# (Lead-owned, called from .github/workflows/agent-team.yml), and AGENTS.md claims the
# two "run the same". That claim had no measurement — a seat could keep this file honest
# while the real merge gate silently dropped a leg or stopped capturing a failure. The
# twin in scripts/gate_roster_diff.py diffs gate.sh's executed commands against the
# spec below, so the spec is the one source of truth BOTH sides are graded against;
# `python` in argv[0] is the launcher placeholder this file re-spells with --python.
MERGE_COMMANDS = {
    "pytest": (".", ("python", "-m", "pytest", "plugin/tests",
                     "-p", "no:cacheprovider", "-q")),
    "check": ("demo-backend", ("python", "manage.py", "check")),
    "migrations": ("demo-backend",
                   ("python", "manage.py", "makemigrations", "--check", "--dry-run")),
}
# The one leg gate.sh is allowed not to run: the dep preflight is this file's own
# addition (EIGHTH law), so its absence there is a documented difference, not drift.
# The twin fires if the exemption ever stops applying (release_readiness's
# reverse-bite rule: an exemption that covers nothing reads as "handled").
ALLOWED_MACHINE_ABSENCE = ("env",)


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


def population(leg, got, want, carrier):
    """Grade a printed count against the count the leg owes (ELEVENTH law)."""
    got = int(got)
    if got == want:
        return
    if got < want:
        verdict = "SHRANK — coverage lost: printed %s, owes %s (delta %d)"
        remedy = ("restore the vanished tests, or bump %s in scripts/landing_gate.py "
                  "in the SAME commit as a deliberate deletion" % carrier)
    else:
        verdict = "GREW — the pin is stale: printed %s, owes %s (delta %d)"
        remedy = ("bump %s in scripts/landing_gate.py in the SAME commit as the "
                  "added tests" % carrier)
    raise LegRed("%s: %s. %s. A printed count with no expectation attached is "
                 "green over whatever coverage is left."
                 % (leg, verdict % (got, want, abs(got - want)), remedy))


def pin_roster(labels, fe):
    """Refuse to run if the leg roster is not the roster this gate advertises."""
    owed = list(MERGE_ROSTER) + (list(FE_ROSTER) if fe else [])
    if sorted(MERGE_COMMANDS) != sorted(l for l in MERGE_ROSTER
                                        if l not in ALLOWED_MACHINE_ABSENCE):
        raise CannotRun("MERGE_COMMANDS (%s) is not MERGE_ROSTER minus the allowed "
                        "absences (%s) — a leg would run an argv this file does not "
                        "advertise, and the machine-gate twin would then diff against "
                        "a spec that is not the gate"
                        % (", ".join(sorted(MERGE_COMMANDS)),
                           ", ".join(MERGE_ROSTER)))
    if labels == owed:
        return
    missing = [l for l in owed if l not in labels]
    extra = [l for l in labels if l not in owed]
    detail = []
    if missing:
        detail.append("MISSING %s (coverage the merge/finalize replay would not get)"
                      % ", ".join(missing))
    if extra:
        detail.append("UNDECLARED %s (a leg this file does not advertise)"
                      % ", ".join(extra))
    if not detail:
        detail.append("ORDER changed: got %s, owes %s — the preflight must run first"
                      % (", ".join(labels), ", ".join(owed)))
    raise CannotRun(
        "the leg roster does not match the pinned roster (%d legs). %s. "
        "Fix the roster, or amend MERGE_ROSTER/FE_ROSTER in scripts/landing_gate.py "
        "in the SAME commit — and if you amend it, AGENTS.md's LANDING GATE definition "
        "and every report quoting \"%d legs\" go stale with it."
        % (len(owed), "; ".join(detail), len(MERGE_ROSTER) - 1))


def twin_roster_on_disk():
    return sorted(p.name for p in (ROOT / "scripts").glob("*_diff.py"))


def pin_twins():
    """The TWINS roster vs the harnesses that actually exist — two independent views."""
    on_disk = twin_roster_on_disk()
    named = sorted(script for _, script, _probe in TWINS)
    if len(TWINS) != EXPECTED_TWINS:
        raise CannotRun("TWINS lists %d harness(es), EXPECTED_TWINS pins %d. A twin "
                        "deleted from the roster still leaves its harness on disk and "
                        "green on its own — the identity/roster claim would then cover "
                        "less than it says. Fix the roster, or bump EXPECTED_TWINS in "
                        "the SAME commit as the deliberate change." % (len(TWINS), EXPECTED_TWINS))
    if named != on_disk:
        raise CannotRun("the TWINS roster (%s) is not the set of twin harnesses on "
                        "disk (%s) — an unwired harness is a comparison nobody runs, a "
                        "roster naming a gone harness is a leg that cannot pass."
                        % (", ".join(named), ", ".join(on_disk)))
    if [name for name, _s, _p in TWINS] != list(FE_ROSTER)[1:]:
        raise CannotRun("the TWINS labels (%s) do not match FE_ROSTER's twin slots (%s)"
                        % (", ".join(n for n, _s, _p in TWINS), ", ".join(FE_ROSTER[1:])))


def leg_pytest(py, log):
    cwd, spec = MERGE_COMMANDS["pytest"]
    proc = launch([py] + list(spec)[1:], ROOT / cwd)
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
    population("pytest", passed.group(1), EXPECTED_PYTEST, "EXPECTED_PYTEST")
    log("pytest     %s passed (plugin/tests)" % passed.group(1))


def leg_django(py, name, probe, log):
    cwd, spec = MERGE_COMMANDS[name]
    proc = launch([py] + list(spec)[1:], ROOT / cwd)
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
    population("vitest tests", tests.group(1), EXPECTED_VITEST, "EXPECTED_VITEST")
    population("vitest files", files.group(1), EXPECTED_VITEST_FILES,
               "EXPECTED_VITEST_FILES")
    log("vitest     %s passed (%s files)" % (tests.group(1), files.group(1)))


# The twin harnesses prove a claim NEITHER suite can see: AGENTS.md states each
# writer (brandToCss/render_css, csv.ts/csv_export.py, the parity table) is
# green against its OWN fixture while the byte-identity lives between them — so
# a drift where both suites stay 100% green lands behind a gate that never ran
# the comparison. Seats have been writing "siblings re-run green" in reports by
# hand; a leg turns that prose back into a measurement. The twins already speak
# the FIFTH-law grammar (0/1/2), so the mapping is direct, not invented here.
# The last two are the same law aimed at ROSTERS instead of bytes: gate-twin diffs
# the machine gate's executed commands against MERGE_COMMANDS, registry-twin diffs
# the three drop-in registries (glob dirs, populations, product importers) against
# the tree on disk — DEVGUIDE THIRTEENTH law, wired because `*_diff.py` on disk IS
# the wiring (pin_twins refuses any harness the roster does not run). doc-twin is the
# same class one layer up: it diffs the `meta{...}` field lists the two mirror docs
# promise against the fields those registries read — DEVGUIDE FOURTEENTH law.
TWINS = [("csv-twin", "csv_twin_diff.py", "BYTE-IDENTICAL"),
         ("brand-twin", "brand_twin_diff.py", "BYTE-IDENTICAL"),
         ("parity-twin", "parity_table_diff.py", "BYTE-IDENTICAL"),
         ("gate-twin", "gate_roster_diff.py", "ROSTER-IDENTICAL"),
         ("registry-twin", "registry_roster_diff.py", "REGISTRY ROSTER OK"),
         ("doc-twin", "doc_field_roster_diff.py", "DOC FIELD ROSTER OK")]


def leg_twin(py, name, script, probe, log):
    proc = launch([py, str(ROOT / "scripts" / script)], ROOT)
    out = proc.stdout + "\n" + proc.stderr
    if proc.returncode == 1:
        raise LegRed("%s (%s) rc 1 — the twins DIVERGE: %s"
                     % (name, script, tail(out)))
    if proc.returncode == 2:
        raise CannotRun("%s (%s) says it cannot run: %s" % (name, script, tail(out)))
    if proc.returncode != 0:
        raise CannotRun("%s (%s) exited %d, outside its documented 0/1/2 "
                        "contract: %s" % (name, script, proc.returncode, tail(out)))
    line = next((ln for ln in out.splitlines() if ln.startswith(probe)), None)
    if line is None:
        raise LegRed("%s rc 0 but printed no %s verdict line — exit 0 alone never "
                     "proved the compare happened: %s" % (name, probe, tail(out)))
    log("%-10s %s" % (name, line))


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

    legs = [("env", leg_env, (py, log)),
            ("pytest", leg_pytest, (py, log)),
            ("check", leg_django, (py, "check",
                                   "System check identified no issues", log)),
            ("migrations", leg_django, (py, "migrations",
                                         "No changes detected", log))]
    if opts.fe:
        legs.append(("vitest", leg_vitest, (log,)))
        legs += [(name, leg_twin, (py, name, script, probe, log))
                 for name, script, probe in TWINS]

    # Pinned before a single leg launches: a roster that drifted is not a verdict
    # about the tree, and running the survivors first would print green lines for a
    # gate that is no longer the gate finalize replays. The refusal is presented as
    # the gate's own verdict, not as a crash — "harness failure" reads like a broken
    # rig and invites a re-run of a decision that will not change (TWELFTH law).
    try:
        pin_twins()
        pin_roster([label for label, _, _ in legs], opts.fe)
    except CannotRun as exc:
        print("CANNOT RUN [roster] — %s" % exc)
        return CANNOT
    log("legs       %d (%s), each graded against its own expectation"
        % (len(legs), ", ".join(label for label, _, _ in legs)))

    failures = []
    for label, fn, args in legs:
        try:
            fn(*args)
        except CannotRun as exc:
            print("CANNOT RUN [%s] — %s" % (label, exc))
            return CANNOT
        except LegRed as exc:
            failures.append("[%s] %s" % (label, exc))
    for f in failures:
        print("RED — %s" % f)
    if failures:
        print("GATE RED (%d leg(s))" % len(failures))
        return RED
    print("GATE GREEN — %d leg(s) matched the pinned roster exactly (%s); every one "
          "of them asserted its own output, exit 0 was never enough"
          % (len(legs), "MERGE_ROSTER+FE_ROSTER" if opts.fe else "MERGE_ROSTER"))
    return GREEN


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # a crash is not a verdict: 2, never 1
        print("CANNOT RUN — harness failure %s: %s" % (type(exc).__name__, exc))
        sys.exit(CANNOT)
