#!/usr/bin/env python3
"""Re-runnable check of the SEGREGATION-LAW pending slot (Owner order 2026-10-22 18:14Z).

WHY this exists (measured, not assumed). Under the segregation law the whole
delivery loop hangs on ONE line of agent-team/TEAM-CONTROL.org, `#+PENDING-REVIEW`:
the turn seat authors a branch, the merger parks it in that slot, the next run's
duty reviewer reads the slot and the gate lands it on an APPROVED verdict behind
a green landing gate. Four separate times today that single slot was the reason
work could not land, and every one of them was found by a seat reading the
workflow by hand:

  1. [18:41Z, platform seat] the slot could not BOOTSTRAP from empty - the park
     write required OUTCOME=approved, and approved required a pending branch to
     already exist. Empty -> empty forever. Fixed by the Lead: the park now keys
     on whether the OLD pending is being RETAINED.
  2. [20:10Z, relief seat] the merger read the author id in the wrong ID SPACE -
     PENDING_AUTHOR is a SEAT KEY, the comparison used member ids, so QA reviewed
     its own branch and the same-member refusal auto-REJECTED it twice.
     Fixed by the Lead (55cf5a9).
  3. [20:45Z, Lead] a timed-out segment step handed the merger EMPTY turn
     outputs and it believed "no-pending", wiping the queued branch; the merger
     now RE-READS the slot from the control file before believing a failed parse.
  4. [20:47Z, measured live on the ref] the durability fix is incomplete: the
     Lead re-queued ai/turn-20261022-1904 in 0ace32e at 20:47:17Z and the very
     next ci-review commit 86d88ce blanked the slot 20 seconds later. Cause: the
     `SEGREGATION bookkeeping` step's retry loop does `git reset --hard
     origin/ai/main` - which re-imports a control file carrying the Lead's NEWER
     slot - and then writes the NEWPENDING it computed BEFORE the reset,
     unconditionally. A race-proof WRITE is only race-proof for the lines it
     re-reads.

Findings 1-3 are fixed; #4 was hardened by the Lead in place (ed378d4 non-clobber
slot guard), which differs from the delivered proposal patch (docs/pending-slot-fix.patch
no longer `git apply`-clean against the shipped shape) and, while re-indenting the sed
into the new guard, DROPPED the trailing `"$CTL"` file operand. The writer was then
`sed -i "s%...%...% "` with no file: GNU sed 4.9 errors "no input files" (rc 4) and
edits NOTHING, the step runs without `set -e`, and the commit message still prints
"next pending: ${NEWPENDING}" — so every slot law below was silently unenforced. The
Lead landed the one-token repair, so the shipped tree is GREEN on blank-guard; what a
seat keeps is the COMMAND that grades all four laws read-only, plus the control that
takes the operand back out and proves the leg can still fail.

This harness grades the shipped workflow READ-ONLY. Four legs, one per claim
above that the machinery is supposed to honor:

  merger-reread   an EMPTY turn parse never overwrites a slot it has not read:
                  the merge step re-reads #+PENDING-REVIEW from the control file.
  park-bootstrap  an author branch can enter an empty slot: the park gate keys on
                  the retain-outcomes, never on approved + gate-green.
  verdict-retain  a REJECTED pending keeps its own branch queued for re-review
                  (agent-team/REVIEW-LOG.org review law 4), not just refused or
                  review-missing.
  blank-guard     the control write inside the race-proof loop re-reads the slot
                  AFTER its own `git reset --hard`, refuses to blank a slot it did
                  not read/resolve/park, and ACTUALLY WRITES — the write must carry
                  a file operand, or "no clobber" becomes "never write at all".
                  The Lead landed that operand, so the shipped tree is GREEN here
                  and `sed operand stripped is red` is what proves the leg can fail.

Before those legs run, the merger's VERDICT ROSTER is closed: every literal
`OUTCOME="<x>"` in the workflow must be known — one of the four park-excluded
retain outcomes, `rejected` (retained by its own clause), or one of the three
resolved outcomes that legitimately park this run's branch. An outcome the
machinery can write and no leg knows is CANNOT RUN naming it, because a green
over an unknown verdict would be a green over a roster the harness no longer
describes. This is how `lane-dead` (Lead cycle 10-l) got away ungraded once: the
park gate gained a fourth exclusion while this file still pinned three, so the
leg printed "all 3 retain outcome(s)" and the control anchored to the old gate
line died, taking seven of the nine controls down with it (rc 2, `--selftest`).

Verdicts follow the house convention (docs/DEVGUIDE.md *EIGHTH* + *ELEVENTH*
harness laws): 0 = OK, 1 = RED (a claim is false), 2 = CANNOT RUN (the harness no
longer understands its own input - never a false red for a tree it has not
measured). The leg roster is pinned, so a leg that vanishes is a refusal, not a
quieter green.

  python3 scripts/chain_slot_check.py                  # grade this tree (0/1/2 verdicts)
  python3 scripts/chain_slot_check.py --root /tmp/copy # grade another tree
  python3 scripts/chain_slot_check.py --live           # also list dropped author branches
  python3 scripts/chain_slot_check.py --selftest       # 11 controls, every leg able to fail

Deliberately NOT named `*_diff.py`: that glob IS the landing gate's twin roster
(`scripts/landing_gate.py` EXPECTED_TWINS cross-checks every `scripts/*_diff.py`
on disk against the harnesses its --fe legs actually run), and this grades the
CHAIN, not a pair of cross-language artifacts - same ruling as
scripts/chain_test_check.py and scripts/chain_session_check.py.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ------------------------------------------------------------ pinned inputs
# The PROMISE, not the disk. A harness that derives its expectations from the
# tree it grades proves nothing.
WORKFLOW_REL = ".github/workflows/agent-team.yml"
CTL_REL = "agent-team/TEAM-CONTROL.org"

MERGE_STEP = "Merger — resolve the pending branch"
SEGREGATE_STEP = "SEGREGATION bookkeeping"

SLOT_KEY = "#+PENDING-REVIEW:"

# The outcomes that must RETAIN the pending branch instead of parking a new one:
# a branch the duty reviewer could not clear stays queued (REVIEW-LOG law 4).
# `lane-dead` joined this list with the Lead's cycle 10-l hardening: the merger
# calls a substituted review lane (no parseable VERDICT token) lane-dead rather
# than review-missing, and the branch must stay pending for a real re-review.
RETAIN_OUTCOMES = ("review-missing", "lane-dead", "refused-same-member",
                   "refused-wrong-reviewer")

# A REJECTED verdict retains through a SEPARATE clause (the park gate does not
# exclude it; the `if [ "$OUTCOME" = "rejected" ]` block re-writes the old
# pending) — that is the clause leg_verdict_retain grades.
REJECTED_RETAIN = "rejected"

# The outcomes that legitimately let THIS run's author branch park: the slot was
# empty, the segment produced nothing to read, or the pending was approved and
# merged. None of them may keep the old branch queued.
RESOLVED_OUTCOMES = ("no-pending", "empty-segment", "approved")

# Every verdict the merger can write, pinned as a CLOSED set. An outcome the
# workflow can produce but this harness has never heard of is CANNOT RUN, not a
# quiet green: `lane-dead` arrived exactly that way — the park gate gained a
# fourth exclusion while this file still pinned three, so the leg kept printing
# "all 3 retain outcome(s) are excluded" over a roster it no longer described,
# and the control anchored to the old gate line died (`--selftest` rc 2, 7 of 9
# controls never ran). A seat cannot watch a Lead-owned file for new literals;
# it can refuse to grade a file containing one it does not know.
OUTCOME_LITERALS = RETAIN_OUTCOMES + (REJECTED_RETAIN,) + RESOLVED_OUTCOMES
EXPECTED_OUTCOMES = 8

# The four claims above, pinned in order. A leg that disappears from the runner
# is CANNOT RUN - a vanished leg prints no red to argue with.
LEG_ROSTER = ("merger-reread", "park-bootstrap", "verdict-retain", "blank-guard")
EXPECTED_LEGS = 4

# The slot is single-writer BY DESIGN (the park law's own comment says "single
# slot by design"). Two writers of one line is a race built into the machinery.
EXPECTED_SED_SITES = 1

STEP_RE = re.compile(r"^      - name: (.*)$")
RUN_RE = re.compile(r"^\s*run:\s*\|\s*$")
LOOP_RE = re.compile(r"^\s*for i in 1 2 3; do\s*$")
DONE_RE = re.compile(r"^\s*done\s*$")
ASSIGN_VAR_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)="\$\(grep .*PENDING-REVIEW')
# The slot write. The hardened writer (Lead ed378d4) re-indented the sed into a
# non-clobber guard and, in doing so, DROPPED the trailing "$CTL" file operand, so
# the matcher may no longer require it on the line — otherwise the slot's only
# writer is invisible and every leg refuses. A `sed -i` with no operand is a defect
# in its own right (blank-guard names it), so recognition and grading are split:
# this regex FINDS the write, CTL_OPERAND_RE checks that it TARGETS the control file.
SED_WRITE_RE = re.compile(r'^\s*sed -i .*PENDING-REVIEW')
CTL_OPERAND_RE = re.compile(r'"\$CTL"')
# A verdict the merger writes by hand (`OUTCOME="lane-dead"`), not one it forwards
# from a step output (`OUTCOME="${{ ... }}"`), which the character class refuses.
OUTCOME_ASSIGN_RE = re.compile(r'^\s*OUTCOME="([a-z][a-z-]*)"\s*$')


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


def indent_of(line):
    return len(line) - len(line.lstrip())


# ------------------------------------------------------------------ parsing
def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CannotRun("cannot read %s: %s" % (rel, exc))


def step_bodies(workflow_text):
    """Every CI step body, keyed by its `- name:` title, dedented.

    A step's script lives in a YAML block scalar (`run: |`), so the body keeps
    its relative indentation for bash and loses the YAML wrapper for us - the
    legs below compare INDENT levels to decide what is inside what, exactly the
    way the shell reads it.
    """
    lines = workflow_text.splitlines()
    marks = []
    for index, line in enumerate(lines):
        match = STEP_RE.match(line)
        if match:
            marks.append((index, match.group(1).strip()))
    bodies = {}
    for position, (start, title) in enumerate(marks):
        stop = marks[position + 1][0] if position + 1 < len(marks) else len(lines)
        body = []
        inside = False
        for line in lines[start:stop]:
            if not inside and RUN_RE.match(line):
                inside = True
                continue
            if inside:
                body.append(line)
        if not inside:
            continue
        width = min((indent_of(line) for line in body if line.strip()), default=0)
        bodies[title] = [line[width:] if line.strip() else line for line in body]
    return bodies


def find_step(bodies, needle):
    for title, body in bodies.items():
        if needle in title:
            return body
    raise CannotRun("%s carries no step named %r - the merger is not where this "
                    "harness believes it is, so it cannot grade the slot"
                    % (WORKFLOW_REL, needle))


def enclosing_if(lines, index, span=14):
    """The nearest `if` at or above `index`, walking out of deeper indentation."""
    depth = indent_of(lines[index])
    for back in range(index - 1, max(-1, index - span), -1):
        line = lines[back]
        if not line.strip():
            continue
        if indent_of(line) <= depth and line.strip().startswith("if "):
            return back, line
        if indent_of(line) < depth and lines[back].strip().endswith("; then"):
            return back, line
    return None, None


# ------------------------------------------------------------------------ legs
# Every leg returns (notes, problems) and never raises on its own finding: one
# run has to report which slot laws hold and which do not, not stop at the first.
def leg_merger_reread(merge_body):
    """An EMPTY turn parse must never overwrite a slot the merger has not read."""
    read_at = None
    for index, line in enumerate(merge_body):
        if "PENDING-REVIEW" in line and CTL_REL in line and line.strip().startswith("SLOT="):
            read_at = index
            break
    if read_at is None:
        return [], ["merger-reread: %s never re-reads %s from %s - when the segment step "
                    "dies or times out the turn outputs are EMPTY, the merger believes "
                    "\"no-pending\" and the control write drops the queued branch "
                    "unreviewed (measured on run 39846623548 at 20:35:52Z)"
                    % (WORKFLOW_REL, SLOT_KEY, CTL_REL)]
    guard_at, guard = enclosing_if(merge_body, read_at)
    if guard_at is None or "PENDING_BRANCH" not in guard:
        return [], ["merger-reread: the slot re-read at step-body line %d is not guarded "
                    "by the empty-output case (`if [ -z \"$PENDING_BRANCH\" ]`), so it is "
                    "not the durability leg this harness grades" % (read_at + 1)]
    return ["merger-reread: the merger re-reads the slot from %s when the turn parse is "
            "empty (guarded at step-body line %d)" % (CTL_REL, guard_at + 1)], []


def leg_park_bootstrap(seg_body):
    """An author branch must be able to enter an EMPTY slot: no approved+green gate."""
    park_at = None
    for index, line in enumerate(seg_body):
        if line.strip().startswith("NEWPENDING=") and "${AUTHOR_BRANCH}" in line:
            park_at = index
            break
    if park_at is None:
        raise CannotRun("park-bootstrap: %s has no write of this run's author branch into "
                        "the slot - the park law is gone and this harness can no longer "
                        "grade it" % SEGREGATE_STEP)
    gate_at, gate = enclosing_if(seg_body, park_at)
    if gate_at is None:
        raise CannotRun("park-bootstrap: the slot write at step-body line %d has no "
                        "enclosing condition - the harness cannot tell what gates it"
                        % (park_at + 1))
    problems = []
    for forbidden in ('= "approved"', '= "green"'):
        if forbidden in gate:
            problems.append("park-bootstrap: the park gate (step-body line %d) still "
                            "requires %s - approved needs a pending branch to have "
                            "existed, so an EMPTY slot could never bootstrap and no author "
                            "branch could ever land (the 18:41Z deadlock; the gate must "
                            "key on the RETAIN outcomes instead)"
                            % (gate_at + 1, forbidden))
    for outcome in RETAIN_OUTCOMES:
        if outcome not in gate:
            problems.append("park-bootstrap: the park gate (step-body line %d) does not "
                            "exclude `%s` - a branch the duty reviewer could not clear "
                            "would be replaced by this run's branch and never re-reviewed"
                            % (gate_at + 1, outcome))
    if problems:
        return [], problems
    return ["park-bootstrap: the author branch parks on `AHEAD > 0` and all %d retain "
            "outcome(s) are excluded (step-body line %d)"
            % (len(RETAIN_OUTCOMES), gate_at + 1)], []


def leg_verdict_retain(seg_body):
    """A REJECTED pending keeps its own branch queued - REVIEW-LOG.org review law 4."""
    clauses = [line for line in seg_body
               if line.strip().startswith("if [") and '"$OUTCOME"' in line
               and "=" in line and "!=" not in line]
    if not clauses:
        raise CannotRun("verdict-retain: %s has no retain clause keyed on $OUTCOME - the "
                        "law this leg grades is no longer expressed in the merger"
                        % SEGREGATE_STEP)
    joined = " ".join(clauses)
    problems = []
    for outcome in RETAIN_OUTCOMES + (REJECTED_RETAIN,):
        if outcome not in joined:
            problems.append("verdict-retain: the retain clause never mentions `%s` - a "
                            "branch carrying that verdict drops out of the slot and can "
                            "never be re-reviewed, which is exactly what review law 4 of "
                            "agent-team/REVIEW-LOG.org promises it must not do (\"Rejected "
                            "/ refused / review-missing: the pending slot keeps the branch "
                            "for re-review\")" % outcome)
    if problems:
        return [], problems
    return ["verdict-retain: %d $OUTCOME clause(s); %s all keep the same branch queued"
            % (len(clauses), ", ".join("`%s`" % o
                                       for o in RETAIN_OUTCOMES + (REJECTED_RETAIN,)))], []


def leg_blank_guard(seg_body):
    """The control write may not blank a slot that changed under this run."""
    start = None
    for index, line in enumerate(seg_body):
        if LOOP_RE.match(line):
            start = index
    if start is None:
        raise CannotRun("blank-guard: %s has no race-proof retry loop (`for i in 1 2 3; "
                        "do`) - the write this leg grades is no longer there"
                        % SEGREGATE_STEP)
    stop = None
    for index in range(start + 1, len(seg_body)):
        if DONE_RE.match(seg_body[index]):
            stop = index
            break
    if stop is None:
        raise CannotRun("blank-guard: the retry loop opened at step-body line %d is never "
                        "closed - the harness cannot read its extent" % (start + 1))
    loop = seg_body[start:stop]

    sites = [index for index, line in enumerate(loop) if SED_WRITE_RE.match(line)]
    if not sites:
        raise CannotRun("blank-guard: the loop writes no %s line at all - either the slot "
                        "is gone or it moved out of the retry loop, and this harness "
                        "refuses to guess which" % SLOT_KEY)
    if len(sites) > 1:
        return [], ["blank-guard: %d writes of %s inside one loop - the slot is "
                    "single-writer by design (\"single slot by design\"), two writers of "
                    "one line is a race built into the machinery" % (len(sites), SLOT_KEY)]
    write_at = sites[0]
    reset_at = None
    for index, line in enumerate(loop):
        if "git reset --hard origin/ai/main" in line:
            reset_at = index
    if reset_at is None:
        raise CannotRun("blank-guard: the loop no longer resets to the moved ref, so its "
                        "write-vs-read ordering cannot be graded here - the race-proof "
                        "shape this leg depends on is gone")
    if reset_at >= write_at:
        return ["blank-guard: the loop writes %s BEFORE it resets, so no stale value can "
                "survive the reset" % SLOT_KEY], []

    reread_at = None
    reread_var = None
    for index, line in enumerate(loop[:write_at]):
        match = ASSIGN_VAR_RE.match(line)
        if match and "$CTL" in line:
            reread_at, reread_var = index, match.group(1)
            break
    if reread_at is None:
        return [], ["blank-guard: the loop never re-reads the slot AFTER its own "
                    "`git reset --hard origin/ai/main` (reset at loop line %d, write at "
                    "loop line %d) - the value it writes was computed BEFORE the reset, so "
                    "a Lead slot write that lands during this run is destroyed by this "
                    "run. Measured live: the Lead re-queued ai/turn-20261022-1904 in "
                    "0ace32e at 20:47:17Z and ci-review 86d88ce blanked it 20 seconds later"
                    % (reset_at + 1, write_at + 1)]

    guards = [index for index in range(reread_at + 1, write_at)
              if loop[index].strip().startswith("if [") and "$NEWPENDING" in loop[index]
              and "$" + reread_var in loop[index]]
    if not guards:
        return [], ["blank-guard: the slot is re-read into $%s (loop line %d) but nothing "
                    "between that read and the write (loop line %d) judges the write "
                    "against it - an EMPTY write still blanks a slot this run did not "
                    "resolve" % (reread_var, reread_at + 1, write_at + 1)]
    guard_at = guards[-1]
    if indent_of(loop[write_at]) <= indent_of(loop[guard_at]):
        return [], ["blank-guard: the write at loop line %d is not INSIDE the guard at "
                    "loop line %d (indent %d vs %d) - the comparison runs and is thrown "
                    "away" % (write_at + 1, guard_at + 1, indent_of(loop[write_at]),
                              indent_of(loop[guard_at]))]
    if not CTL_OPERAND_RE.search(loop[write_at]):
        return [], ["blank-guard: the slot write at loop line %d runs `sed -i` with NO file "
                    "operand - GNU sed errors \"no input files\" (rc 4, measured on sed 4.9) "
                    "and edits NOTHING, and this step runs without `set -e`, so the "
                    "non-clobber guard computes the park/retain/clear decision and prints it "
                    "in the commit message (\"next pending: ${NEWPENDING}\") but never writes "
                    "it to %s. Every slot law this harness grades is silently unenforced: an "
                    "author branch never parks, a rejected pending never retains, and a "
                    "resolved branch is never cleared. Fix (Lead-owned): add `\"$CTL\"` as "
                    "the sed operand - the pre-hardening writer carried it and ed378d4 "
                    "dropped it while re-indenting the guard into the write."
                    % (write_at + 1, CTL_REL)]
    return ["blank-guard: the loop re-reads $%s after its reset (loop line %d), the write "
            "at loop line %d is guarded by the comparison at loop line %d and carries its "
            "%s operand" % (reread_var, reread_at + 1, write_at + 1, guard_at + 1, CTL_REL)], []


# -------------------------------------------------------------------- grading
def outcome_closure(bodies):
    """Every verdict the merger can write must be a verdict this harness knows.

    Reads the literal `OUTCOME="<x>"` assignments across every CI step body (the
    merger writes them, the bookkeeping step reads $OUTCOME) and refuses on a
    set difference in EITHER direction. This is not a fifth leg: a graded claim
    needs a law to grade, and a new outcome has none until a seat writes one —
    so an unknown outcome is CANNOT RUN (the harness no longer understands its
    input), never a green that silently excludes it.
    """
    found = set()
    for body in bodies.values():
        for line in body:
            match = OUTCOME_ASSIGN_RE.match(line)
            if match:
                found.add(match.group(1))
    if not found:
        raise CannotRun("no `OUTCOME=\"<verdict>\"` literal appears in any step body - "
                        "the merger's verdicts are no longer written in the workflow, so "
                        "the retain/park law this harness grades has nothing to read")
    unknown = sorted(found - set(OUTCOME_LITERALS))
    if unknown:
        raise CannotRun("the merger writes outcome(s) %s that this harness has never heard "
                        "of - no leg knows whether one of them must keep a pending branch "
                        "queued, so a green run here would be grading a roster it does not "
                        "describe. Name it in RETAIN_OUTCOMES / REJECTED_RETAIN / "
                        "RESOLVED_OUTCOMES and pin EXPECTED_OUTCOMES in the SAME commit"
                        % ", ".join('"%s"' % u for u in unknown))
    gone = sorted(set(OUTCOME_LITERALS) - found)
    if gone:
        raise CannotRun("this harness pins outcome(s) %s but the workflow no longer writes "
                        "any of them - a verdict was renamed or removed and the leg that "
                        "graded it is now reading a line that does not exist"
                        % ", ".join('"%s"' % g for g in gone))
    if len(found) != EXPECTED_OUTCOMES:
        raise CannotRun("the merger writes %d distinct outcome(s), this harness pins %d - "
                        "the population this closure claims is no longer the population it "
                        "compares" % (len(found), EXPECTED_OUTCOMES))
    return ["outcomes   %d literal(s), all known (%d park-excluded + `%s` retained by "
            "clause + %d resolved)"
            % (len(found), len(RETAIN_OUTCOMES), REJECTED_RETAIN, len(RESOLVED_OUTCOMES))]


def slot_line(root):
    try:
        for line in read(root, CTL_REL).splitlines():
            if line.startswith(SLOT_KEY):
                return line[len(SLOT_KEY):].strip()
    except CannotRun:
        return "(control file unread)"
    return "(no slot line)"


def grade(root):
    if len(LEG_ROSTER) != EXPECTED_LEGS:
        raise CannotRun("the leg roster holds %d leg(s) but this harness pins %d - it no "
                        "longer knows what it grades" % (len(LEG_ROSTER), EXPECTED_LEGS))
    workflow_text = read(root, WORKFLOW_REL)
    bodies = step_bodies(workflow_text)
    merge_body = find_step(bodies, MERGE_STEP)
    seg_body = find_step(bodies, SEGREGATE_STEP)

    sed_sites = [line for line in workflow_text.splitlines() if SED_WRITE_RE.match(line)]
    if len(sed_sites) != EXPECTED_SED_SITES:
        raise CannotRun("%s writes %s in %d place(s) that look like the merger's - this "
                        "harness reads the slot's writer where it believes it lives (the "
                        "park law says single slot by design)"
                        % (WORKFLOW_REL, SLOT_KEY, len(sed_sites)))

    notes = []
    problems = []
    fired = set()
    notes += outcome_closure(bodies)
    for leg, body in ((leg_merger_reread, merge_body), (leg_park_bootstrap, seg_body),
                      (leg_verdict_retain, seg_body), (leg_blank_guard, seg_body)):
        found, missing = leg(body)
        notes += found
        problems += missing
        for problem in missing:
            fired.add(problem.split(":")[0])

    slot = slot_line(root)
    notes.append("LIVE: %s on this tree is %s" % (SLOT_KEY, slot or "(empty)"))
    notes.append("LEGS: %d of %d green, red: %s"
                 % (len(LEG_ROSTER) - len(fired), len(LEG_ROSTER),
                    ", ".join(sorted(fired)) or "none"))

    if problems:
        for note in notes:
            print("  " + note)
        raise Red("\n".join(problems))

    print("SLOT CHECK OK — %d/%d leg(s) green: the pending slot bootstraps, retains, "
          "re-reads and never blanks" % (len(LEG_ROSTER), EXPECTED_LEGS))
    for note in notes:
        print("  " + note)
    return 0


# ---------------------------------------------------------------------- live
def live_note(root):
    """Which authored branches are OUTSIDE the slot right now (informational only).

    Never changes the verdict: a branch that is not parked is not automatically a
    defect (the Lead audit-merges overflow under the single-slot law), but a
    reader cannot audit what they cannot list.
    """
    out = []
    try:
        probe = subprocess.run(("git", "ls-remote", "--heads", "origin"), cwd=root,
                               capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return ["LIVE-DROP: not measured (git ls-remote failed: %s)" % exc]
    if probe.returncode != 0:
        return ["LIVE-DROP: not measured (%s)" % probe.stderr.strip()[:120]]
    heads = {}
    for line in probe.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            heads[parts[1]] = parts[0]
    main = heads.get("refs/heads/ai/main")
    if not main:
        return ["LIVE-DROP: not measured (no ai/main on the remote)"]
    parked = set()
    try:
        parked = set(re.findall(r"branch=(\S+)", read(root, CTL_REL)))
    except CannotRun:
        pass
    dropped = []
    for ref, sha in sorted(heads.items()):
        name = ref.replace("refs/heads/", "")
        if not name.startswith("ai/turn-") or sha == main:
            continue
        count = subprocess.run(("git", "rev-list", "--count", "%s..%s" % (main, sha)),
                               cwd=root, capture_output=True, text=True)
        if count.returncode == 0 and int(count.stdout.strip() or 0) > 0:
            if name not in parked:
                dropped.append("%s (%s commit(s))" % (name, count.stdout.strip()))
    if dropped:
        out.append("LIVE-DROP: %d author branch(es) carry commits ai/main does not and "
                   "are not in the slot — %s" % (len(dropped), ", ".join(dropped)))
    else:
        out.append("LIVE-DROP: no author branch is outside the slot with unmerged work")
    return out


# ------------------------------------------------------------------ selftest
# A check that cannot FAIL is not a check (DEVGUIDE *EIGHTH harness law*, applied
# to the harness itself). The Lead hardened the writer in place (ed378d4) with a
# guard that differs from the delivered proposal patch (docs/pending-slot-fix.patch
# no longer `git apply`-clean), and in re-indenting the sed dropped its `"$CTL"`
# operand — the shipped tree was RED on blank-guard until the Lead landed that
# operand. The green baseline is therefore BUILT on a COPY (restore the operand if
# the tree has lost it, accept the tree as-is if it has not), never by applying the
# stale patch, and the shipped tree is never written to. No Lead-owned file is
# ever touched.


def _read_file(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def _write_file(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def _replace_once(root, rel, old, new):
    text = _read_file(root, rel)
    if old not in text:
        raise CannotRun("control: the text to mutate is not in %s" % rel)
    _write_file(root, rel, text.replace(old, new, 1))


def _park_gate(root):
    """The park gate's own text, located the way leg_park_bootstrap locates it.

    Returns the line WITHOUT its indentation (the step bodies are dedented by
    YAML depth, so the harness reads them that way); `_replace_line` puts the
    indentation back.
    """
    text = _read_file(root, WORKFLOW_REL)
    body = find_step(step_bodies(text), SEGREGATE_STEP)
    write_at = None
    for index, line in enumerate(body):
        if line.strip().startswith("NEWPENDING=") and "${AUTHOR_BRANCH}" in line:
            write_at = index
            break
    if write_at is None:
        raise CannotRun("control: %s has no park of this run's author branch, so there "
                        "is no gate to mutate" % SEGREGATE_STEP)
    gate_at, gate = enclosing_if(body, write_at)
    if gate_at is None:
        raise CannotRun("control: the park write at step-body line %d has no enclosing "
                        "condition - the control cannot tell which line to rewrite"
                        % (write_at + 1))
    return gate.strip()


def _replace_line(root, rel, stripped_line, new_stripped_line):
    """Rewrite ONE whole line, matched on its dedented text."""
    lines = _read_file(root, rel).split("\n")
    hits = [index for index, line in enumerate(lines) if line.strip() == stripped_line]
    if len(hits) != 1:
        raise CannotRun("control: %s carries %d line(s) equal to %r, expected exactly 1 - "
                        "the anchor this control mutates is not where it believes it is"
                        % (rel, len(hits), stripped_line[:80]))
    line = lines[hits[0]]
    indent = line[:len(line) - len(line.lstrip())]
    lines[hits[0]] = indent + new_stripped_line
    _write_file(root, rel, "\n".join(lines))


# The shipped (hardened) slot-write exactly as it sits on ai/main, and the
# one-token fix: GNU sed needs a file operand, the landed line has none.
SED_WRITE_LINE = ('              sed -i "s%^\\#+PENDING-REVIEW:.*%'
                  '\\#+PENDING-REVIEW: ${NEWPENDING}%"\n')
SED_WRITE_FIXED = ('              sed -i "s%^\\#+PENDING-REVIEW:.*%'
                   '\\#+PENDING-REVIEW: ${NEWPENDING}%" "$CTL"\n')
LANDED_REREAD = ('            CURSLOT="$(grep -E \'^\\#+PENDING-REVIEW:\' "$CTL" | head -1 | '
                 'sed \'s/^#+PENDING-REVIEW:[[:space:]]*//\' | xargs || true)"\n')
LANDED_GUARD = ('            if [ -n "$NEWPENDING" ] || [ -z "$CURSLOT" ] || '
                '{ [ -n "${PENDING_BRANCH:-}" ] && [ "$SLOTISOURS" = "1" ]; }; then\n')


def build_green(root):
    """Bring a COPY to the green baseline: the sed write targets "$CTL".

    This is the green baseline: the non-clobber guard already re-reads $CURSLOT
    after the reset and gates the write, so once the write actually targets "$CTL"
    all four slot laws hold.

    Idempotent across BOTH shipped shapes: the pre-fix tree carries the operand-less
    SED_WRITE_LINE and needs it restored, but the Lead has since landed the fix, so
    the shipped tree already holds SED_WRITE_FIXED and there is nothing to restore.
    Insisting on the broken text once the real file is repaired turns the green
    baseline into a CANNOT RUN and blinds every control that builds on it - the same
    stale-anchor rot this harness exists to catch in others.
    """
    text = _read_file(root, WORKFLOW_REL)
    if SED_WRITE_LINE in text:
        _write_file(root, WORKFLOW_REL, text.replace(SED_WRITE_LINE, SED_WRITE_FIXED, 1))
    elif SED_WRITE_FIXED in text:
        pass  # already green - the fix is landed on the shipped tree
    else:
        raise CannotRun("control: neither the broken nor the fixed slot-write line is in "
                        "%s - the writer shape this harness understands has changed"
                        % WORKFLOW_REL)


def control_no_change(root):
    return None


def control_strip_operand(root):
    """Take the one-token fix back out: the write loses its "$CTL" file operand.

    Proves blank-guard can still fail on the repaired tree - without it, a control
    that only asserted "the shipped tree is red" would be grading a state that no
    longer exists and would silently stop exercising the leg.
    """
    _replace_once(root, WORKFLOW_REL, SED_WRITE_FIXED, SED_WRITE_LINE)


def control_reintroduce_approved_gate(root):
    """Put the 18:41Z deadlock back: the park needs approved + gate-green.

    Found STRUCTURALLY, not against a hand-typed copy of the gate line: the
    control pinned the exact three-clause exclusion the Lead shipped on
    2026-10-22, and cycle 10-l's `lane-dead` exclusion rewrote that line under
    it, so this control raised CANNOT RUN and killed the other seven with it.
    Reusing the leg's own walk means the control follows the gate wherever the
    Lead moves it, and an anchor that genuinely vanished is still a refusal.
    """
    _replace_line(root, WORKFLOW_REL, _park_gate(root),
                  'if [ "${AHEAD:-0}" -gt 0 ] && [ "$OUTCOME" = "approved" ] && '
                  '[ "$GATE" = "green" ]; then')


def control_drop_lane_dead_exclusion(root):
    """The fourth retain outcome leaves the park gate: a dead review lane drops it.

    Without this control the harness grades three exclusions and prints
    "all 3 retain outcome(s)" whatever the fourth does — which is precisely how
    `lane-dead` sat ungraded between the Lead's hardening and this segment.
    """
    gate = _park_gate(root)
    clause = '&& [ "$OUTCOME" != "lane-dead" ] '
    if clause not in gate:
        raise CannotRun("control: the park gate no longer carries %s - the exclusion this "
                        "control deletes is gone, so it grades nothing" % clause)
    _replace_line(root, WORKFLOW_REL, gate, gate.replace(clause, "", 1))


def control_drop_rejected_retain(root):
    """REVIEW-LOG law 4 stops being honored: a rejected branch leaves the slot."""
    _replace_once(root, WORKFLOW_REL,
                  ' || [ "$OUTCOME" = "rejected" ]; then', "; then")


def control_drop_merger_reread(root):
    """Take the durability re-read out: an empty turn parse is believed again."""
    text = _read_file(root, WORKFLOW_REL)
    start = text.find('          if [ -z "$PENDING_BRANCH" ]; then\n')
    end = text.find("          fi\n", start)
    if start < 0 or end < 0:
        raise CannotRun("control: the merger's slot re-read block is not where this "
                        "control believes it is")
    _write_file(root, WORKFLOW_REL, text[:start] + text[end + len("          fi\n"):])


def control_drop_loop_reread(root):
    """The hardened guard, minus its re-read: the write trusts its stale value."""
    _replace_once(root, WORKFLOW_REL, LANDED_REREAD, "")


def control_unguard_write(root):
    """The hardened write, minus the guard: nothing judges it, so an empty value blanks."""
    _replace_once(root, WORKFLOW_REL, LANDED_GUARD, '            if true; then\n')


def control_drop_write_site(root):
    """No slot write at all: the harness cannot understand its own input."""
    _replace_once(root, WORKFLOW_REL, SED_WRITE_FIXED,
                  '              sed -i "s%^\\#+STALL-COUNT:.*%\\#+STALL-COUNT: '
                  '${NEWPENDING}%" "$CTL"\n')


def control_introduce_unknown_outcome(root):
    """The merger grows a verdict no leg knows: the closure refuses, not greens.

    The counterfactual for cycle 10-l: rename a pinned outcome to a name this
    harness has never seen and check that grading STOPS with a refusal naming it,
    rather than quietly dropping one exclusion from a roster it still calls full.
    """
    _replace_line(root, WORKFLOW_REL, 'OUTCOME="no-pending"', 'OUTCOME="lane-timeout"')


def control_missing_workflow(root):
    os.remove(os.path.join(root, WORKFLOW_REL))


# (name, mutation, expected rc, expected text, build the green baseline first?)
CONTROLS = (
    ("operand fix is green", control_no_change, 0, "SLOT CHECK OK", True),
    ("sed operand stripped is red", control_strip_operand, 1, "blank-guard", True),
    ("approved+green park gate back", control_reintroduce_approved_gate, 1, "park-bootstrap", True),
    ("lane-dead exclusion deleted", control_drop_lane_dead_exclusion, 1, "lane-dead", True),
    ("rejected dropped from retain", control_drop_rejected_retain, 1, "verdict-retain", True),
    ("merger slot re-read deleted", control_drop_merger_reread, 1, "merger-reread", True),
    ("loop slot re-read deleted", control_drop_loop_reread, 1, "blank-guard", True),
    ("slot write left unguarded", control_unguard_write, 1, "blank-guard", True),
    ("slot write site removed", control_drop_write_site, 2, "CANNOT RUN", True),
    ("outcome literal unknown", control_introduce_unknown_outcome, 2, "never heard", True),
    ("workflow file missing", control_missing_workflow, 2, "CANNOT RUN", True),
)
EXPECTED_CONTROLS = 11


def selftest(root):
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d control(s) but this harness pins %d - "
                        "its population is no longer its own expectation"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = os.path.join(root, "scripts", "chain_slot_check.py")
    failures = []
    for name, mutation, expected_rc, expected_text, green_base in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="chain-slot-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                          ".pytest_cache", "dist", "build"))
            if green_base:
                build_green(target)
            mutation(target)
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-30s -> rc %d as expected (%s)"
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
    parser.add_argument("--root", default=os.getcwd(),
                        help="tree to grade (default: the current working directory)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the controls against copies and prove every leg can fail")
    parser.add_argument("--live", action="store_true",
                        help="also list author branches holding work ai/main has never seen")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.selftest:
        return selftest(root)
    if args.live:
        # Printed BEFORE the verdict, because the list is most useful on the tree
        # where the grading is RED (a red verdict exits before grade() returns).
        for note in live_note(root):
            print("  " + note)
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
