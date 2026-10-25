#!/usr/bin/env python3
"""chain_patch_check.py — a handover patch must still apply, or say it is dead.

WHY this exists (measured, not assumed). A seat cannot edit the chain's own files
(`.github/workflows/*` and `.github/scripts/*` are Lead-owned, chain law 11), so a
chain defect can only be handed over as a PATCH in docs/ plus the instruction to
run it. docs/ carried two of them and BOTH were dead:

  * `docs/session-loop-fix.patch` — its own NOTE says `git apply --check` has failed
    since eaf34bd extracted the segment step out of the workflow inline, yet the
    header above that NOTE still read "Apply with: git apply docs/...". The
    workflow no longer holds the code the hunks mutate.
  * `docs/pending-slot-fix.patch` — the non-clobber guard it proposes IS in the
    workflow now (the Lead landed it, reworded), so this patch is a stale
    duplicate whose removal-line matches nothing at its recorded offset; it carried
    no STATUS at all, so a reader could not tell it from a live proposal.

Measured on this tree before the repair: `git apply --check` rc 1 on both, while
`python3 scripts/chain_slot_check.py` grades the guard those files describe as
LIVE and green. Nothing in the tree saw the contradiction. A dead instruction is
worse than no instruction: the Lead spends a cycle on a patch that cannot land, or
believes an applied law is still pending (DEVGUIDE *EIGHTH harness law: a gate that
lives as prose is a check nobody can re-run; *ELEVENTH: a comparison cannot see its
own coverage).

So this harness grades the handover, READ-ONLY:

  POPULATION  the patches in docs/ are exactly the pinned roster. A new handover
              nobody counted, or one that silently vanished, is CANNOT RUN.
  CLASSIFY    every patch carries `STATUS: PROPOSAL` or `STATUS: RETIRED`, plus the
              line its status owes: a PROPOSAL must carry an APPLY instruction (a
              proposal the Lead cannot act on is prose), and a RETIRED must carry
              `GRADED BY: <harness>` and must NOT carry an APPLY instruction (a
              dead command a reader would follow).
  TARGET      each hunk's `--- a/<path>` names a file that exists in the tree.
  APPLY       a PROPOSAL must pass `git apply --check`. When it does not, the
              MOVED diagnostic runs: the patch's own removal-line text is searched
              in the other chain carriers, so the verdict names the file the code
              was extracted INTO instead of just "does not apply" — that is the
              sentence that would have saved this repo two review cycles.
  GRADE       a RETIRED patch's named grader exists and EXITS 0. "The law landed"
              is then a measured claim delegated to the harness that owns that
              file, never a line of prose here: the Lead rewords what it lands, so
              re-matching the patch's added text verbatim would fire on correct
              work (the ruling that keeps a false red off a true citation).

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its own input — never a false
red for a tree it has not measured).

Controls prove each leg can fire, against a copy, so the shipped tree is only read:
  python3 scripts/chain_patch_check.py --selftest
and a copy can be graded directly:
  cp -r . /tmp/x && python3 scripts/chain_patch_check.py --root /tmp/x
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

PATCH_GLOB = "docs/*-fix.patch"

# The roster is a SECOND, INDEPENDENT source for the population, the way
# landing_gate.py's EXPECTED_TWINS is cross-checked against the *_diff.py files on
# disk: a literal alone cannot see WHICH harnesses it counts, and a glob alone
# accepts whatever appears. A new handover must be added here in the same commit
# that writes it, or the check refuses rather than grading less than it claims.
HANDOVERS = ("docs/pending-slot-fix.patch",
             "docs/slot-dialect-fix.patch")
EXPECTED_PATCHES = 2

STATUS_RE = re.compile(r"^STATUS:\s*([A-Za-z-]+)", re.M)
PROPOSAL = "PROPOSAL"
RETIRED = "RETIRED"

# An APPLY instruction is what makes a proposal actionable — the two accepted
# spellings, both measured on the shipped headers.
APPLY_RE = re.compile(r"^(APPLY:|Apply with)", re.M)
GRADED_BY_RE = re.compile(r"^GRADED BY:\s*(\S+)", re.M)
TARGET_RE = re.compile(r"^--- a/(.+?)\t.*$", re.M)
TARGET_LOOSE_RE = re.compile(r"^--- a/(.+?)\s*$", re.M)
REMOVAL_RE = re.compile(r"^-([^-+].*)$", re.M)

# Where chain code lives: the MOVED diagnostic searches these for the text a dead
# hunk tried to remove, which is how "the block moved" is named instead of guessed.
CARRIER_DIRS = (".github/scripts", ".github/workflows")

CANNOT = 2
RED = 1


class CannotRun(Exception):
    pass


def read(path):
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def patches_on_disk(root):
    return sorted(os.path.relpath(p, root) for p in
                  glob.glob(os.path.join(root, PATCH_GLOB)))


def leg_population(root):
    """docs/*-fix.patch must be exactly the pinned roster."""
    on_disk = patches_on_disk(root)
    if len(on_disk) != EXPECTED_PATCHES:
        raise CannotRun("%s holds %d patch(es) (%s), the pin says %d — a handover "
                        "added without its roster entry is a patch nobody grades, "
                        "one deleted is a claim of coverage the harness no longer "
                        "has. Fix %s in the SAME commit as the patch."
                        % (PATCH_GLOB, len(on_disk), ", ".join(on_disk) or "none",
                           EXPECTED_PATCHES, os.path.basename(__file__)))
    if tuple(on_disk) != HANDOVERS:
        raise CannotRun("the patches on disk (%s) are not the pinned roster (%s) — "
                        "the harness would grade a set it does not name"
                        % (", ".join(on_disk), ", ".join(HANDOVERS)))
    return ["POPULATION: %d handover patch(es) in docs/, exactly the pinned roster"
            % EXPECTED_PATCHES], []


def classify(text, name):
    """(status, problems, notes) for one patch, from its own header."""
    problems = []
    notes = []
    match = STATUS_RE.search(text)
    if not match:
        raise CannotRun("%s carries no `STATUS: PROPOSAL|RETIRED` line — the harness "
                        "cannot tell a live proposal from a landed law without it, "
                        "and guessing from whether the hunks happen to apply is "
                        "exactly how a dead patch kept looking pending" % name)
    status = match.group(1).upper()
    if status not in (PROPOSAL, RETIRED):
        raise CannotRun("%s declares STATUS: %s, which is neither %s nor %s — the "
                        "two states this harness knows. A third state needs a rule "
                        "written for it, never a green by default."
                        % (name, status, PROPOSAL, RETIRED))
    has_apply = bool(APPLY_RE.search(text))
    grader = GRADED_BY_RE.search(text)
    if status == PROPOSAL:
        if not has_apply:
            problems.append("CLASSIFY: %s is a %s with no APPLY instruction — a "
                            "proposal the Lead cannot act on is prose. Add the "
                            "`APPLY:  git apply <patch>` line the other proposals "
                            "carry." % (name, PROPOSAL))
        notes.append("CLASSIFY: %s -> %s (APPLY instruction %s)"
                     % (name, status, "present" if has_apply else "MISSING"))
    else:
        if not grader:
            problems.append("CLASSIFY: %s is labelled %s but names no `GRADED BY: "
                            "<harness>` — 'the law landed' would be prose here, and "
                            "the queue has already eaten a rejection for exactly "
                            "that shape." % (name, RETIRED))
        if has_apply:
            problems.append("CLASSIFY: %s is labelled %s and still tells the reader "
                            "to apply it — a dead command a reader FOLLOWS is worse "
                            "than no command. Drop the APPLY line, keep the grader."
                            % (name, RETIRED))
        notes.append("CLASSIFY: %s -> %s (%s)"
                     % (name, status,
                        ("graded by " + grader.group(1)) if grader else "no grader"))
    return status, problems, notes


def targets_of(text):
    found = TARGET_RE.findall(text) or TARGET_LOOSE_RE.findall(text)
    out = []
    for path in found:
        clean = path.strip().rstrip("\t")
        if clean and clean != "/dev/null" and clean not in out:
            out.append(clean)
    return out


def leg_target(root, name, text):
    """Every patched path must exist — a patch against a moved or deleted file is
    not a handover, it is a fossil."""
    problems = []
    notes = []
    targets = targets_of(text)
    if not targets:
        raise CannotRun("%s has no parsable `--- a/<path>` header — there is no "
                        "hunk here to grade, so this harness has no opinion about "
                        "it (an empty or truncated patch is a rig failure, not a "
                        "finding)" % name)
    for path in targets:
        if not os.path.isfile(os.path.join(root, path)):
            problems.append("TARGET: %s patches %s, which is not in the tree — the "
                            "file was renamed or deleted, so this patch cannot land "
                            "no matter how correct its fix is." % (name, path))
        else:
            notes.append("TARGET: %s -> %s exists" % (name, path))
    return problems, notes


def carrier_lines(root):
    """(file, stripped line text) for every line of every chain carrier."""
    rows = []
    for directory in CARRIER_DIRS:
        base = os.path.join(root, directory)
        if not os.path.isdir(base):
            continue
        for path in sorted(glob.glob(os.path.join(base, "*"))):
            if not os.path.isfile(path):
                continue
            for number, line in enumerate(read(path).splitlines(), start=1):
                rows.append((os.path.relpath(path, root), number, line.strip()))
    return rows


def moved_hint(root, text, lines):
    """Where did the code this patch removes go? Returns a sentence or None."""
    removals = [m.strip() for m in REMOVAL_RE.findall(text) if m.strip()]
    if not removals:
        return None
    targets = set(targets_of(text))
    wanted = [r for r in removals if len(r) > 24]
    if not wanted:
        return None
    best = None
    for path, number, line in lines:
        if path in targets:
            continue
        for needle in wanted:
            if line == needle:
                return ("the line this patch removes is carried INSTEAD by %s:%d — "
                        "the block moved out of %s, so re-cut the hunks against the "
                        "file the chain actually runs"
                        % (path, number, ", ".join(sorted(targets))))
    return best


def leg_apply(root, name, text, status, lines):
    """A live proposal must pass `git apply --check` — read-only, nothing lands."""
    if status != PROPOSAL:
        return [], ["APPLY: %s is %s, so applicability is out of its domain"
                    % (name, status)]
    git = shutil.which("git")
    if not git:
        raise CannotRun("no `git` on PATH — `git apply --check` is the only way this "
                        "leg measures applicability, and a guess is not a green")
    proc = subprocess.run([git, "apply", "--check", name], cwd=root,
                          capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0:
        return [], ["APPLY: %s passes `git apply --check` against %s"
                    % (name, ", ".join(targets_of(text)) or "its target")]
    tail = out.splitlines()[0] if out.splitlines() else "no output"
    hint = moved_hint(root, text, lines)
    problem = ("APPLY: %s does NOT apply (rc %d: %s). "
               "%sThe header tells the Lead to run `git apply` on it — that "
               "instruction is dead until the hunks are re-cut or the patch is "
               "labelled RETIRED." % (name, proc.returncode, tail,
                                      (hint + " ") if hint else ""))
    return [problem], []


def leg_grade(root, name, text, status):
    """A RETIRED patch's claim is measured through the harness it names."""
    if status != RETIRED:
        return [], []
    grader = GRADED_BY_RE.search(text)
    if not grader:
        return [], []          # already RED from CLASSIFY
    path = grader.group(1)
    if not os.path.isfile(os.path.join(root, path)):
        return ["GRADE: %s is retired on the strength of %s, which is not on disk — "
                "the landed law would be graded by nothing." % (name, path)], []
    if path.endswith(".sh"):
        argv = ["bash", path]
    else:
        argv = [sys.executable, path]
    proc = subprocess.run(argv, cwd=root, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        return ["GRADE: %s claims its law landed and is graded by %s, but that "
                "grader exits %d: %s — either the law regressed or the retirement "
                "was asserted too early."
                % (name, path, proc.returncode,
                   " ".join(out.splitlines()[-1:])[:200])], []
    return [], ["GRADE: %s -> %s exits 0, so the landed law is measured by the "
                "harness that owns it, not re-matched here" % (name, path)]


def check(root):
    notes = []
    problems = []
    pop_notes, pop_problems = leg_population(root)
    notes.extend(pop_notes)
    problems.extend(pop_problems)
    lines = carrier_lines(root)
    statuses = {}
    for name in HANDOVERS:
        text = read(os.path.join(root, name))
        status, classify_problems, classify_notes = classify(text, name)
        statuses[name] = status
        problems.extend(classify_problems)
        notes.extend(classify_notes)
    for name in HANDOVERS:
        text = read(os.path.join(root, name))
        target_problems, target_notes = leg_target(root, name, text)
        problems.extend(target_problems)
        notes.extend(target_notes)
    for name in HANDOVERS:
        text = read(os.path.join(root, name))
        apply_problems, apply_notes = leg_apply(root, name, text, statuses[name],
                                                lines)
        problems.extend(apply_problems)
        notes.extend(apply_notes)
    for name in HANDOVERS:
        text = read(os.path.join(root, name))
        grade_problems, grade_notes = leg_grade(root, name, text, statuses[name])
        problems.extend(grade_problems)
        notes.extend(grade_notes)
    return notes, problems


# ---------------------------------------------------------------------------
# Controls. Each mutates a COPY of the tree, so the shipped handovers are never
# touched, and each names the leg it is the counterfactual for.

def _patch_path(root, name):
    return os.path.join(root, name)


def _write(root, rel, text):
    with open(os.path.join(root, rel), "w") as handle:
        handle.write(text)


def control_no_change(root):
    pass


def control_target_deleted(root):
    """TARGET: the patched file is gone."""
    for name in HANDOVERS:
        text = read(_patch_path(root, name))
        for path in targets_of(text):
            if os.path.isfile(os.path.join(root, path)):
                os.remove(os.path.join(root, path))
                return


def control_context_moved(root):
    """APPLY: the carrier reworded the line the hunk anchors on."""
    name = "docs/slot-dialect-fix.patch"
    text = read(_patch_path(root, name))
    for path in targets_of(text):
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            continue
        lines = read(full).splitlines()
        for number, line in enumerate(lines):
            if "CURSLOT=\"$(grep -E" in line:
                lines[number] = line.replace("^\\#+", "^#\\+")
                _write(root, path, "\n".join(lines) + "\n")
                return
    raise AssertionError("no guard read line to reword")


def control_extracted(root):
    """APPLY + MOVED: the patched block was lifted into another carrier."""
    name = "docs/slot-dialect-fix.patch"
    text = read(_patch_path(root, name))
    removals = [m for m in REMOVAL_RE.findall(text) if "CURSLOT" in m]
    if not removals:
        raise AssertionError("the proposal hunks carry no guard-read removal line")
    needle = removals[0].strip()
    for path in targets_of(text):
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            continue
        body = read(full).splitlines(keepends=False)
        moved = [l for l in body if l.strip() == needle]
        body = [l for l in body if l.strip() != needle]
        _write(root, path, "\n".join(body) + "\n")
        _write(root, ".github/scripts/segment_extracted.sh",
               "#!/usr/bin/env bash\n" + "\n".join(moved) + "\n")
        return
    raise AssertionError("patch target missing from the copy")


def control_no_apply_line(root):
    """CLASSIFY: a proposal that lost its instruction."""
    name = "docs/slot-dialect-fix.patch"
    text = read(_patch_path(root, name))
    _write(root, name, re.sub(r"^APPLY:.*$", "", text, count=1, flags=re.M))


def control_bad_status(root):
    """CLASSIFY: a status nobody wrote a rule for."""
    name = "docs/slot-dialect-fix.patch"
    text = read(_patch_path(root, name))
    _write(root, name, text.replace("STATUS: PROPOSAL", "STATUS: WAITING", 1))


def control_extra_patch(root):
    """POPULATION: a handover appeared that the roster does not name."""
    # Its needle is count-FREE by design: a needle carrying a literal patch count
    # would fire on the shipped tree the day the roster grows, grading the pin
    # instead of the leg.
    text = read(_patch_path(root, "docs/slot-dialect-fix.patch"))
    _write(root, "docs/third-handover-fix.patch", text)


def control_retired_no_grader(root):
    """CLASSIFY: retired, but the landed law rests on prose."""
    name = "docs/pending-slot-fix.patch"
    text = read(_patch_path(root, name))
    _write(root, name, re.sub(r"^GRADED BY:.*$", "", text, count=1, flags=re.M))


def control_grader_missing(root):
    """GRADE: the retired patch points at a harness that is not on disk."""
    name = "docs/pending-slot-fix.patch"
    text = read(_patch_path(root, name))
    _write(root, name, text.replace("scripts/chain_slot_check.py",
                                    "scripts/chain_slot_check_gone.py", 1))


def control_retired_apply_line(root):
    """CLASSIFY: retired AND still ordering the reader to apply it."""
    name = "docs/pending-slot-fix.patch"
    text = read(_patch_path(root, name))
    _write(root, name, "APPLY:  git apply docs/pending-slot-fix.patch\n" + text)


def control_grader_red(root):
    """GRADE: the named grader exists and answers red."""
    name = "docs/pending-slot-fix.patch"
    text = read(_patch_path(root, name))
    _write(root, "scripts/stub_grader.sh", "#!/usr/bin/env bash\necho STUB RED\nexit 1\n")
    _write(root, name, text.replace("scripts/chain_slot_check.py",
                                    "scripts/stub_grader.sh", 1))


def control_no_hunks(root):
    """TARGET: a patch with nothing parsable in it grades no claim."""
    name = "docs/slot-dialect-fix.patch"
    text = read(_patch_path(root, name))
    head = text.split("diff --git", 1)[0]
    _write(root, name, head + "(content unavailable in this copy)\n")


CONTROLS = (
    ("shipped tree is green", control_no_change, 0, "PATCH HANDOVER OK"),
    ("patched file is gone", control_target_deleted, 1, "TARGET"),
    ("carrier reworded the anchor", control_context_moved, 1, "does NOT apply"),
    ("block extracted to another carrier", control_extracted, 1, "the block moved"),
    ("proposal lost its APPLY line", control_no_apply_line, 1, "no APPLY instruction"),
    ("STATUS value unknown", control_bad_status, 2, "neither PROPOSAL nor RETIRED"),
    ("an extra handover, uncounted", control_extra_patch, 2, "without its roster entry"),
    ("retired names no grader", control_retired_no_grader, 1, "names no `GRADED BY"),
    ("retired grader is missing", control_grader_missing, 1, "not on disk"),
    ("retired still says APPLY", control_retired_apply_line, 1, "still tells the reader"),
    ("retired grader answers red", control_grader_red, 1, "exits 1"),
    ("patch has no parsable hunk", control_no_hunks, 2, "no parsable"),
)

# PINNED, not derived (chain_test_check's EXPECTED_CONTROLS law): a roster whose
# length is only printed cannot see its own coverage, so deleting a control would
# shrink the claim instead of refusing.
EXPECTED_CONTROLS = 12


def selftest(root):
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d entries, the pin says %d — a "
                        "control vanished (or arrived without the pin), so "
                        "`SELFTEST OK` would no longer mean every leg was run"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = os.path.join(root, "scripts", "chain_patch_check.py")
    failures = []
    for name, mutation, expected_rc, expected_text in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="chain-patch-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", ".git",
                                                          "__pycache__",
                                                          ".pytest_cache",
                                                          "dist", "build",
                                                          ".sessions-restore"))
            mutation(target)
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-36s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
            else:
                failures.append("%s: expected rc %d containing %r, got rc %d: %s"
                                % (name, expected_rc, expected_text,
                                   proc.returncode, out.strip()[:240]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise CannotRun("SELFTEST RED — %d control(s) did not fire as expected: %s"
                        % (len(failures), "; ".join(failures)))
    print("SELFTEST OK — %d control(s), every leg proved able to fail" % len(CONTROLS))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(
        description="Grade the chain's handover patches: applicable, classified, "
                    "or honestly retired.")
    parser.add_argument("--root", default=".",
                        help="the tree to grade (default: this repo)")
    parser.add_argument("--selftest", action="store_true",
                        help="prove every leg can fail, against copies")
    opts = parser.parse_args(argv)
    root = os.path.abspath(opts.root)
    if opts.selftest:
        try:
            return selftest(root)
        except CannotRun as exc:
            print("CANNOT RUN — %s" % exc)
            return CANNOT
    try:
        notes, problems = check(root)
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        return CANNOT
    for note in notes:
        print("  %s" % note)
    if problems:
        print("PATCH HANDOVER RED — %d problem(s)" % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        return RED
    print("PATCH HANDOVER OK — %d handover patch(es): the live proposal applies to "
          "the carrier the chain runs, and every retired law is graded by a harness "
          "that exits 0" % EXPECTED_PATCHES)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
