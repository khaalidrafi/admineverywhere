#!/usr/bin/env python3
"""Does the chain's own check family stay findable and runnable — or does a harness land dead?

WHY this exists (measured on the delivered tree, 2026-10-25, seat software-engineer).
This repo's answer to "prose that cannot be re-run" is a scripts/ family of graders:
six `*_diff.py` twins the landing gate replays, plus a growing set of `*_check.py` and
`*_probe.py` harnesses. The twins are population-pinned (landing_gate.py's
EXPECTED_TWINS cross-check refuses a `*_diff.py` on disk that its roster does not run,
and vice versa). The rest of the family is in NOBODY's domain:

  1. `python3 scripts/slot_reader_probe.py` — the harness that measures the inert
     non-clobber guard (the exact 27748d9 clobber class the Lead calls the root of the
     register treadmill) — landed on ai/main with the 1552 merge at 04:14Z and is
     cited by ZERO lines of AGENTS.md and ZERO lines of docs/DEVGUIDE.md. Nothing in
     CI runs it either: grepping every `.github/` file for a `scripts/*.py` reference
     returns NOTHING AT ALL — this whole family is run BY INSTRUCTION, by a seat or the
     Lead who read it in one of the two mirror docs. A check nobody can find is a check
     nobody runs, and its RED finding (the guard is still inert) stays invisible to
     everyone who does not already know it exists.
  2. `chat_feature_check.py` is cited in DEVGUIDE only OUTSIDE its `## Commands`
     region — so a reader who walks the command table never learns the chat feature is
     graded at all.

The law this harness pins is therefore the one this repo already enforces for suite
counts (release_readiness's `doc-counts` leg grades counts published AS AN INSTRUCTION
inside `## Layout` / `## Commands`, "the class a reader FOLLOWS"): a grader must be
published in the command table of BOTH mirror docs, and every invocation it publishes
must be an invocation the grader actually accepts.

FOUR LEGS, all read-only:

  population  the grader files on disk are one pinned roster — by NAME and by count.
              A vanished harness is CANNOT RUN, never a quieter green: a comparison
              cannot see its own coverage (DEVGUIDE ELEVENTH law, the same rule that
              caught truncated SENTINELS in the CSV twins and deleted controls here).
  publish     every harness in that roster has at least one row inside the
              `## Commands` region of AGENTS.md AND of docs/DEVGUIDE.md. The region is
              the domain, not the whole file: prose elsewhere does not tell a reader
              which command to run.
  invoke      every `scripts/<harness>.py --flag` a mirror doc prints is a flag that
              harness declares (argparse `add_argument("--flag")`). This is the inverse
              hazard — a doc promising a mode that does not exist is the instruction a
              seat then runs, hits argparse's exit 2, and reports as tooling rot.
  ghost       no mirror doc prints a `*_diff|_check|_probe.py` instruction for a file
              that is not on disk (a dead instruction is not a green one).

Printed as a LIVE note, deliberately NOT a leg: how many of these graders CI actually
invokes. Measured answer today: zero of thirteen. That is the reason the publish leg
exists, so it is stated where a reader can see it rather than asserted in prose.

Usage: python3 scripts/harness_roster_check.py [--root TREE] [--selftest]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The two mirror docs, and the region inside them a reader follows.
MIRROR_DOCS = ("AGENTS.md", "docs/DEVGUIDE.md")
COMMANDS_REGION = "## Commands"

# Grader filename patterns. A generator (scripts/gen_icon.py) or a rig
# (scripts/mock_openai.js) is not a grader and stays out of domain.
GRADER_SUFFIXES = ("_diff.py", "_check.py", "_probe.py")

# PINNED, not derived (landing_gate's EXPECTED_TWINS law, chain_slot_check's
# EXPECTED_CONTROLS law): the roster is the harness's own expectation, so a file
# vanishing or arriving is a refusal this harness understands, not a smaller green.
EXPECTED_HARNESS = 21
EXPECTED_NAMES = (
    "brand_twin_diff.py",
    "chain_merge_check.py",
    "chain_patch_check.py",
    "chain_session_check.py",
    "chain_slot_check.py",
    "chain_test_check.py",
    "chat_feature_check.py",
    "chat_when_check.py",
    "csv_twin_diff.py",
    "doc_field_roster_diff.py",
    "gate_roster_diff.py",
    "harness_image_check.py",
    "harness_roster_check.py",
    "lane_budget_check.py",
    "parity_table_diff.py",
    "rbac_live_check.py",
    "ref_prune_check.py",
    "registry_roster_diff.py",
    "review_preflight_check.py",
    "review_verdict_check.py",
    "slot_reader_probe.py",
)


class Red(Exception):
    pass


class CannotRun(Exception):
    pass


def is_grader(name):
    return name.endswith(GRADER_SUFFIXES)


def harnesses_on_disk(root):
    scripts = os.path.join(root, "scripts")
    if not os.path.isdir(scripts):
        raise CannotRun("no scripts/ directory under %s — this is not the repo root" % root)
    return tuple(sorted(n for n in os.listdir(scripts)
                        if n.endswith(GRADER_SUFFIXES) and not n.startswith(".")))


def commands_region(text, source):
    match = re.search(r"^## Commands\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        raise CannotRun("%s carries no %r region — the harness cannot grade a table "
                        "that is not there (a missing region would let every publish "
                        "claim pass on an empty string)" % (source, COMMANDS_REGION))
    return match.group(1)


def declared_flags(root, name):
    """Flags the harness itself declares: argparse add_argument("--x") literals."""
    path = os.path.join(root, "scripts", name)
    try:
        text = open(path, "r").read()
    except IOError as exc:
        raise CannotRun("cannot read scripts/%s to grade its flags: %s" % (name, exc))
    return set(re.findall(r'add_argument\(\s*"(--[a-z][a-z0-9-]*)"', text)) \
         | set(re.findall(r'==\s*"(--[a-z][a-z0-9-]*)"', text))


def cited_invocations(text, name):
    """(flag, line_no) for every `scripts/<name> --flag` a doc prints, anywhere."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for match in re.finditer(r"scripts/%s(\s+(--[a-z][a-z0-9-]*))?" % re.escape(name), line):
            if match.group(1):
                hits.append((match.group(2), lineno, line.strip()))
    return hits


