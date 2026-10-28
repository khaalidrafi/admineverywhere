#!/usr/bin/env python3
"""Functional proof of the #+PENDING-REVIEW slot readers — read-only.

scripts/chain_slot_check.py grades the slot laws by TEXT (the guard mentions
the key, the write carries an operand). This probe grades the one property a
text read cannot see: does the EXACT grep command shipped in
.github/workflows/agent-team.yml FIND the EXACT slot line shipped in
agent-team/CONTROL.org, in the interpreter running the check?

Evidence it was written for (Lead 10-am, CONTROL.org:8): run 40103691787's
finalize (27748d9, 15:01Z) blanked a slot that did not belong to it — the
exact failure the NON-CLOBBER guard (ed378d4) exists to refuse. The guard
judges `CURSLOT`, and CURSLOT is produced by `grep -E '^\\#+PENDING-REVIEW:'`.
In ERE a backslash-escaped underscore-less punctuation is undefined; GNU grep
3.11 (Debian trixie — the lane image family) reads `\\#` as an ordinary `#`
and then `#+` as the quantifier "one-or-more hashes", which the line
`#+PENDING-REVIEW: ...` does NOT contain. A guard whose read is always empty
degrades to `[ -z "$CURSLOT" ]` = true: every empty-write finalize may blank
the register. Meanwhile the merger-reread (workflow L793) uses the OTHER form
`^#\\+` (literal plus) — same key, two pattern dialects, opposite results.

Verdicts follow house law: 0 = every shipped reader finds the live line;
1 = RED, a reader that cannot see the register (named, with its line);
2 = CANNOT RUN, the probe cannot parse the workflow or the control file.

  python3 scripts/slot_reader_probe.py            # probe this tree
  python3 scripts/slot_reader_probe.py --root D   # probe another checkout
"""

import re
import subprocess
import sys
import tempfile
import os

WORKFLOW_REL = ".github/workflows/agent-team.yml"
CTL_REL = "agent-team/CONTROL.org"

# The three slot-touching commands, located by their stable variable names,
# never by line number (docs move; the assignments do not).
READERS = (
    ("merger-reread",  "SLOT=",     "grep -E"),
    ("guard-curslot",  "CURSLOT=",  "grep -E"),
    ("guard-sed",      None,        "sed -i"),   # matched by its s%...% write
)


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CannotRun("cannot read %s: %s" % (rel, exc))


def slot_command(text, varname, tool):
    """Return the command line that assigns varname (or the guard's sed write)."""
    for line in text.splitlines():
        s = line.strip()
        if varname and s.startswith(varname) and tool in s and "PENDING-REVIEW" in s:
            return s
        if varname is None and s.startswith("sed -i") and "PENDING-REVIEW" in s:
            return s
    return None


def pattern_of(cmd):
    """Extract the grep -E / sed s%% pattern body from a shipped command."""
    m = re.search(r"grep -E '([^']*)'", cmd)
    if m:
        return ("grep", m.group(1))
    m = re.search(r"s%([^%]*?)%", cmd)
    if m:
        return ("sed-addr", m.group(1))
    raise CannotRun("cannot parse a pattern out of: %s" % cmd[:120])


def run_grep(pattern, text):
    """Run the pattern EXACTLY as bash would have: grep -E, single-quoted."""
    with tempfile.NamedTemporaryFile("w", suffix=".org", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        proc = subprocess.run(["grep", "-E", pattern, path],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout
    finally:
        os.unlink(path)


def grade(root):
    wf = read(root, WORKFLOW_REL)
    ctl = read(root, CTL_REL)
    slot_lines = [l for l in ctl.splitlines() if l.startswith("#+PENDING-REVIEW:")]
    if len(slot_lines) != 1:
        raise CannotRun("%s carries %d `#+PENDING-REVIEW:` column-0 lines; the slot "
                        "law says exactly one" % (CTL_REL, len(slot_lines)))
    slot_line = slot_lines[0]

    problems, notes = [], []
    found = 0
    for name, varname, tool in READERS:
        cmd = slot_command(wf, varname, tool)
        if cmd is None:
            raise CannotRun("%s: no command assigning %s found in %s — the probe no "
                            "longer understands the workflow"
                            % (name, varname or "the slot sed", WORKFLOW_REL))
        kind, pattern = pattern_of(cmd)
        if kind == "sed-addr":
            # The write's address must MATCH the live line, else the park can
            # never move the register. Run it through the SAME GNU sed the
            # workflow uses, in-place on a scratch copy, and see if the line moves.
            with tempfile.NamedTemporaryFile("w", suffix=".org", delete=False) as fh:
                fh.write(ctl)
                path = fh.name
            try:
                body = pattern.replace(".*", "")  # drop the wildcard tail
                subprocess.run(["sed", "-i", "s%%%s%%MARKER%%" % body, path],
                               capture_output=True)
                moved = any("MARKER" in l for l in open(path))
            finally:
                os.unlink(path)
            if moved:
                found += 1
                notes.append("%s: sed write address [%s] MOVES the live slot line"
                             % (name, pattern))
            else:
                notes.append("%s: sed write address [%s] matches NOTHING" % (name, pattern))
                problems.append(
                    "RED %s: the slot WRITE's address cannot match the live line in "
                    "this interpreter, so parks would silently do nothing" % name)
            continue
        rc, out = run_grep(pattern, ctl)
        hit = slot_line in out
        if hit:
            found += 1
            notes.append("%s: grep -E [%s] FINDS the live slot line" % (name, pattern))
        else:
            notes.append("%s: grep -E [%s] finds NOTHING -> guard sees empty slot"
                         % (name, pattern))
            problems.append(
                "RED %s: the command shipped in %s, run in THIS interpreter, cannot "
                "see the line shipped in %s. The NON-CLOBBER guard judges an always-"
                "empty CURSLOT, so `[ -z \"$CURSLOT\" ]` admits every empty write — "
                "the exact shape of the 27748d9 clobber (Lead 10-am: \"wrote 'next "
                "pending: none' and wiped the register EMPTY\"). Repair: use the "
                "literal-plus form already proven in merger-reread (`^#\\+`) or "
                "`grep -F` — one dialect for all slot readers."
                % (name, WORKFLOW_REL, CTL_REL))
    if problems:
        for n in notes:
            print("  " + n)
        print("  readers matching: %d of %d" % (found, len(READERS)))
        raise Red("\n".join(problems))
    print("SLOT READERS OK — %d/%d shipped slot commands match the live register "
          "line in this interpreter" % (found, len(READERS)))
    for n in notes:
        print("  " + n)
    return 0


def main(argv):
    root = "."
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--root":
            i += 1
            root = args[i]
        i += 1
    try:
        return grade(root)
    except CannotRun as exc:
        print("SLOT READERS CANNOT RUN — %s" % exc)
        return 2
    except Red as exc:
        print("SLOT READERS RED:\n%s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
