#!/usr/bin/env python3
"""Re-runnable check of the chain's REVIEW-VERDICT contract (SEGREGATION LAW v2).

WHY this exists (measured, not assumed). Under the segregation law a branch
lands on exactly one thing: the literal token the duty reviewer's own answer is
supposed to end with. Tonight that token was lost twice over, and every seat
that looked had to read the Lead-owned chain by hand to find it:

  1. [06:5xZ, REVIEW-LOG / commit 784b2ed] the duty QA lane DID review
     ai/turn-20261024-0659 and produced a complete verdict-ready report —
     "Law check — clean", two non-blocking findings, the prior rejection's
     defect confirmed closed — and ended its answer on prose. The brief makes
     the last line a machine-readable token, the host extracts it with a grep
     for that token, found nothing, and the merger wrote `review-missing`:
     the branch stayed pending and the stall grew (c1f3419, `#+STALL-COUNT: 1`).
     A re-review costs a lane call, ~15-20 min of the 45-min step budget and a
     rotation tick — and can lose the token again.
  2. [same file, line 1] `Model "deepseek-v4.1-flash" is not available right
     now; using "qfmodel" instead.` The CLI silently substituted the pinned
     reviewer brain, and the review lane accepted whatever the substitute
     printed. Every SEAT lane has an honest-lane guard (a network/dead-marker
     grep that turns an exit-0-with-no-work into a failed lane, measured at
     turn_segment.sh:394-400, :438, :474-480); the lane whose ENTIRE
     deliverable is a verdict string has none. A different model is exactly
     when a required format stops being honoured — which is what happened.

So the contract lives in three places that nothing compares: the token the
BRIEF instructs, the token the EXTRACTOR greps, and the FILE both sides name —
plus two reviewer member ids spelled once per carrier (the segment script picks
the reviewer, the workflow merger grades it). Any one of those five drifting is
silently "no verdict", "unmergeable verdict" or "refused-wrong-reviewer forever".
A finding delivered as prose is a finding the next reader has to trust; this
makes the whole review-lane path re-runnable, read-only against Lead-owned
files, in one command.

  brief-token        when a pending branch exists, the reviewer brief instructs
                     the verdict token explicitly: a "last line of your answer"
                     law AND exactly the two pinned tokens, no more, no other
                     spelling. A reviewer that is never told the format cannot
                     produce it, and a lane can be edited out from under the law.
  extractor-agrees   the host extractor greps the SAME token set the brief
                     instructs, reads the SAME file the lanes write, takes the
                     LAST match (so the reviewer's own closing token outranks any
                     copy of the instruction it quoted), and runs HOST-SIDE (the
                     verdict is exported through $GITHUB_OUTPUT, which the
                     container never receives — extracting inside the container
                     writes a verdict into nothing).
  lane-coverage      every reviewer seat the selector can assign has a lane in
                     the dispatch, and every such lane is handed the brief and
                     redirected into the verdict file. A selector value with no
                     lane falls through to `*)` and prints "no duty reviewer" —
                     which reads at the merger exactly like a lost token.
  reviewer-ids       the two carriers spell the reviewer member ids identically,
                     once each, and both key the duty on the author's SEAT KEY
                     (the 2026-10-22 20:15Z author-id fix). Drift here is the
                     worst shape: a real duty verdict graded
                     `refused-wrong-reviewer` for ever, with nothing red.
  lane-guard         the review output is checked for a substituted/dead lane
                     BEFORE its verdict is trusted, in either outcome. The
                     shipped guard (Lead 10-l, .github/scripts/turn_segment.sh)
                     fires only when NO verdict token came out, so a substituted
                     brain that still prints `VERDICT: APPROVED` is trusted with
                     no provenance record — the class of the five 2026-10-24
                     verdicts whose transcript line 1 read "using qfmodel
                     instead" (Lead 10-az/10-bc/10-bf/10-bh/10-bj). A guard
                     condition on an empty verdict therefore still grades RED.
  scratch-ignored    the verdict file and the inner script live in the workspace
                     the host commits with `git add -A`, so both must be
                     gitignored — the leak that cost ai/turn-20261024-0454 its
                     verdict (BENIGN-REJECTED 05:56Z) and that 0339/0527 still
                     carried. OK on the shipped tree since ai/turn-20261024-0607
                     landed the ignore rule.

Verdicts follow the house convention (docs/DEVGUIDE.md *EIGHTH* + *ELEVENTH*
harness laws): 0 = OK, 1 = RED (a claim is false), 2 = CANNOT RUN (the harness no
longer understands its own input — never a false red for a tree it has not
measured). The leg roster is pinned, so a leg that vanishes is a refusal, not a
quieter green.

The shipped tree is RED on the last two legs BY DESIGN: both fixes are in
Lead-owned files (`.github/scripts/turn_segment.sh`, and the `.gitignore` half
that the pending branch ai/turn-20261024-0659 already carries). The controls
therefore BUILD their own green baseline — the two repairs, reconstructed on a
copy — so every leg is proven able to pass as well as to fail; a check that can
only ever say RED is not a check.

  python3 scripts/review_verdict_check.py                  # grade this tree
  python3 scripts/review_verdict_check.py --root /tmp/copy # grade another tree
  python3 scripts/review_verdict_check.py --selftest       # 13 controls, every leg able to fail

Deliberately NOT named `*_diff.py`: that glob IS the landing gate's twin roster
(`scripts/landing_gate.py` EXPECTED_TWINS cross-checks every `scripts/*_diff.py`
on disk against the harnesses its `--fe` legs actually run), and this grades the
CHAIN, not a pair of cross-language artifacts — same ruling as
scripts/chain_test_check.py, scripts/chain_session_check.py and
scripts/chat_feature_check.py.
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
# tree it grades proves nothing (DEVGUIDE *ELEVENTH law*).
SEGMENT_REL = ".github/scripts/turn_segment.sh"
WORKFLOW_REL = ".github/workflows/agent-team.yml"
GITIGNORE_REL = ".gitignore"

# The one file the review duty produces, and the scratch file the host writes
# beside it. Both sit in the workspace the host `git add -A`s.
REVIEW_FILE = ".turn-review.txt"
INNER_SCRIPT = ".turn-inside.sh"
SCRATCH_NAMES = (REVIEW_FILE, INNER_SCRIPT)

# The verdict vocabulary. The brief instructs it, the extractor greps it, and
# the merger branches on APPROVED alone (.github/workflows/agent-team.yml:829).
VERDICT_TOKENS = ("APPROVED", "REJECTED")
LAST_LINE_LAW = "LAST line of your answer MUST be exactly"

# The reviewer seats the host selector can assign, and the member-id variables
# the two carriers must spell identically.
REVIEWER_SEATS = ("quality-assurance-engineer", "visiting-engineer")
MEMBER_ID_VARS = ("QA_MEMBER", "VISITING_MEMBER")
# The author-side key the duty is keyed on: PENDING_AUTHOR is a SEAT KEY, not a
# member id (night-watch fix, measured in REVIEW-LOG 19:46Z + 20:10Z).
AUTHOR_SEAT_KEY = "quality-assurance-engineer"

# The marker measured at the top of tonight's review output: the CLI substituted
# the pinned reviewer model and kept going. No seat-lane marker list covers it.
SUBSTITUTION_MARKER = "not available right now"
# The variable name an UNGATED provenance stamp would write. The chain records
# `lane_dead` only when the verdict token is missing, so nothing today names a
# substituted brain that still decided — this is the shape that would.
PROVENANCE_STAMP = "REVIEW_PROVENANCE"

# Six claims, pinned in order. A leg that disappears from the runner is
# CANNOT RUN — a vanished leg prints no red to argue with.
LEG_ROSTER = ("brief-token", "extractor-agrees", "lane-coverage",
              "reviewer-ids", "lane-guard", "scratch-ignored")
EXPECTED_LEGS = 6

# Controls are pinned too, so a deleted control is a refusal, not a shorter
# "SELFTEST OK".
EXPECTED_CONTROLS = 15

# ------------------------------------------------------------- file shapes
INNER_OPEN_RE = re.compile(r"cat\s+>\s+\"?\$PWD/\.turn-inside\.sh\"?\s*<<'([A-Za-z_]+)'")
SEGMENT_CALL_RE = re.compile(r"bash\s+\S*\.github/scripts/turn_segment\.sh")
BRIEF_INIT_RE = re.compile(r"^\s*REVIEW_BRIEF=\"\"\s*$")
FI_RE = re.compile(r"^\s*fi\s*$")
CASE_REVIEW_RE = re.compile(r"^\s*case\s+\"\$REVIEWER_SEAT\"\s+in\s*$")
ESAC_RE = re.compile(r"^\s*esac\s*$")
LABEL_RE = re.compile(r"^\s*([A-Za-z0-9_*][A-Za-z0-9_*-]*)\)\s*(?:#.*)?$")
MEMBER_ID_RE = r'^\s*(%s)="([^"]*)"\s*(?:#.*)?$'
EXTRACT_RE = re.compile(r"^\s*REVIEW_VERDICT=\$\(")
ALT_RE = re.compile(r"VERDICT:\[\[:space:\]\]\*\(([^)]*)\)")
GREP_ON_REVIEW_FILE_RE = re.compile(r"grep\s.*%s" % re.escape(REVIEW_FILE))


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


# ------------------------------------------------------------------ parsing
def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CannotRun("cannot read %s: %s" % (rel, exc))


def dedent(lines):
    """Strip the common indent so `^fi'` means what the shell means.

    The inner script sat INLINE in the workflow until eaf34bd extracted the
    segment step (GitHub refuses an inline `run:` over 21000 chars); YAML
    indentation is not part of the script, so both shapes must grade the same.
    The body of a QUOTED heredoc is verbatim, so when the block sat at column 0
    this is a no-op; it only removes indentation the heredoc really carries.
    """
    return [l.lstrip() if l.strip() else l for l in lines]


def split_carrier(text, rel):
    """(inner, host) line lists for the script that writes .turn-inside.sh."""
    lines = text.splitlines()
    start = None
    marker = None
    for index, line in enumerate(lines):
        match = INNER_OPEN_RE.search(line)
        if match:
            start = index
            marker = match.group(1)
            break
    if start is None:
        raise CannotRun("neither %s nor %s writes a %s heredoc — the chain "
                        "changed shape and this harness has not been retyped"
                        % (SEGMENT_REL, WORKFLOW_REL, INNER_SCRIPT))
    end = None
    for index in range(start + 1, len(lines)):
        if lines[index].strip() == marker:
            end = index
            break
    if end is None:
        raise CannotRun("the %s heredoc in %s is never closed" % (marker, rel))
    inner = dedent(lines[start + 1:end])
    host = dedent(lines[:start + 1] + lines[end:])
    # +1 for 1-based file lines, +1 again because the heredoc opener itself is
    # not part of the body: an inner-script line N is FILE line N + offset.
    return inner, host, start + 1


def block_after(lines, start, end_re):
    """Lines from `start` through the first line after it matching `end_re`."""
    for index in range(start + 1, len(lines)):
        if end_re.match(lines[index]):
            return lines[start:index + 1]
    return lines[start:]


def find_case_block(inner):
    for index, line in enumerate(inner):
        if CASE_REVIEW_RE.match(line):
            return index, block_after(inner, index, ESAC_RE)
    raise CannotRun("no `case \"$REVIEWER_SEAT\" in` dispatch in the inner script — "
                    "there is no duty-reviewer lane to grade")


def case_tail(inner, case_end):
    """What runs after the dispatch, inside the pending-branch guard."""
    for index in range(case_end, len(inner)):
        if FI_RE.match(inner[index]):
            return inner[case_end:index]
    return inner[case_end:]


def label_body(block, label):
    """The lines of one `case` label's body, or None when the label is absent.

    A body ends at the next label (`visiting-engineer)`, `*)`) or at `esac`.
    Comments are dropped: a lane described in a comment is not a lane called.
    """
    lines = [l for l in block if not l.strip().startswith("#")]
    for index, line in enumerate(lines):
        if ESAC_RE.match(line):
            break
        match = LABEL_RE.match(line)
        if match and match.group(1) == label:
            body = []
            for candidate in lines[index + 1:]:
                if ESAC_RE.match(candidate):
                    break
                nxt = LABEL_RE.match(candidate)
                if nxt:
                    break
                body.append(candidate)
            return body
    return None


def labels(block):
    out = []
    for line in block:
        if line.strip().startswith("#"):
            continue
        match = LABEL_RE.match(line)
        if match and match.group(1) != "in":
            out.append(match.group(1))
        if ESAC_RE.match(line):
            break
    return out


# ---------------------------------------------------------------------- legs
def leg_brief_token(host):
    start = None
    for index, line in enumerate(host):
        if BRIEF_INIT_RE.match(line):
            start = index
            break
    if start is None:
        raise CannotRun("no `REVIEW_BRIEF=\"\"` block on the host side of %s — the "
                        "duty reviewer is never briefed" % SEGMENT_REL)
    region = "\n".join(block_after(host, start, FI_RE))
    if "PENDING_BRANCH" not in region:
        raise Red("brief-token: the reviewer brief is built without a pending-branch "
                  "guard — a review runs (and a verdict is expected) with nothing queued")
    if LAST_LINE_LAW not in region:
        raise Red("brief-token: the brief no longer instructs the token as the LAST "
                  "line of the answer — this is precisely how 0659 lost its verdict")
    tokens = re.findall(r"VERDICT:\s*([A-Z]+)", region)
    if sorted(set(tokens)) != sorted(VERDICT_TOKENS):
        raise Red("brief-token: the brief instructs %s, the contract is %s"
                  % (sorted(set(tokens)) or "nothing", list(VERDICT_TOKENS)))
    if len(tokens) != len(VERDICT_TOKENS):
        raise Red("brief-token: the brief carries %d token sites, the contract has %d "
                  "(a third spelling is a token the extractor cannot read)"
                  % (len(tokens), len(VERDICT_TOKENS)))
    return "the brief instructs the last line as one of %s" % "/".join(VERDICT_TOKENS)


def leg_extractor_agrees(inner, host):
    line_no = None
    line = None
    for index, candidate in enumerate(host):
        if EXTRACT_RE.match(candidate):
            line_no, line = index + 1, candidate
            break
    if line is None:
        if any(EXTRACT_RE.match(l) for l in inner):
            raise Red("extractor-agrees: the verdict is extracted INSIDE the container, "
                      "which never receives $GITHUB_OUTPUT — the extraction writes into "
                      "nothing and every run reads as review-missing")
        raise CannotRun("no `REVIEW_VERDICT=$(...)` extractor on the host side of %s — "
                        "nothing turns a review into a verdict" % SEGMENT_REL)
    if REVIEW_FILE not in line:
        raise Red("extractor-agrees: line %d reads %r, not the file the review lanes "
                  "write (%s)" % (line_no, line.strip()[:60], REVIEW_FILE))
    match = ALT_RE.search(line)
    if not match:
        raise Red("extractor-agrees: line %d no longer greps a token alternation this "
                  "harness recognises — the contract moved without this file" % line_no)
    alts = tuple(a for a in match.group(1).split("|"))
    if sorted(alts) != sorted(VERDICT_TOKENS):
        raise Red("extractor-agrees: the extractor greps %s while the brief instructs %s — "
                  "a verdict in the instructed shape is invisible to the merger"
                  % (list(alts), list(VERDICT_TOKENS)))
    if "tail -1" not in line:
        raise Red("extractor-agrees: the extractor no longer takes the LAST match, so a "
                  "quoted copy of the brief can outrank the reviewer's own verdict")
    evid = [l for l in host if re.match(r"^\s*REVIEW_EVID=\$\(", l)]
    if not evid:
        raise Red("extractor-agrees: no REVIEW_EVID line — the verdict reaches the merger "
                  "with no evidence behind it")
    for line2 in evid:
        if REVIEW_FILE not in line2:
            raise Red("extractor-agrees: REVIEW_EVID reads a different file than "
                      "REVIEW_VERDICT — one of the two is not the review output")
    return "extractor greps %s from %s, last match wins, host-side" % ("/".join(alts), REVIEW_FILE)


def leg_lane_coverage(inner, host, case_index, case_block):
    # `search`, not a line-start match: the selector assigns all three reviewer
    # variables on ONE line (turn_segment.sh:74/:76), so an anchored read finds
    # only the first of them and grades a duty that plainly exists as empty.
    selector = set(re.findall(r'REVIEWER_SEAT="([a-z0-9-]+)"', "\n".join(host)))
    if selector != set(REVIEWER_SEATS):
        raise Red("lane-coverage: the selector can assign %s, this harness pins %s — the "
                  "duty is chosen from one list and executed from another"
                  % (sorted(selector), sorted(REVIEWER_SEATS)))
    present = set(labels(case_block)) - {"*"}
    if present != set(REVIEWER_SEATS):
        raise Red("lane-coverage: %s has no lane in the dispatch — a run that selects it "
                  "prints `no duty reviewer`, which the merger reads exactly like a lost "
                  "verdict" % sorted(set(REVIEWER_SEATS) - present))
    for seat in REVIEWER_SEATS:
        body = label_body(case_block, seat)
        if body is None:
            raise Red("lane-coverage: no body for the %s lane" % seat)
        text = "\n".join(body)
        if "$REVIEW_BRIEF" not in text:
            raise Red("lane-coverage: the %s lane is called without the reviewer brief — "
                      "a reviewer who never sees the format law cannot emit the token" % seat)
        if REVIEW_FILE not in text:
            raise Red("lane-coverage: the %s lane does not redirect into %s — its answer "
                      "goes to the step log, where the extractor cannot find it" % (seat, REVIEW_FILE))
        # Owner rotation 2026-10-25 made the QA lane's goose call PRIMARY with the
        # demoted qoder call as its fallback. One brief-carrying call is not
        # coverage: the pre-rotation primary died 17 consecutive review-missing
        # runs, and whichever call answers — primary or fallback — must have
        # received the format law. A whole-body contains-check let the lane grade
        # GREEN with a brief-less primary (the fallback's brief carried it), the
        # exact shape that made the pre-rotation `lane-unbriefed` control inert:
        # it mutated the then-PRIMARY qoder line and the leg stayed green.
        call_lines = [l for l in body
                      if re.search(r"\b(goose|qoder|codebuddy|claude|aider)\b", l)]
        for call in call_lines:
            if "$REVIEW_BRIEF" not in call and "-t " in call + " ":
                raise Red("lane-coverage: the %s lane runs `%s` without $REVIEW_BRIEF — "
                          "a reviewer invoked off the format law cannot emit the token"
                          % (seat, call.strip()[:72]))
        if seat == "quality-assurance-engineer":
            if not re.search(r"^\s*else\s*$", text, re.M):
                raise Red("lane-coverage: the QA lane has no fallback arm at all — the "
                          "rotation shipped one BECAUSE the primary died 17 consecutive "
                          "review-missing runs; a single-call lane silently revives that "
                          "failure mode")
            after = re.split(r"^\s*else\s*$", text, flags=re.M, maxsplit=1)[1]
            if ("qoder" in after) and ("$REVIEW_BRIEF" not in after):
                raise Red("lane-coverage: the QA lane's fallback re-invokes without "
                          "$REVIEW_BRIEF — the demoted qoder call would answer a "
                          "prompt that never saw the format law")
    tail_text = "\n".join(case_tail(inner, case_index + len(case_block)))
    if "REVIEWER_SEAT" not in tail_text:
        raise Red("lane-coverage: nothing reports which duty reviewer ran after the "
                  "dispatch — a silent fall-through is indistinguishable from a verdict")
    return "%d reviewer seats, each briefed and writing %s" % (len(REVIEWER_SEATS), REVIEW_FILE)


def leg_reviewer_ids(inner, host, workflow):
    found = {}
    for rel, lines in ((SEGMENT_REL, host), (WORKFLOW_REL, workflow.splitlines())):
        for var in MEMBER_ID_VARS:
            pattern = re.compile(MEMBER_ID_RE % var)
            hits = [pattern.match(l).group(2) for l in lines if pattern.match(l)]
            if not hits:
                raise Red("reviewer-ids: %s does not define %s — either the reviewer is "
                          "unnamed or this carrier is no longer the live one" % (rel, var))
            if len(set(hits)) > 1:
                raise Red("reviewer-ids: %s defines %s twice with different values (%s) — "
                          "one file cannot agree with the other" % (rel, var, sorted(set(hits))))
            found.setdefault(var, []).append((rel, hits[0]))
    for var, pairs in found.items():
        values = set(v for _, v in pairs)
        if len(values) > 1:
            raise Red("reviewer-ids: %s is %s across the carriers (%s) — the merger grades "
                      "the reviewer against ITS literal, so a duty verdict lands "
                      "refused-wrong-reviewer forever"
                      % (var, "spelled differently",
                         ", ".join("%s=%s" % (r, v) for r, v in pairs)))
    keyed = []
    for rel, lines in ((SEGMENT_REL, host), (WORKFLOW_REL, workflow.splitlines())):
        text = "\n".join(lines)
        if ('"%s"' % AUTHOR_SEAT_KEY) not in text:
            raise Red("reviewer-ids: %s no longer keys the duty on the author's SEAT KEY "
                      "(%r) — the 2026-10-22 20:15Z author-id fix is gone, so QA can be "
                      "picked to review its own branch" % (rel, AUTHOR_SEAT_KEY))
        keyed.append(rel)
    return "reviewer ids agree across %s; duty keyed on the author seat key in %s" % (
        " and ".join(sorted(set(r for rs in found.values() for r, _ in rs))),
        " + ".join(keyed))


def _guard_is_gated(lines, index):
    """True when the guard at `index` only runs as part of a test on an EMPTY verdict.

    The shipped guard is the middle of `if [ -z "$REVIEW_VERDICT" ] && ... &&
    grep -q '<marker>' ...; then`, so walking the `&&` chain back to its `if`
    finds the condition that makes it fire only in the no-verdict case.
    """
    j = index
    while j > 0 and (lines[j].lstrip().startswith("&&")
                     or lines[j - 1].rstrip().endswith("&&")):
        j -= 1
    window = "\n".join(lines[max(0, j - 3):index + 1])
    return '-z "$REVIEW_VERDICT"' in window


def leg_lane_guard(inner, host):
    guards = []
    for rel, lines in ((INNER_SCRIPT, inner), ("%s host side" % SEGMENT_REL, host)):
        for index, line in enumerate(lines):
            if GREP_ON_REVIEW_FILE_RE.search(line) and SUBSTITUTION_MARKER in line:
                guards.append((rel, index, line, _guard_is_gated(lines, index)))
    if not guards:
        raise Red("lane-guard: nothing checks the review output before its verdict "
                  "is trusted. Measured at line 1 of the 0659 review output: the CLI "
                  "printed %r and the lane accepted whatever the substitute brain wrote "
                  "— while every SEAT lane greps a dead-lane marker before calling "
                  "itself OK (the honest-lane guards in %s). FIX (Lead-owned): grep the "
                  "review file for the substitution marker right after the dispatch."
                  % (SUBSTITUTION_MARKER, SEGMENT_REL))
    if not [g for g in guards if not g[3]]:
        raise Red("lane-guard: %d guard(s) on the review output, EVERY one conditioned "
                  "on an empty verdict (%s) — so a substituted reviewer that still "
                  "prints `VERDICT: APPROVED/REJECTED` is trusted with no provenance "
                  "record. That is the class of the five 2026-10-24 verdicts the Lead "
                  "triaged from transcripts only (10-az, 10-bc, 10-bf, 10-bh, 10-bj: "
                  "transcript line 1 = 'Model ... is not available right now; using "
                  "qfmodel instead', lane_dead=0 because a verdict was produced). FIX "
                  "(Lead-owned, the 10-bb 'provenance stamping' item): stamp the "
                  "ci-review record from the substitution marker WHETHER OR NOT a "
                  "verdict came out."
                  % (len(guards), " | ".join(sorted(set("%s [%s]" % (r, line.strip()[:58])
                                                        for r, _, line, _ in guards)))))
    full = [g for g in guards if not g[3]]
    return ("review output guarded %d time(s); %d unconditional on the verdict token "
            "(%s) — a substituted brain is recorded even when it decides"
            % (len(guards), len(full),
               " | ".join(sorted(set("%s [%s]" % (r, line.strip()[:58])
                                     for r, _, line, _ in full)))))


def leg_scratch_ignored(root):
    text = read(root, GITIGNORE_REL)
    # Accepted spellings: the bare name, `/name` (root-only) and `./name`. A
    # gitignore is a set of PATTERNS, and grading one legitimate spelling as a
    # missing one would be a false red — the worse failure of the two.
    names = set()
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        names.add(entry.lstrip("/").lstrip("./") if entry.startswith("/") else entry)
    missing = [n for n in SCRATCH_NAMES
               if n not in names and "/" + n not in names and "./" + n not in names]
    if missing:
        raise Red("scratch-ignored: %s %s not ignored, and the host commits the workspace "
                  "with `git add -A` (%s) — that is how a review verdict ends up inside a "
                  "branch and costs it the review (0454, BENIGN-REJECTED 05:56Z; 0339/0527 "
                  "still carry it)" % (" and ".join(missing),
                                      "is" if len(missing) == 1 else "are", SEGMENT_REL))
    return "%s ignored (the host's `git add -A` cannot sweep a verdict into a branch)" % (
        " + ".join(SCRATCH_NAMES),)


# ------------------------------------------------------------------- grading
def carriers(root):
    segment = read(root, SEGMENT_REL)
    workflow = read(root, WORKFLOW_REL)
    if not SEGMENT_CALL_RE.search(workflow):
        raise Red("the workflow does not run %s, yet this harness grades it as the "
                  "chain — a script the chain does not run must not be graded as if it did"
                  % SEGMENT_REL)
    inner, host, inner_offset = split_carrier(segment, SEGMENT_REL)
    # A second carrier writing the same file is a race, not a fallback.
    other_inner = None
    try:
        other_inner = split_carrier(workflow, WORKFLOW_REL)[0]
    except CannotRun:
        other_inner = None
    if other_inner:
        raise Red("TWO carriers write the %s heredoc — %s inline and %s: grading the "
                  "wrong one would be a false green" % (INNER_SCRIPT, WORKFLOW_REL, SEGMENT_REL))
    return inner, host, workflow, inner_offset


def grade(root):
    inner, host, workflow, inner_offset = carriers(root)
    case_index, case_block = find_case_block(inner)
    notes = []
    notes.append("CARRIER: %s (run by %s); review lanes at %s:%d-%d"
                 % (SEGMENT_REL, WORKFLOW_REL, SEGMENT_REL,
                    inner_offset + case_index + 1,
                    inner_offset + case_index + len(case_block)))
    runners = {
        "brief-token": lambda: leg_brief_token(host),
        "extractor-agrees": lambda: leg_extractor_agrees(inner, host),
        "lane-coverage": lambda: leg_lane_coverage(inner, host, case_index, case_block),
        "reviewer-ids": lambda: leg_reviewer_ids(inner, host, workflow),
        "lane-guard": lambda: leg_lane_guard(inner, host),
        "scratch-ignored": lambda: leg_scratch_ignored(root),
    }
    if sorted(runners) != sorted(LEG_ROSTER) or len(runners) != EXPECTED_LEGS:
        raise CannotRun("the leg roster is %s but this harness runs %s — a vanished leg "
                        "prints no red to argue with" % (list(LEG_ROSTER), sorted(runners)))
    # Every leg is graded, not stopped at the first: the Lead needs the whole
    # list of what the review lane does not honour, and one red must never hide
    # a second one sitting behind it.
    reds = []
    for name in LEG_ROSTER:
        try:
            notes.append("  OK  %-16s %s" % (name, runners[name]()))
        except Red as exc:
            reds.append(str(exc))
            notes.append("  RED %-16s (named below — every red is reported, not just the first)" % name)
    print("\n".join(notes))
    if reds:
        raise Red("\n".join(reds))
    print("REVIEW-VERDICT CHECK OK — %d legs green on %s" % (EXPECTED_LEGS, root))
    return 0


# ------------------------------------------------------------------ controls
def _write(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def _sub(root, rel, pattern, repl, missing, count=0):
    text = read(root, rel)
    # re.M: the line-anchored controls are patterns for ONE line of a
    # script, not for the whole file's start and end.
    new, hits = re.subn(pattern, repl, text, count=count, flags=re.M)
    if hits == 0:
        raise CannotRun("control cannot mutate %s: %s (%s)" % (rel, missing, pattern))
    _write(root, rel, new)


def _insert_after_line_containing(root, rel, needle, added, missing):
    text = read(root, rel)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if needle in line:
            lines.insert(index + 1, added)
            _write(root, rel, "\n".join(lines) + "\n")
            return
    raise CannotRun("control cannot find %r in %s (%s)" % (needle, rel, missing))


def _sub_line(root, rel, line_prefix, old, new, missing):
    """Replace `old` with `new` on the FIRST line starting with `line_prefix`.

    Whole-line addressing, not a cross-line regex: the extractor line contains a
    `)` (its own grep alternation), which no `[^)]*` scan can step over.
    """
    text = read(root, rel)
    lines = text.splitlines(True)
    for index, line in enumerate(lines):
        if line.startswith(line_prefix) and old in line:
            lines[index] = line.replace(old, new, 1)
            _write(root, rel, "".join(lines))
            return
    raise CannotRun("control cannot find %r on a %r line in %s (%s)"
                    % (old, line_prefix, rel, missing))


def build_green(root):
    """The two Lead-owned repairs, reconstructed on a COPY.

    Not a patch: a pinned patch stops applying the moment the block is re-indented
    (docs/session-loop-fix.patch is the cautionary precedent — it silently killed
    eight controls when eaf34bd extracted the heredoc).
    """
    segment = read(root, SEGMENT_REL)
    # The shipped guard fires only in the no-verdict case, so the green baseline
    # adds the other half: a stamp that does not read the verdict token at all.
    if PROVENANCE_STAMP not in segment:
        stamp = ('  # green-baseline provenance stamp: a substituted reviewer brain is '
                 'recorded\n'
                 '  # whether or not a verdict token came out of it\n'
                 '  %s=clean\n'
                 '  grep -qE \'%s\' "$PWD/%s" 2>/dev/null && %s=substituted\n'
                 '  echo "review_provenance=${%s}" >> "$GITHUB_OUTPUT"'
                 % (PROVENANCE_STAMP, SUBSTITUTION_MARKER, REVIEW_FILE,
                    PROVENANCE_STAMP, PROVENANCE_STAMP))
        _insert_after_line_containing(root, SEGMENT_REL,
                                      'echo "review verdict for', stamp,
                                      "no review-verdict report line to stamp after")
    ignore = read(root, GITIGNORE_REL)
    held = [l.strip() for l in ignore.splitlines()]
    add = [n for n in SCRATCH_NAMES if n not in held]
    if add:
        _write(root, GITIGNORE_REL, ignore.rstrip("\n") + "\n" + "\n".join(add) + "\n")


CONTROLS = [
    # (name, mutation, expected rc, expected text, build green baseline first).
        ("green-baseline", lambda root: None, 0, "REVIEW-VERDICT CHECK OK", True),
        ("brief-last-line-law", lambda root: _sub(
            root, SEGMENT_REL, re.escape(LAST_LINE_LAW) + r".*", "print the verdict somehow",
            "last-line law gone"), 1, "brief-token", True),
        ("brief-token-re spelled", lambda root: _sub(
            root, SEGMENT_REL, r"VERDICT: REJECTED", "VERDICT: REFUSED",
            "instructed token"), 1, "brief-token", True),
        ("extractor-alt-narrowed", lambda root: _sub(
            root, SEGMENT_REL, r"\(APPROVED\|REJECTED\)", "(APPROVED)",
            "extractor alternation"), 1, "extractor-agrees", True),
        ("extractor-no-tail", lambda root: _sub_line(
            root, SEGMENT_REL, "REVIEW_VERDICT=$(", "tail -1", "cat",
            "tail -1"), 1, "extractor-agrees", True),
        ("extractor-wrong-file", lambda root: _sub_line(
            root, SEGMENT_REL, "REVIEW_VERDICT=$(", REVIEW_FILE, ".turn-other.txt",
            "verdict file operand"), 1, "extractor-agrees", True),
        ("lane-dropped", lambda root: _sub(
            root, SEGMENT_REL, r"[ \t]*visiting-engineer\)\n", "",
            "visiting lane label"), 1, "lane-coverage", True),
        # Owner rotation 2026-10-25 rewired the QA lane: goose/groq is the
        # PRIMARY brief carrier (via `-t "$REVIEW_BRIEF"`) and the demoted qoder
        # call survives as the else-arm fallback. The pre-rotation `lane-unbriefed`
        # control mutated the then-primary qoder line and stayed GREEN — the goose
        # carrier kept the lane briefed, so the leg it was supposed to prove had
        # no live firing. Three firings now, one per shape that loses a briefed
        # reviewer: the `-t` primary unbriefed, the fallback arm deleted outright
        # (the rotation's recovery path is gone), the fallback re-invoking without
        # the brief (a demoted brain answers a prompt that never saw the law).
        ("lane-unbriefed", lambda root: _sub(
            root, SEGMENT_REL, r'-t "\$REVIEW_BRIEF"', '-t "say something"',
            "goose review lane brief"), 1, "lane-coverage", True),
        ("lane-fallback-gone", lambda root: _sub(
            root, SEGMENT_REL,
            r'[ \t]*else\n[ \t]*echo "REVIEW: groq lane failed[^\n]*\n(?:[ \t]+[^\n]*\n)*?[ \t]*fi ;;',
            '      echo "REVIEW: groq lane failed, no fallback" ;;',
            "QA lane fallback block"), 1, "lane-coverage", True),
        ("lane-fallback-unbriefed", lambda root: _sub(
            root, SEGMENT_REL, r'qoder -p "\$REVIEW_BRIEF"', 'qoder -p "say something"',
            "QA lane fallback brief"), 1, "lane-coverage", True),
        ("member-id-drift", lambda root: _sub(
            root, WORKFLOW_REL, r'QA_MEMBER="[^"]*"', 'QA_MEMBER="other@qoder"',
            "workflow QA_MEMBER"), 1, "reviewer-ids", True),
        ("author-seat-key-gone", lambda root: _sub(
            root, WORKFLOW_REL, r'"\$\{PENDING_AUTHOR:-x\}" = "quality-assurance-engineer"',
            '"${PENDING_AUTHOR:-x}" = "someone-else"', "author seat key"), 1,
            "reviewer-ids", True),
        ("guard-removed", lambda root: _sub(
            root, SEGMENT_REL, r"[ \t]*grep -qE '[^']*not available right now[^\n]*\n", "",
            "injected guard"), 1, "lane-guard", True),
        ("scratch-unignored", lambda root: _sub(
            root, GITIGNORE_REL, r"\n\.turn-review\.txt", "", "gitignored verdict file"),
            1, "scratch-ignored", True),
        # The refusal path must fire too: an unreadable contract is CANNOT RUN,
        # never a quieter green.
        ("brief-block-vanished", lambda root: _sub(
            root, SEGMENT_REL, r'^REVIEW_BRIEF=""$', "BRIEF_REMOVED=",
            "REVIEW_BRIEF initialiser"), 2, "CANNOT RUN", True),
    ]


def selftest(root):
    script = os.path.abspath(__file__)
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d entries but this harness pins %d — "
                        "a deleted control is not a shorter SELFTEST OK"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    failures = []
    for name, mutation, expected_rc, expected_text, green_base in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="review-verdict-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                          ".pytest_cache", ".git",
                                                          ".sessions-restore", "dist",
                                                          "build"))
            if green_base:
                build_green(target)
            mutation(target)
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-24s -> rc %d as expected (%s)"
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
                        help="mutate copies and prove every leg can fail")
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