def print_live_note(root):
    refs = []
    github = os.path.join(root, ".github")
    for base, _dirs, files in os.walk(github):
        for fname in files:
            if not fname.endswith((".yml", ".yaml", ".sh")):
                continue
            try:
                body = open(os.path.join(base, fname), "r").read()
            except IOError:
                continue
            refs.extend(re.findall(r"scripts/[A-Za-z0-9_]+\.(?:py|js)", body))
    graded = set(harnesses_on_disk(root))
    invoked = sorted(set(os.path.basename(r) for r in refs) & graded)
    print("  LIVE     %d of %d grader(s) are invoked anywhere under .github/: %s"
          % (len(invoked), len(graded), ", ".join(invoked) if invoked else "NONE"))
    print("           so this family runs BY INSTRUCTION — which is what the publish "
          "leg grades, not a CI wiring claim.")


def grade(root):
    disk = harnesses_on_disk(root)
    if len(disk) != EXPECTED_HARNESS or disk != tuple(EXPECTED_NAMES):
        missing = sorted(set(EXPECTED_NAMES) - set(disk))
        extra = sorted(set(disk) - set(EXPECTED_NAMES))
        raise CannotRun("the grader roster on disk holds %d file(s); this harness pins "
                        "%d by name. vanished: %s / unrostered: %s. A comparison cannot "
                        "see its own coverage, so a roster that no longer matches its "
                        "pin is a refusal, never a quieter green — fix the pin in the "
                        "SAME commit as a deliberate change."
                        % (len(disk), EXPECTED_HARNESS,
                           ", ".join(missing) if missing else "none",
                           ", ".join(extra) if extra else "none"))

    docs = {}
    for rel in MIRROR_DOCS:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            raise CannotRun("mirror doc %s is missing — the publish leg has no table "
                            "to read" % rel)
        docs[rel] = open(path, "r").read()

    print_live_note(root)

    reds = []
    graded_flags = 0
    for name in disk:
        regions = dict((rel, commands_region(text, rel)) for rel, text in docs.items())
        unpublished = [rel for rel, region in regions.items() if name not in region]
        if unpublished:
            reds.append("PUBLISH %s: no row inside %r of %s — a grader a reader cannot "
                        "find in the command table is a grader nobody runs"
                        % (name, COMMANDS_REGION, " and ".join(unpublished)))

        own = None
        for rel, text in docs.items():
            for flag, lineno, line in cited_invocations(text, name):
                if own is None:
                    own = declared_flags(root, name)
                graded_flags += 1
                if flag not in own:
                    reds.append("INVOKE %s: %s:%d prints %r but scripts/%s declares only "
                                "%s — a doc promising a mode that does not exist is run "
                                "and reported as tooling rot"
                                % (name, rel, lineno, flag, name,
                                   ", ".join(sorted(own)) or "no flags"))

    ghost_pat = re.compile(r"scripts/([A-Za-z0-9_]+(?:_diff|_check|_probe)\.py)")
    for rel, text in docs.items():
        for match in ghost_pat.finditer(text):
            if match.group(1) not in disk:
                raise CannotRun("%s prints an instruction for scripts/%s, which is not on "
                                "disk — grading a dead instruction would report the file "
                                "as missing rather than the doc as stale" % (rel, match.group(1)))

    if reds:
        raise Red("\n".join(reds))
    print("HARNESS ROSTER OK — %d grader(s) on disk equal the pinned roster, every one "
          "published in the %r region of both mirror docs, %d invocation flag(s) graded "
          "against the flag each harness actually declares"
          % (len(disk), COMMANDS_REGION, graded_flags))
    return 0


