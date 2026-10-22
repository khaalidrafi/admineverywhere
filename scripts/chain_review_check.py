#!/usr/bin/env python3
"""Re-runnable check of the chain's DUTY-REVIEWER routing (Owner orders 18:14Z + 18:55Z).

WHY this exists (measured, not assumed). SEGREGATION LAW v2 says the review
duty belongs to a NAMED ROLE: the QA ENGINEER reviews every pending branch and
the VISITING SENIOR ENGINEER reviews when QA itself authored it. Both the
router (.github/scripts/turn_segment.sh:54) and the merger (.github/workflows/
agent-team.yml:726, :744) decide that by comparing the pending slot's
``author=`` value against a MEMBER id (``deepseek-v4.1-flash@qoder``). But the
slot's author is written from the turn seat's SEAT id
(``AUTHOR_ID=$(printf '%s' "$SEAT" | cut -d' ' -f1)``, agent-team.yml:824,
:847) — ``quality-assurance-engineer``, a different id space, spelled by a
different grammar. Two id spaces that never intersect:

  * the QA-authored arm is UNREACHABLE, so a branch authored by the QA seat is
    routed to the QA seat's own lane every single run;
  * the lane correctly refuses (reviewer-equals-author) and the merger's own
    same-member refusal (:744) can never fire either, so the collision is
    graded as an ordinary ``rejected``;
  * ``rejected`` RETAINS the branch in the single pending slot (:856, REVIEW-LOG
    law 4), and the next run routes it to the same self-refusing lane.

Live state at writing: #+PENDING-REVIEW carries
``branch=ai/turn-20261022-1904 | author=quality-assurance-engineer`` (agent-team/
TEAM-CONTROL.org:13) and agent-team/REVIEW-LOG.org holds one `* REVIEW` record
for exactly that branch, :OUTCOME: rejected — reviewer-equals-author. Under the
slot-write ordering (:847 park, then the :856 retain overwrite) NO future turn's
author branch can enter the slot while it sits there: the chain is again unable
to land anything, this time from the reviewer side. Same class as the bootstrap
deadlock the platform seat measured at 18:41Z (Lead-fixed in ba00442), one door
further down the pipeline.

The fix lives in Lead-owned files, so a seat may not apply it. What a seat CAN
hand over is (a) the patch, unapplied — docs/review-routing-fix.patch — and
(b) this check, so the Lead sees the routing in one command instead of in prose:

  AUTHOR-SPACE   the id space the slot's author= is WRITTEN in, derived from
                 the writer's own source, cross-checked against the value the
                 live slot actually carries.
  ROUTER-SPACE   every author= comparison in the duty-reviewer router is
                 against a value in THAT space.
  MERGER-SPACE   every author= comparison in the merger is too (both the
                 duty-reviewer expectation and the same-member refusal).
  LIVE-ROUTE     replay the router on the branch sitting in the slot NOW and
                 refuse when it hands the branch to the author's own seat.

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its input — never a false
red for a tree it has not measured). The shipped tree is RED on purpose; the
--selftest baseline is the DELIVERED PATCH applied to a copy, because a check
that can only ever say RED is not a check (DEVGUIDE *EIGHTH harness law).

  python3 scripts/chain_review_check.py                 # grade this tree
  python3 scripts/chain_review_check.py --root /tmp/x   # grade another tree
  python3 scripts/chain_review_check.py --selftest      # prove every leg can fail
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

WORKFLOW_REL = ".github/workflows/agent-team.yml"
SEGMENT_REL = ".github/scripts/turn_segment.sh"
CONTROL_REL = "agent-team/TEAM-CONTROL.org"
PATCH_REL = "docs/review-routing-fix.patch"

# The population this harness grades: one author= comparison in the router, two
# in the merger (the duty expectation and the same-member refusal). A site that
# vanishes silently would leave the law unenforced and the check still green, so
# the count is pinned, not printed (DEVGUIDE *ELEVENTH harness law) — a legitimate
# change bumps this literal in the SAME commit.
AUTHOR_SITES = {SEGMENT_REL: 1, WORKFLOW_REL: 2}

SEAT = "seat"
MEMBER = "member"


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


# --------------------------------------------------------------- id spaces
# MEMBER ID FORMAT LAW (Owner 13:22Z): PROVIDER/MODEL@PLATFORM — a member id
# always carries "@". A seat id is the lower-case role slug the control step's
# pointer grammar emits (platform-engineer, relief-engineer, ...). Anything
# else is outside both spaces and the harness says so instead of guessing.
def classify(literal, seat_vocab):
    value = literal.strip().strip('"').strip("'")
    if not value:
        return None
    if "@" in value:
        return MEMBER
    if value in seat_vocab or re.fullmatch(r"[a-z][a-z0-9-]*-engineer", value):
        return SEAT
    return None


def seat_vocabulary(texts):
    """The seat ids the chain itself emits: NEXT_SEAT=<slug> in the pointer grammar."""
    vocab = set()
    for text in texts:
        for match in re.finditer(r"NEXT_SEAT=([a-z0-9-]+)", text):
            vocab.add(match.group(1))
    return vocab


# ----------------------------------------------------------- symbol tables
ASSIGN_RE = re.compile(r'\b([A-Z_][A-Z0-9_]*)="([^"]*?)"')
ASSIGN_SUB_RE = re.compile(r'\b([A-Z_][A-Z0-9_]*)=\$\((.+?)\)')
ASSIGN_BARE_RE = re.compile(r'\b([A-Z_][A-Z0-9_]*)=([A-Za-z0-9][A-Za-z0-9_.@/-]*)')
VAR_REF_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")
ECHO_OUT_RE = re.compile(r'echo\s+"([a-z_]+)=\$\{?([A-Za-z_][A-Za-z0-9_]*)[^"}]*\}?"')
OUTPUT_REF_RE = re.compile(r"\$\{\{[^}]*outputs\.([a-z_]+)[^}]*\}\}")


def build_tables(texts):
    """Per-FILE symbol tables plus the step outputs that bridge them (a name can hold a seat id in one file and a member id in another)."""
    tables = {}
    echoes = {}
    for rel, text in texts.items():
        table = {}
        for regex in (ASSIGN_RE, ASSIGN_SUB_RE, ASSIGN_BARE_RE):
            for match in regex.finditer(text):
                table.setdefault(match.group(1), []).append(match.group(2))
        for match in ECHO_OUT_RE.finditer(text):
            echoes.setdefault(match.group(1), (rel, match.group(2)))
        tables[rel] = table
    return tables, echoes


def resolve(name, rel, tables, echoes, seat_vocab, depth=0):
    """The id space(s) a variable's value can hold; None when unresolvable."""
    if depth > 6:
        return None
    table = tables.get(rel, {})
    spaces = set()
    for rhs in table.get(name, []):
        rhs = rhs.strip()
        targets = {echoes[out] for out in OUTPUT_REF_RE.findall(rhs) if out in echoes}
        if not targets:
            targets = {(rel, ref) for ref in VAR_REF_RE.findall(rhs) if ref in table}
        if targets:
            for home, var in targets:
                space = resolve(var, home, tables, echoes, seat_vocab, depth + 1)
                if space:
                    spaces |= space
            continue
        space = classify(rhs, seat_vocab)
        if space:
            spaces.add(space)
    return spaces or None