# --------------------------------------------------------------------------- controls

def _write(path, text):
    with open(path, "w") as handle:
        handle.write(text)


def _read(path):
    with open(path, "r") as handle:
        return handle.read()


def build_green(root):
    """Make the copy satisfy the publish law, so a control fires on ITS mutation only."""
    disk = harnesses_on_disk(root)
    for rel in MIRROR_DOCS:
        path = os.path.join(root, rel)
        text = _read(path)
        region = commands_region(text, rel)
        rows = "\n".join("python3 scripts/%s   # control row" % name
                         for name in disk if name not in region)
        if rows:
            _write(path, text.replace(region, region + rows + "\n", 1))


def control_no_change(root):
    pass


def control_delete_harness(root):
    victim = os.path.join(root, "scripts", "slot_reader_probe.py")
    if not os.path.isfile(victim):
        raise AssertionError("no slot_reader_probe.py in the copy")
    os.remove(victim)


def control_unpublish_both(root):
    for rel in MIRROR_DOCS:
        path = os.path.join(root, rel)
        text = _read(path)
        region = commands_region(text, rel)
        kept = "\n".join(line for line in region.splitlines()
                         if "slot_reader_probe.py" not in line)
        _write(path, text.replace(region, kept + "\n", 1))


def control_unpublish_one_doc(root):
    rel = "docs/DEVGUIDE.md"
    path = os.path.join(root, rel)
    text = _read(path)
    region = commands_region(text, rel)
    kept = "\n".join(line for line in region.splitlines()
                     if "slot_reader_probe.py" not in line)
    _write(path, text.replace(region, kept + "\n", 1))


def control_ghost_flag(root):
    path = os.path.join(root, "AGENTS.md")
    text = _read(path)
    region = commands_region(text, "AGENTS.md")
    _write(path, text.replace(region,
                              region + "python3 scripts/csv_twin_diff.py --nope-mode\n", 1))


def control_ghost_file(root):
    path = os.path.join(root, "AGENTS.md")
    text = _read(path)
    region = commands_region(text, "AGENTS.md")
    _write(path, text.replace(region,
                              region + "python3 scripts/ghost_roster_diff.py\n", 1))


def control_uncited_newcomer(root):
    _write(os.path.join(root, "scripts", "fresh_probe.py"),
           '#!/usr/bin/env python3\n"""A new grader nobody published."""\n'
           "import argparse\nimport sys\n\n"
           "def main(argv):\n"
           "    parser = argparse.ArgumentParser()\n"
           '    parser.add_argument("--selftest", action="store_true")\n'
           "    return 0\n\n"
           'if __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))\n')


def control_retune_pin(root):
    path = os.path.join(root, "scripts", "harness_roster_check.py")
    text = _read(path)
    # the literal is derived, not hardcoded: a pin bump in a landing commit must
    # not rot this control (the retune target's SHAPE is the contract, not the era's number)
    pin = "EXPECTED_HARNESS = %d" % EXPECTED_HARNESS
    if pin not in text:
        raise AssertionError("the pin this control retunes is not spelled as expected")
    _write(path, text.replace(pin, "EXPECTED_HARNESS = 12", 1))


def control_missing_region(root):
    path = os.path.join(root, "AGENTS.md")
    text = _read(path)
    _write(path, text.replace("## Commands", "## Something Else", 1))


# (name, mutation, expected rc, expected text, build the green baseline first?,
#  run the COPY's script?) — the last flag exists because one control mutates THIS
# file's own pin, and a shipped script reading a retuned copy proves nothing: the
# mutation has to be the script that runs, exactly as it is when a seat edits a pin
# and runs it.
CONTROLS = (
    ("honest run is green", control_no_change, 0, "HARNESS ROSTER OK", True, False),
    ("harness vanished from disk", control_delete_harness, 2, "roster on disk holds %d" % (EXPECTED_HARNESS - 1), True, False),
    ("row pulled from both docs", control_unpublish_both, 1, "PUBLISH slot_reader_probe.py", True, False),
    ("row pulled from one doc", control_unpublish_one_doc, 1, "DEVGUIDE.md", True, False),
    ("doc prints a flag the harness lacks", control_ghost_flag, 1, "INVOKE csv_twin_diff.py", True, False),
    ("doc prints a file that is not on disk", control_ghost_file, 2, "not on", True, False),
    ("new grader lands unpublished", control_uncited_newcomer, 2, "unrostered: fresh_probe.py", True, False),
    ("pin retuned without a change", control_retune_pin, 2, "this harness pins 12", True, True),
    ("command table renamed away", control_missing_region, 2, "carries no", True, False),
)
EXPECTED_CONTROLS = 9


def selftest(root):
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d control(s) but this harness pins %d "
                        "- its population is no longer its own expectation"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = os.path.join(root, "scripts", "harness_roster_check.py")
    failures = []
    for name, mutation, expected_rc, expected_text, green_base, copy_script in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="harness-roster-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                          ".pytest_cache", "dist", "build",
                                                          ".git"))
            if green_base:
                build_green(target)
            mutation(target)
            runner = os.path.join(target, "scripts", "harness_roster_check.py") \
                if copy_script else script
            proc = subprocess.run([sys.executable, runner, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-38s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
            else:
                failures.append("%s: expected rc %d containing %r, got rc %d: %s"
                                % (name, expected_rc, expected_text, proc.returncode,
                                   out.strip()[:300]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise Red("\n".join(failures))
    print("SELFTEST OK — %d control(s), every leg proved able to fail" % len(CONTROLS))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=ROOT,
                        help="tree to grade (default: this repo)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the controls against copies and prove every leg can fail")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.selftest:
        return selftest(root)
    return grade(root)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        sys.exit(2)
    except Red as exc:
        print("RED —")
        for line in str(exc).strip().splitlines():
            print("    " + line.strip())
        sys.exit(1)