CMP_RE = re.compile(
    r'\[\s*"\$\{PENDING_AUTHOR[^"]*\}"\s*=\s*"'
    r'(?:\$\{(?P<varbr>[A-Za-z_][A-Za-z0-9_]*)[^}]*\}'
    r'|\$(?P<var>[A-Za-z_][A-Za-z0-9_]*)'
    r'|(?P<lit>[^"$]+))"'
)


def author_sites(text):
    """Every `[ "$PENDING_AUTHOR..." = <right> ]` comparison in `text`."""
    out = []
    for match in CMP_RE.finditer(text):
        right = match.group("lit")
        var = match.group("varbr") or match.group("var")
        out.append((right, var, text[:match.start()].count("\n") + 1))
    return out


WRITE_RE = re.compile(r'author=\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
SLOT_RE = re.compile(r"^\#\+PENDING-REVIEW:\s*(.*)$", re.MULTILINE)


def written_author_space(workflow, tables, echoes, seat_vocab):
    """The id space the merger writes into the slot's author= (a retain is not a write)."""
    names = set(WRITE_RE.findall(workflow)) - {"PENDING_AUTHOR"}
    if not names:
        raise CannotRun("%s writes no author=${VAR} into #+PENDING-REVIEW — the "
                        "slot's grammar moved and this harness no longer understands "
                        "its input" % WORKFLOW_REL)
    spaces = set()
    for name in set(names):
        resolved = resolve(name, WORKFLOW_REL, tables, echoes, seat_vocab)
        if not resolved:
            raise CannotRun("the slot's author= is written from ${%s}, which this "
                            "harness cannot resolve to an id space — the writer's "
                            "source moved" % name)
        spaces |= resolved
    return spaces


def live_slot(control_text):
    line = SLOT_RE.search(control_text)
    value = (line.group(1).strip() if line else "")
    if not value:
        return None, None, None
    branch = re.search(r"branch=([^ |]+)", value)
    author = re.search(r"author=([^ |]+)", value)
    return (branch.group(1) if branch else ""), (author.group(1) if author else ""), value


# ------------------------------------------------------------- router shape
def routed_reviewer_seat(segment_text, author_value, tables, echoes, seat_vocab):
    """Replay the duty-reviewer router's if/else on an author value, as the file is written."""
    sites = author_sites(segment_text)
    if not sites:
        raise CannotRun("%s compares PENDING_AUTHOR nowhere — the duty-reviewer "
                        "router is gone and this harness cannot replay it" % SEGMENT_REL)
    arms = re.findall(r'REVIEWER_SEAT="([a-z0-9-]+)"', segment_text)
    if len(arms) < 2:
        raise CannotRun("%s assigns REVIEWER_SEAT %d time(s); the router needs a "
                        "then-arm and an else-arm to be replayed" % (SEGMENT_REL, len(arms)))
    then_arm, else_arm = arms[0], arms[1]
    right, var, _ = sites[0]
    compared = right
    if compared is None:
        literals = [value for value in tables[SEGMENT_REL].get(var, [])
                    if classify(value, seat_vocab)]
        if not literals:
            raise CannotRun("%s compares PENDING_AUTHOR against $%s, which resolves "
                            "to no id-space literal" % (SEGMENT_REL, var))
        compared = literals[0]
    if author_value == compared:
        return then_arm
    return else_arm


# ------------------------------------------------------------------- grade
def grade(root):
    workflow = read(root, WORKFLOW_REL)
    segment = read(root, SEGMENT_REL)
    control = read(root, CONTROL_REL)

    texts = {WORKFLOW_REL: workflow, SEGMENT_REL: segment}
    seat_vocab = seat_vocabulary(texts.values())
    tables, echoes = build_tables(texts)

    problems = []
    notes = []

    # ---- 1. AUTHOR-SPACE: what the writer puts in the slot, vs what the slot holds
    write_spaces = written_author_space(workflow, tables, echoes, seat_vocab)
    if len(write_spaces) > 1:
        raise CannotRun("the slot's author= resolves to %s — one field cannot be "
                        "written in two id spaces, so no comparison against it can "
                        "be graded" % "/".join(sorted(write_spaces)))
    write_space = next(iter(write_spaces))
    branch, author, raw = live_slot(control)
    notes.append("AUTHOR-SPACE: %s writes author=${...} in %s space" % (WORKFLOW_REL, write_space))
    if author:
        live_space = classify(author, seat_vocab)
        if live_space is None:
            raise CannotRun("the live #+PENDING-REVIEW carries author=%s, which is in "
                            "neither id space (member ids carry '@', seat ids end in "
                            "'-engineer') — the slot's grammar moved under this harness"
                            % author)
        if live_space != write_space:
            raise CannotRun("the writer resolves to %s space but the live slot holds "
                            "author=%s (%s space): %s — this harness's derivation "
                            "disagrees with the tree, so its verdict would be invented"
                            % (write_space, author, live_space, raw))
        notes.append("AUTHOR-SPACE: live slot agrees — branch=%s author=%s (%s space)"
                     % (branch, author, live_space))
    else:
        notes.append("AUTHOR-SPACE: #+PENDING-REVIEW is empty (nothing queued)")

    # ---- 2 + 3. ROUTER-SPACE / MERGER-SPACE: every author= comparison agrees
    for rel, text, leg in ((SEGMENT_REL, segment, "ROUTER-SPACE"),
                           (WORKFLOW_REL, workflow, "MERGER-SPACE")):
        sites = author_sites(text)
        if len(sites) != AUTHOR_SITES[rel]:
            raise CannotRun("%s holds %d author= comparison site(s), the pin is %d — a "
                            "site that came or went changes what the duty law enforces, "
                            "and this harness will not grade the law it cannot see"
                            % (rel, len(sites), AUTHOR_SITES[rel]))
        for right, var, line_no in sites:
            if right is not None:
                space = classify(right, seat_vocab)
                shown = '"%s"' % right
            else:
                space_set = resolve(var, rel, tables, echoes, seat_vocab)
                space = next(iter(space_set)) if space_set and len(space_set) == 1 else None
                shown = "$%s" % var
            if space is None:
                raise CannotRun("%s:%d compares PENDING_AUTHOR against %s, which this "
                                "harness cannot place in an id space — the comparison "
                                "moved, it is not necessarily wrong" % (rel, line_no, shown))
            if space != write_space:
                problems.append(
                    "%s: line %d compares the slot's author (%s space) against %s = "
                    "%s space. The two NEVER intersect, so the arm is dead code: an "
                    "author routed by its own seat id can never be recognised as the "
                    "%s, and the law that depends on the match cannot be enforced"
                    % (leg, line_no, write_space, shown, space,
                       "QA lane handing off" if leg == "ROUTER-SPACE" else "merger's refusal"))
        notes.append("%s: %d author= comparison site(s) graded" % (leg, len(sites)))

    # ---- 4. LIVE-ROUTE: replay the router on what is queued NOW
    if author:
        routed = routed_reviewer_seat(segment, author, tables, echoes, seat_vocab)
        if routed == author:
            problems.append(
                "LIVE-ROUTE: the router in %s sends %s (author=%s) to the %s lane — "
                "the author's OWN seat. The duty reviewer refuses (reviewer-equals-"
                "author), 'rejected' RETAINS the branch in the single slot (%s: the "
                "retain clause runs after the author-branch park), and the next run "
                "routes it identically: nothing can ever be approved, and no newer "
                "author branch can enter the slot" % (SEGMENT_REL, branch, author, routed,
                                                      WORKFLOW_REL))
        else:
            notes.append("LIVE-ROUTE: %s (author=%s) is routed to %s — a different seat"
                         % (branch, author, routed))
    else:
        notes.append("LIVE-ROUTE: nothing queued, nothing to replay")

    notes.append("NOTE: a 'rejected' pending holds the single slot by REVIEW-LOG law 4 "
                 "— survivable ONLY while the routing can hand a branch to a reviewer "
                 "that is not its author. Clearing a poisoned slot is a Lead edit to "
                 "%s, which no seat may write" % CONTROL_REL)

    if problems:
        raise Red("\n".join(problems))
    print("REVIEW-ROUTING CHECK OK — slot written in %s space, all author= comparisons "
          "agree, live pending routed away from its author" % write_space)
    for note in notes:
        print("  " + note)
    return 0


# ----------------------------------------------------------------- controls
def _write(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def _replace(root, rel, old, new, required=True):
    text = read(root, rel)
    if old not in text:
        if required:
            raise CannotRun("control: %r is not in %s — the control no longer matches "
                            "the tree it mutates" % (old[:60], rel))
        return text
    _write(root, rel, text.replace(old, new, 1))
    return text


def apply_patch(root):
    patch = os.path.join(root, PATCH_REL)
    if not os.path.exists(patch):
        raise CannotRun("the delivered patch %s is missing — the baseline cannot be built"
                        % PATCH_REL)
    check = subprocess.run(("git", "apply", "--check", patch), cwd=root,
                           capture_output=True, text=True)
    if check.returncode != 0:
        raise CannotRun("the delivered patch does not apply to this tree: %s"
                        % check.stderr.strip()[:300])
    done = subprocess.run(("git", "apply", patch), cwd=root, capture_output=True, text=True)
    if done.returncode != 0:
        raise CannotRun("the delivered patch failed to apply: %s" % done.stderr.strip()[:300])


def control_no_change(root):
    return None


def control_member_router(root):
    """Put the router back to comparing a member id: ROUTER-SPACE must fire."""
    _replace(root, SEGMENT_REL, 'if [ "${PENDING_AUTHOR:-}" = "$QA_SEAT" ]; then',
             'if [ "${PENDING_AUTHOR:-}" = "$QA_MEMBER" ]; then')


def control_member_merger(root):
    """Put the merger's expectation back to a member id: MERGER-SPACE must fire."""
    _replace(root, WORKFLOW_REL, 'if [ "${PENDING_AUTHOR:-x}" = "$QA_SEAT" ]; then',
             'if [ "${PENDING_AUTHOR:-x}" = "$QA_MEMBER" ]; then')


def control_self_routed_author(root):
    """Point the QA arm at the wrong seat: the live pending must be self-routed."""
    _replace(root, SEGMENT_REL, 'QA_SEAT="quality-assurance-engineer"',
             'QA_SEAT="platform-engineer"')


def control_foreign_slot_author(root):
    """A slot value from the other id space: the writer's derivation must be refused."""
    _replace(root, CONTROL_REL, "author=quality-assurance-engineer",
             "author=deepseek-v4.1-flash@qoder")


def control_drop_write(root):
    """The slot grammar moves: CANNOT RUN, never a false red."""
    _replace(root, WORKFLOW_REL, "author=${AUTHOR_ID}", "reviewer=${AUTHOR_ID}")


def control_drop_site(root):
    """A comparison site vanishes: the harness no longer grades what it claims to."""
    _replace(root, WORKFLOW_REL,
             'elif [ "${PENDING_AUTHOR:-x}" = "${REVIEW_SEAT:-none}" ]; then',
             'elif [ "${REVIEW_SEAT:-none}" = "${REVIEW_SEAT:-none}" ]; then')


def control_missing_segment(root):
    os.remove(os.path.join(root, SEGMENT_REL))


CONTROLS = (
    ("patched baseline is green", control_no_change, 0, "REVIEW-ROUTING CHECK OK", True),
    ("shipped tree is red", control_no_change, 1, "ROUTER-SPACE", False),
    ("router back to member space", control_member_router, 1, "ROUTER-SPACE", True),
    ("merger back to member space", control_member_merger, 1, "MERGER-SPACE", True),
    ("live pending self-routed", control_self_routed_author, 1, "LIVE-ROUTE", True),
    ("slot holds the other space", control_foreign_slot_author, 2, "CANNOT RUN", True),
    ("author= write gone", control_drop_write, 2, "CANNOT RUN", True),
    ("comparison site gone", control_drop_site, 2, "CANNOT RUN", True),
    ("router file missing", control_missing_segment, 2, "CANNOT RUN", True),
)


def selftest(root):
    script = os.path.join(root, "scripts", "chain_review_check.py")
    failures = []
    for name, mutation, expected_rc, expected_text, patched in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="chain-review-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                          ".pytest_cache", "dist", "build"))
            if patched:
                apply_patch(target)
            mutation(target)
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-28s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
            else:
                failures.append("%s: expected rc %d containing %r, got rc %d: %s"
                                % (name, expected_rc, expected_text, proc.returncode,
                                   out.strip()[:320]))
        except CannotRun as exc:
            failures.append("%s: control could not be built — %s" % (name, exc))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise Red("\n".join(failures))
    print("SELFTEST OK — %d control(s), every leg proved able to fail" % len(CONTROLS))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="grade the chain's duty-reviewer routing")
    parser.add_argument("--root", default=None, help="grade another tree (control)")
    parser.add_argument("--selftest", action="store_true",
                        help="prove every leg can fail, against copies of this tree")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root) if args.root else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
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
