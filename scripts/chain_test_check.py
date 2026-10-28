#!/usr/bin/env python3
"""Re-runnable check of the TEST-CHAIN objective's landed evidence.

WHY this exists (measured, not assumed). The Owner ordered a 3-turn
machinery test on 2026-10-22 09:22Z (TEST-T1 check-in, TEST-T2 one
harness improvement, TEST-T3 board/chat verification). Each turn left a
PROSE record: a chat entry and a line in docs/CHAIN-TEST.md. Prose is not
re-runnable. The Lead's next move is to flip #+OBJECTIVE-STATE in
agent-team/CONTROL.org and restore the parked feature order, and the
evidence that move rests on was, until now, readable only by trusting a
seat's own summary — the exact shape this repo's harness laws keep
forbidding (EIGHTH: a GATE that lives as prose is a check nobody can
re-run).

So this harness grades the objective's claims against the tree, the way the
other six harnesses grade their pairs:

  TURNS        the three scripted turns each landed as a commit whose
               subject names the turn, and every one of them is an ancestor
               of the main ref (a turn that exists only on a side branch
               never reached the trunk is not a landed turn).
  CHAT-TURN    each turn left a chat entry carrying its marker.
  CHAT-FORMAT  EVERY message in the chat carries the FROM in its headline
               and a complete :PROPERTIES: drawer (:FROM: :TO: :KIND:
               :WHEN: :END:) — the FORMAT LAW, graded over the whole file
               and not over the handful of entries a reader happens to
               scroll to.
  CHAT-STRUCTURE  every drawer line in the file is OWNED by a `* MSG`
               headline. A message whose header vanished is invisible to
               CHAT-FORMAT (it grades parsed entries, and an orphan drawer
               parses as the PREVIOUS entry's body), so the fold shape
               below needs its own scan.
  APPEND-ONLY  in the objective's own window (the commit that switched
               the chain to TEST-CHAIN and everything after it), every entry
               every historical version of the chat held is still THERE, in
               the same order, with the same bytes: no entry was edited, no
               entry was dropped, none moved. Graded PER ENTRY, because the
               whole-file byte-prefix read called a union-merged concurrent
               append — where every entry is intact — a violation, and on
               ai/main that made the leg permanently red (115 lines) so a
               reviewer could not use its verdict at all.
  NO-DROP      over the WHOLE history, the sequence of entry identities
               (routing + date + time, day name aside) never loses a member
               and never reorders one. A body region that changed BEFORE the
               objective's window is a note naming the entry, not a red — the
               Lead's own file-rename propagation reworded two historical
               bodies on 2026-10-21. A change INSIDE the window is red unless
               it is a repair pinned in ACCEPTED_REPAIRS with the line that
               records the ruling.
  LOG          docs/CHAIN-TEST.md holds one well-formed run line per turn
               (`sha@branch | seat | lane | date [| note]`), every run id
               resolves to a real commit, each turn's line carries that
               turn's marker AND the same date as its chat entry, and the
               log ends with the closed 3-line summary.
  LOG-COVERAGE every run-shaped line in the log is one the harness READS:
               inside a `runs` section, or re-listed in one, or a pinned
               superseded record. A line that fell outside the region is a
               turn silently missing from the evidence — this log admits in
               its own prose that two cycles' lines dropped below the fold,
               and nothing graded that claim until now.
  BOARD        every parked feature item is still a headline on
               agent-team/TODOS.org: the Lead restores an ORDER, and an
               order cannot be restored over a deleted item.

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its own input — never a
false red for a tree it has not measured).

Controls run against copies via --root, so the shipped tree is only read:
  cp -r . /tmp/x && python3 scripts/chain_test_check.py --root /tmp/x

And the harness proves it can FAIL, against a copy, with no hand-holding:
  python3 scripts/chain_test_check.py --selftest

It is deliberately NOT named `*_diff.py`: that glob is the landing gate's
twin roster (scripts/landing_gate.py: EXPECTED_TWINS), and a harness that
is not in that roster is not a twin. This one grades the CHAIN, not a pair
of artifacts, so it stands beside the gate and is run by hand — but it is
also the FIRST harness in this repo whose verdict a reader can reproduce
with one command and no setup.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ------------------------------------------------------------ pinned inputs
# These are the PROMISE, not the disk: they are what the objective said it
# would do, and the tree is measured against them. A harness that derives
# its expectations from the tree it grades proves nothing.
TURNS = ("T1", "T2", "T3")
EXPECTED_TURNS = 3

# The note phrases each turn's run line carries in the delivered log. A
# reworded log line must edit THIS table — a visible, deliberate change,
# instead of a silent drift that turns the check into a no-op.
LOG_MARKERS = {
    "T1": ("TEST-T1",),
    "T2": ("TEST-T2", "improvement:"),
    "T3": ("TEST-T3",),
}

MAIN_REF = "ai/main"
CHAT_REL = "agent-team/CHAT.org"
LOG_REL = "docs/CHAIN-TEST.md"
BOARD_REL = "agent-team/TODOS.org"
CONTROL_REL = "agent-team/CONTROL.org"

# The parked feature order the Lead restores after the test. Every fragment
# must still be a headline on the board: an order cannot be restored over a
# deleted item.
BOARD_ITEMS = (
    "FR R-001 lifecycle state machine",
    "FR-R001-FE",
    "FR R-003 custom actions + audit",
    "FR-R003-FE",
    "FR R-002 document independent-enum pattern",
    "FR R-004 kanban view",
    "FR R-005 canonical CSV export",
    "FR R-006 page registration",
    "FR R-008 widget data sources + new charts",
    "FR-R007-LIVE",
    "FR R-007 RBAC phased",
    # Owner 2026-10-23 17:37Z "Remove the cool naming": the three DONE
    # chat items were renamed on the board (history keeps the old IDs).
    "CHAT-PREVIEW",
    "verify-chat-2",
    "CHAT-SEND-BACK-2",
)
EXPECTED_BOARD_ITEMS = 14

# Floors (the chat and the board only GROW, so an exact count would rot
# every turn; the floors are the population promise: the evidence this
# harness grades must still be THERE).
CHAT_MESSAGE_FLOOR = 50
LOG_RUN_LINE_FLOOR = 3
LOG_SUMMARY_LINE_FLOOR = 3

# A run record the harness cannot READ is coverage lost, not coverage printed:
# parse_log grades only a section named exactly `runs`, and this log admits in
# its own words that it had to RE-OPEN that region twice — the second cycle's
# `## runs` block ("the first cycle's `runs` block was closed by the FIRST
# cycle's T3, so the second cycle's T1/T2 lines fell below the fold") and the
# third cycle's ("the second cycle's `## runs` block was closed by that cycle's
# own T3"). Meanwhile the file still carries a run-shaped record under
# `## Post-chain handoff`, which no leg reads: a line the harness does not read
# costs the log nothing to print, so `LOG: N run line(s)` keeps looking complete
# while a turn vanishes from the evidence — the shape the ELEVENTH law forbids
# (a comparison blind to its own coverage, the same hole that let five CSV
# sentinels and a FLOAT_PARITY row disappear while still printing "identical").
#
# SUPERSEDED_RUN_LINES is the accepted-divergence pin, the same shape the CSV
# twins use for a row whose divergence is recorded on purpose: a line the log
# keeps (the append-only law forbids deleting it) that is deliberately NOT
# re-listed into the graded region. Pinned by `sha@branch` IDENTITY, never by
# line number — numbers move with every edit, which is the trap this repo
# already fell into once (the brand twin's positional read compared the shipped
# brand.json against an unrelated brand and invented a re-theme flicker).
SUPERSEDED_RUN_LINES = (
    # The second cycle's own correction, in its own words (docs/CHAIN-TEST.md
    # TEST-T1 re-list line): "the 11:24Z line at :39 quoted f1678cd, the v0.1.0
    # release tag's commit — corrected here". The corrected record IS graded;
    # this line stays as the visible mistake, in the prose region it was
    # written into.
    "f1678cd@ai/turn-20261022-1124",
)

# A LANDED entry may never be edited (append-only law) — except a correction
# the FORMAT LAW itself demands and a seat is forbidden to make, which the
# Lead then applies to the entry. Such a repair is legal exactly when it is
# RECORDED and VISIBLE, so it lives here as a pinned row instead of joining
# the "accepted noise" pile the byte-prefix legs used to print: the entry it
# names, the line the repair wrote, and the defective line(s) it replaced —
# matched by bytes, so an edit of any OTHER shape stays red.
# (identity stamp, corrected line, accepted predecessor(s), where the ruling is recorded)
ACCEPTED_REPAIRS = (
    (("platform-engineer", "lead", "report", "2026-10-22 11:24"),
     ":WHEN: [2026-10-22 Thu 11:24 UTC]",
     (":WHEN: 2026-10-22 Wed 11:24 UTC",
      ":WHEN: [2026-10-22 Wed 11:24 UTC]"),
     "agent-team/CHAT.org:6391 — the defect is reported there and left in place "
     "because 'only the Lead can correct the entry'; 2026-10-22 is a Thursday, so the "
     "correction is the day name (the brackets came with the same repair pass)"),
)
EXPECTED_ACCEPTED_REPAIRS = 1

# Multi-line in-window rewrites (the "rewritten" class: more than one line of an
# entry's region differs from a landed version) cannot match a one-line
# ACCEPTED_REPAIRS row by construction — but the law text above says a repair
# "pinned in ACCEPTED_REPAIRS with the line that records the ruling" is legal,
# and the Lead's own restructure rulings ARE recorded repairs of exactly this
# class. REWRITTEN_BASELINES completes that design: the identity it names plus
# the byte-anchored marker of the chat line that records the ruling. The marker
# is verified against the CURRENT chat on every run, so deleting the ruling
# re-opens the red — a disposition without its visible ruling is a permit, and
# a dead row raises CannotRun in every plain run (stronger than a selftest
# control; no extra control is owed and the 18-control roster stands).
# (identity stamp, ruling-line byte marker)
REWRITTEN_BASELINES = (
    (("software-engineer", "lead", "report", "2026-10-24 22:05"),
     "SECOND UNION-REPAIR RULING (chat-law restructure, union with 0015)"),
    (("software-engineer", "lead", "report", "2026-10-26 15:45"),
     "THIRD UNION-REPAIR RULING (chat cross-entry body fold, union 54d0d0c)"),
    (("software-engineer", "lead", "correction", "2026-10-26 15:52"),
     "THIRD UNION-REPAIR RULING (chat cross-entry body fold, union 54d0d0c)"),
    (("platform-engineer", "lead", "report", "2026-10-26 16:21"),
     "THIRD UNION-REPAIR RULING (chat cross-entry body fold, union 54d0d0c)"),
)
EXPECTED_REWRITTEN_BASELINES = 4

# ------------------------------------------------------------- file shapes
HEADLINE_RE = re.compile(
    # KIND/MKIND admit hyphens (e.g. :hiring-consult: — the 13:35Z Lead
    # entry was legal in spirit; QA + relief flagged the red 2026-10-22).
    r"^\* MSG (?P<from>.+?) -> @(?P<to>\S+) :(?P<kind>[\w-]+):"
    r"\s+:msg:(?P<mfrom>[^:]+):(?P<mto>[^:]+):(?P<mkind>[\w-]+):\s*$"
)
RUN_LINE_RE = re.compile(
    r"^(?P<sha>[0-9a-f]{7,40})@(?P<branch>\S+)"
    r" \| (?P<seat>[^|]+?) \| (?P<lane>[^|]+?) \| (?P<date>\d{4}-\d{2}-\d{2})"
    r"(?: \| (?P<note>.*))?$"
)
# A line that STARTS like a run line (`<hex-sha>@`) is INTENDED to be one; if
# it does not match the full shape it is a malformed run line, not prose.
# The log's header prose ("One line per turn: run id | seat | lane | date.")
# does not start like a run line, so it is prose and stays prose.
RUN_LINE_INTENT_RE = re.compile(r"^[0-9a-f]{4,40}@")
# The COVERAGE scan's intent: same shape, any column. A run record an author
# indents is just as invisible to parse_log (which requires column 0) as one
# that fell outside the `runs` region, and it silently lowers the graded count
# instead of raising a red. Measured on the delivered log: ZERO indented
# run-shaped lines, so the tolerance buys the blind spot at no false positive.
RUN_LINE_LOOSE_RE = re.compile(r"^[ \t]*(?P<id>[0-9a-f]{4,40}@\S+)")
WHEN_RE = re.compile(r"^\[?(?P<date>\d{4}-\d{2}-\d{2})")
DRAWER_KEYS = ("FROM", "TO", "KIND", "WHEN")
HEADLINE_LINE = re.compile(r"^\* MSG ")
# A drawer FIELD line is a line whose first column is `:` followed by an
# uppercase key (`:PROPERTIES:`, `:FROM: …`, `:END:`). Every body line the
# FORMAT LAW writes is INDENTED by two spaces, so column-0 is what makes a
# drawer line a drawer line — and what makes one outside a drawer region an
# orphan. The key must ALSO satisfy the field grammar — `:KEY:` alone, or
# `:KEY:` + whitespace + value — because a BODY line can legally quote the
# drawer order at column 0: run 40113340018 REJECTED the clean housekeeping
# branch ai/turn-20261024-1632 on exactly that (a relief seat's TEST-T2 line
# reporting the fold hazard, `:PROPERTIES:, :WHEN:, :FROM:, …`, was reported
# AS a fold — the prefix read matched `:PROPERTIES:` and stopped). After that
# `:KEY:` comes a COMMA, and a comma is neither end-of-line nor whitespace,
# so the grammar read excludes the prose while every real field still
# matches. The key itself is group(1) — report sites print it, not the
# whole match (the value's first character is not part of the field).
DRAWER_FIELD_RE = re.compile(r"^(:[A-Z][A-Z0-9_-]*:)(\s*$|\s+\S)")


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


def git(root, *args):
    out = subprocess.run(("git",) + args, cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        raise CannotRun("git %s failed: %s" % (" ".join(args), out.stderr.strip()[:200]))
    return out.stdout


def read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CannotRun("cannot read %s: %s" % (rel, exc))


# ------------------------------------------------------------------- chat
def parse_messages(text):
    """Split the chat into messages.

    A message is a `* MSG ...` headline, its :PROPERTIES: drawer (ending
    at :END:), and its body. The identity of a message is its ROUTING
    (from/to/kind) plus its timestamp — the part the FORMAT LAW fixes —
    so a body can be reworded without the entry ever ceasing to exist.
    """
    lines = text.splitlines()
    messages = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if not HEADLINE_LINE.match(line):
            idx += 1
            continue
        start = idx
        head = HEADLINE_RE.match(line)
        drawer = {}
        cursor = idx + 1
        ended = False
        body = []
        while cursor < len(lines):
            cur = lines[cursor]
            if HEADLINE_LINE.match(cur):
                break
            if cur.startswith(":") and not cur.startswith(":PROPERTIES:"):
                key = cur[1:].split(":", 1)[0].strip()
                # split(":", 2) and NOT split(":", 1): a drawer VALUE carries
                # colons of its own (`:WHEN: [2026-10-22 Thu 18:58 UTC]`), and
                # splitting once leaves the key glued to the value, so every
                # value read back as "WHEN: [2026-10-22 Thu 18".
                parts = cur.split(":", 2)
                drawer[key] = parts[2].strip() if len(parts) > 2 else ""
            if cur.startswith(":END:"):
                ended = True
                cursor += 1
                break
            cursor += 1
        while cursor < len(lines) and not HEADLINE_LINE.match(lines[cursor]):
            body.append(lines[cursor])
            cursor += 1
        identity = None
        if head:
            identity = (head.group("mfrom"), head.group("mto"), head.group("mkind"),
                        drawer.get("WHEN", ""))
        messages.append({
            "line": start + 1,
            "headline": line,
            "head_ok": head is not None,
            "drawer": drawer,
            "ended": ended,
            "identity": identity,
            "body": "\n".join(body).strip("\n"),
        })
        idx = cursor
    return messages


# ------------------------------------------------- entry-granularity history
# The law this harness first shipped with compared the WHOLE file at every
# commit to the whole file today. That proxy cannot tell a violation from a
# legitimate history event, and on ai/main it printed 115 red lines (58
# APPEND-ONLY + 57 NO-DROP) for THREE explained classes — measured
# 2026-10-25 over the 138 commits that touched the chat, 12,399 entry
# comparisons, 0 order breaks, 1 identity ever moved:
#   CONCURRENT APPENDS: two branches append at EOF, the merge interleaves
#     them, and an older commit stops being a prefix although every entry is
#     intact. Never a violation of "no entry edited or dropped" — reported
#     as one, every time, for every merged pair.
#   FOLD REPAIRS: an entry that had swallowed a folded sibling's drawer tail
#     and was later split back apart by the Lead's re-head repair; the
#     historical block's bytes no longer exist because the region was
#     subdivided, not because anything was rewritten.
#   ONE PINNED REPAIR: an entry's :WHEN: day name, corrected by the Lead
#     because a seat may not touch a landed entry (ACCEPTED_REPAIRS).
# So the claim is now measured WHERE IT IS ACTUALLY MADE — per entry. An
# entry is matched by identity and only three things are violations: an entry
# that vanished, an entry that moved behind a younger one, an entry whose
# bytes changed after it landed. Each red names the entry, its line and the
# bytes, instead of naming a commit and shrugging.
WHEN_STAMP_RE = re.compile(
    r"\[?\s*(?P<date>\d{4}-\d{2}-\d{2})(?:\s+[A-Za-z]+)?(?:\s+(?P<time>\d{2}:\d{2}))?")


def when_stamp(value):
    """The timestamp an entry is IDENTIFIED by: date and time, no day name.

    The day name is exactly what a recorded repair moves (2026-10-22 was
    written `Wed`; it is a Thursday). Dropping it from the identity keeps
    that entry the SAME entry across the repair, so the harness grades the
    byte change as an edit — which is what it is — rather than as one entry
    dropped and a second one added.
    """
    match = WHEN_STAMP_RE.search(value or "")
    if not match or not match.group("date"):
        return (value or "").strip()
    stamp = match.group("date")
    if match.group("time"):
        stamp += " " + match.group("time")
    return stamp


def entry_records(text):
    """Every parsed entry, with the EXACT bytes of its region.

    A region is the headline line through the line before the next headline,
    trailing blank lines off. A folded entry's tail therefore rides inside
    the swallowing entry's region — which is what a fold repair later moves,
    and what classify_edit() recognises instead of calling it an edit.
    """
    messages = [m for m in parse_messages(text) if m["identity"]]
    lines = text.splitlines()
    starts = sorted({m["line"] - 1 for m in messages})
    if len(starts) != len(messages):
        raise CannotRun("two chat entries report the same headline line — the parser "
                        "disagrees with itself over %s, so no per-entry claim can be made"
                        % CHAT_REL)
    records = []
    for index, message in enumerate(messages):
        start = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = lines[start:end]
        while block and block[-1].strip() == "":
            block.pop()
        frm, to, kind, when = message["identity"]
        records.append({
            "identity": (frm, to, kind, when_stamp(when)),
            "raw_when": when,
            "line": message["line"],
            "block": "\n".join(block),
        })
    return records


def align_entries(old_records, cur_records):
    """Match an older version's entries onto today's, IN ORDER.

    Greedy forward scan: each historical entry must be found at or after the
    cursor, which is what "the file only ever grew at the end, entry by entry"
    means once concurrent appends can interleave. An identity that exists only
    BEHIND the cursor did not vanish — it moved, which the append-only law
    forbids just as hard.
    """
    positions = {}
    for position, record in enumerate(cur_records):
        positions.setdefault(record["identity"], []).append(position)
    matched, dropped, reordered = [], [], []
    cursor = 0
    for record in old_records:
        found = next((p for p in positions.get(record["identity"], ()) if p >= cursor), None)
        if found is None:
            (reordered if record["identity"] in positions else dropped).append(record)
            continue
        matched.append((record, cur_records[found]))
        cursor = found + 1
    return matched, dropped, reordered


def classify_edit(old_block, cur_block, cur_stamps):
    """Name WHAT CHANGED between an entry's historical bytes and its own bytes.

    ('fold-split', tail)  the region shrank by a tail that today belongs to a
                          headed entry — the fold repair, not a rewrite. The
                          tail's own :WHEN: must resolve to a live entry, or
                          this is not a split and does not get the name.
    ('one-line', (o, n))  exactly one line differs, same region length.
    ('body', None)        anything else: a rewritten entry.
    """
    if cur_block and old_block.startswith(cur_block):
        tail = old_block[len(cur_block):].strip("\n")
        if tail:
            stamp = next((when_stamp(line.split(":", 2)[2])
                          for line in tail.splitlines() if line.startswith(":WHEN:")), None)
            if stamp and stamp in cur_stamps:
                return "fold-split", tail
    old_lines, cur_lines = old_block.splitlines(), cur_block.splitlines()
    if len(old_lines) == len(cur_lines):
        diff = [(o, n) for o, n in zip(old_lines, cur_lines) if o != n]
        if len(diff) == 1:
            return "one-line", diff[0]
    return "body", None


def audit_version(root, sha, cur_text, cur_records, cur_stamps):
    """Everything that happened to the chat between one commit and today."""
    old_text = git(root, "show", "%s:%s" % (sha, CHAT_REL))
    old_records = entry_records(old_text)
    matched, dropped, reordered = align_entries(old_records, cur_records)
    edits = []
    for old, cur in matched:
        if old["block"] == cur["block"]:
            continue
        kind, payload = classify_edit(old["block"], cur["block"], cur_stamps)
        edits.append({"kind": kind, "payload": payload, "old": old, "cur": cur})
    return {"sha": sha, "dropped": dropped, "reordered": reordered, "edits": edits,
            "entries": len(old_records), "prefix": cur_text.startswith(old_text)}


def scan_orphan_drawers(text):
    """Every column-0 drawer field line, split into OWNED and ORPHAN.

    OWNED = it sits between a `* MSG` headline and that entry's `:END:`.
    ORPHAN = it sits anywhere else: the file's preamble, or an entry's body
    region. A body region never legitimately holds one, because the FORMAT
    LAW indents every body line — so an orphan is an entry whose headline
    and drawer HEADER were eaten while its `:WHEN:` / `:END:` tail survived.

    That is not hypothetical, it is the shape a MERGE FOLD leaves behind:
    two branches append at EOF, the appended blocks begin with identical
    header lines (`* MSG platform-engineer -> @lead :report:` + the four
    drawer keys), and the three-way merge reads those identical lines as
    COMMON CONTEXT and folds them, so one header ends up serving two
    bodies. Measured on ai/main: the merge 3b121ee of ai/turn-20261024-0809
    took the branch's 81 appended lines and dropped 5 of them — the
    headline, `:PROPERTIES:`, `:FROM:`, `:TO:`, `:KIND:` — which is why
    agent-team/CHAT.org:7731 opens with a bare `:WHEN:`. The same
    fold hit 4598a81 at :6407. CHAT-FORMAT cannot see either one (the orphan
    parses as the previous entry's body), and APPEND-ONLY / NO-DROP do fire
    on those merges but report only "not a prefix" — never WHICH message
    lost its headline, and both are already red under the Lead's
    merge-as-prefix ruling. So nothing named the two entries whose FROM is
    gone until this leg did.

    Returns (orphans, owned) — ([(line_number, text, owner_line)], count).
    """
    orphans = []
    owned = 0
    state = "preamble"
    owner = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if HEADLINE_LINE.match(line):
            state = "drawer"
            owner = number
            continue
        if state == "drawer":
            if DRAWER_FIELD_RE.match(line):
                owned += 1
            if line.startswith(":END:"):
                state = "body"
            continue
        if DRAWER_FIELD_RE.match(line):
            orphans.append((number, line, owner))
    return orphans, owned


# -------------------------------------------------------------------- log
def parse_log(text):
    """Split docs/CHAIN-TEST.md into its run lines and its prose sections."""
    lines = text.splitlines()
    run_lines = []
    summary = []
    section = "runs"
    for number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section == "runs":
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            if RUN_LINE_INTENT_RE.match(line):
                run_lines.append((number, line))
        elif section.startswith("Summary"):
            if line.strip():
                summary.append((number, line))
    return run_lines, summary


def loose_run_id(line):
    """`sha@branch` for anything shaped like a run record, else None — the ONE
    identity spelling the coverage scan and its controls compare on."""
    match = RUN_LINE_LOOSE_RE.match(line)
    return match.group("id") if match else None


def scan_run_line_coverage(text, graded):
    """Split every run-shaped line in the log into what the harness can see.

    `graded` is the (line_number, text) set parse_log returned — the ONLY region
    this harness reads. Anything else shaped like a run record is:
      duplicate   — the same `sha@branch` is also graded, i.e. the log re-listed
                    the turn in a fresh `## runs` block (the established
                    append-only repair; the original stays where it fell);
      superseded  — one of the pinned accepted-divergence records;
      stranded    — a turn the evidence loses WITHOUT SAYING SO. That is the red.

    Returns (stranded, duplicates, superseded, seen_ids, graded_count).
    """
    graded_numbers = set()
    graded_ids = set()
    for number, line in graded:
        graded_numbers.add(number)
        # One identity spelling for both sides of the compare: loose_run_id, so
        # a malformed-but-intended line cannot be its own twin. A line parse_log
        # graded but RUN_LINE_RE rejects is already RED above; here it simply
        # contributes no id, which is the honest reading.
        ident = loose_run_id(line)
        if ident is not None:
            graded_ids.add(ident)
    stranded = []
    duplicates = []
    superseded = []
    seen_ids = set(graded_ids)
    section = "runs"
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        ident = loose_run_id(line)
        if ident is None:
            continue
        seen_ids.add(ident)
        if number in graded_numbers:
            continue
        if ident in graded_ids:
            duplicates.append((number, ident, section))
        elif ident in SUPERSEDED_RUN_LINES:
            superseded.append((number, ident, section))
        else:
            stranded.append((number, ident, section))
    return stranded, duplicates, superseded, seen_ids, len(graded)


# ------------------------------------------------------------------ board
def board_headlines(text):
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("*") and stripped.lstrip("*").startswith(" "):
            out.append((number, stripped))
    return out


# ------------------------------------------------------------------- main
def main(argv):
    parser = argparse.ArgumentParser(description="grade the TEST-CHAIN objective's landed evidence")
    parser.add_argument("--root", default=None,
                        help="run against another tree (control); default: this repo")
    parser.add_argument("--main", default=MAIN_REF, help="the ref the turns must have landed on")
    parser.add_argument("--selftest", action="store_true",
                        help="prove every leg can fail, against copies of this tree")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root) if args.root else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.selftest:
        return selftest(root)

    if len(TURNS) != EXPECTED_TURNS:
        raise CannotRun("TURNS lists %d turn(s), EXPECTED_TURNS pins %d — the harness "
                        "does not understand its own promise" % (len(TURNS), EXPECTED_TURNS))
    if len(BOARD_ITEMS) != EXPECTED_BOARD_ITEMS:
        raise CannotRun("BOARD_ITEMS lists %d item(s), EXPECTED_BOARD_ITEMS pins %d — "
                        "the harness does not understand its own promise"
                        % (len(BOARD_ITEMS), EXPECTED_BOARD_ITEMS))

    problems = []
    notes = []

    chat_text = read(root, CHAT_REL)
    log_text = read(root, LOG_REL)
    board_text = read(root, BOARD_REL)
    control_text = read(root, CONTROL_REL)

    messages = parse_messages(chat_text)
    if len(messages) < CHAT_MESSAGE_FLOOR:
        problems.append("POPULATION chat: %d message(s), floor is %d — the evidence this "
                        "harness grades is no longer there" % (len(messages), CHAT_MESSAGE_FLOOR))
    if not messages:
        raise CannotRun("agent-team/CHAT.org holds no `* MSG` entry — there is no chat "
                        "to grade (a rename or a wipe is not a failure of the objective)")

    orphans, owned_fields = scan_orphan_drawers(chat_text)
    if owned_fields == 0:
        raise CannotRun("the drawer scan matched no field line inside any entry region "
                        "(pattern %r over %d entry(ies)) — CHAT-STRUCTURE grades nothing "
                        "on this file, so a clean answer here would be meaningless"
                        % (DRAWER_FIELD_RE.pattern, len(messages)))

    # ---- 1. TURNS: a landed commit per scripted turn
    subjects = {}
    for line in git(root, "log", "--format=%H%x09%s").splitlines():
        sha, _, subject = line.partition("\t")
        subjects[sha] = subject
    for turn in TURNS:
        marker = "TEST-%s" % turn
        candidates = [sha for sha, subject in subjects.items() if marker in subject]
        if not candidates:
            problems.append("TURN %s: no commit anywhere in the history names %s — the "
                            "scripted turn never landed" % (turn, marker))
            continue
        landed = []
        for sha in candidates:
            if subprocess.run(("git", "merge-base", "--is-ancestor", sha, args.main),
                              cwd=root, capture_output=True).returncode == 0:
                landed.append(sha)
        if not landed:
            problems.append("TURN %s: %d commit(s) name %s but none is an ancestor of %s — "
                            "the turn exists only on a side branch"
                            % (turn, len(candidates), marker, args.main))
        else:
            notes.append("TURN %s: %d commit(s) name %s, %d landed on %s (newest %s)"
                         % (turn, len(candidates), marker, len(landed), args.main, landed[0][:8]))

    # ---- 2. CHAT-TURN: a chat entry per scripted turn
    turn_dates = {}
    for turn in TURNS:
        marker = "TEST-%s" % turn
        hits = [m for m in messages if marker in m["body"]]
        if not hits:
            problems.append("CHAT-TURN %s: no chat entry mentions %s — the turn left no "
                            "record in the single chat buffer" % (turn, marker))
            continue
        dates = set()
        for hit in hits:
            when = hit["drawer"].get("WHEN", "")
            match = WHEN_RE.match(when)
            if match:
                # group(1), not group(0): the FORMAT LAW writes an Org INACTIVE
                # timestamp `[YYYY-MM-DD Eee HH:MM UTC]`, and the bracket is not
                # part of the date the log line carries.
                dates.add(match.group("date"))
        turn_dates[turn] = dates
        notes.append("CHAT-TURN %s: %d entr(y/ies) carry %s (line %s)"
                     % (turn, len(hits), marker, ", ".join(str(h["line"]) for h in hits[:4])))

    # The DATE cross-check below compares each turn's log date against its chat
    # entry's — a comparison that cannot see its own coverage. A turn whose chat
    # entries exist but yield NO parseable :WHEN: has nothing to compare, and the
    # leg would silently skip it (that is exactly how the glued-key parse hid it:
    # three cycles answered "OK" with turn_dates permanently empty). So a blind
    # turn is CANNOT RUN, naming the parse — never a silent pass, and never a
    # false red for a missing entry, which leg CHAT-TURN already reports.
    blind = [turn for turn in TURNS if turn in turn_dates and not turn_dates[turn]]
    if messages and blind:
        raise CannotRun("the chat entries carrying %s yield no parseable :WHEN: value (%r) — "
                        "the drawer parse is broken, so the log/chat date cross-check "
                        "compares nothing"
                        % (", ".join("TEST-%s" % t for t in blind), WHEN_RE.pattern))

    # ---- 3. CHAT-FORMAT: the FORMAT LAW over EVERY entry
    for message in messages:
        if not message["head_ok"]:
            problems.append("CHAT-FORMAT line %d: headline does not carry the FROM "
                            "(expected `* MSG <from> -> @<to> :<kind>:  :msg:<from>:<to>:<kind>:`)"
                            % message["line"])
            continue
        missing = [key for key in DRAWER_KEYS if key not in message["drawer"]]
        if missing:
            problems.append("CHAT-FORMAT line %d: drawer is missing %s"
                            % (message["line"], ", ".join(":" + key + ":" for key in missing)))
        if not message["ended"]:
            problems.append("CHAT-FORMAT line %d: the drawer never closes with :END:"
                            % message["line"])

    # ---- 3b. CHAT-STRUCTURE: every drawer line has an owning headline
    # CHAT-FORMAT can only complain about an entry it PARSED. When a merge
    # folds two concurrent EOF appends, the second entry loses its headline
    # and its drawer header, and the surviving `:WHEN:` / `:END:` tail is
    # absorbed into the PREVIOUS entry's body — a shape the parser cannot
    # see and a byte-prefix check does not flag (nothing was deleted from
    # the perspective of the earlier commit). So the orphan scan reads the
    # file structurally instead.
    for number, line, owner in orphans:
        field = DRAWER_FIELD_RE.match(line).group(1)
        problems.append(
            "CHAT-STRUCTURE line %d: drawer field `%s` sits outside any entry "
            "(folded into the message whose headline is at line %d) — an entry lost "
            "its `* MSG` headline and drawer header, so the FORMAT LAW's FROM no "
            "longer travels with this message. Repair = re-insert the five header "
            "lines above it (headline + :PROPERTIES:/:FROM:/:TO:/:KIND:); the body "
            "and timestamp survived intact"
            % (number, field, owner))
    if not orphans:
        notes.append("CHAT-STRUCTURE: %d drawer field(s) inside %d entry region(s), "
                     "0 orphan(s) — every drawer belongs to a headline"
                     % (owned_fields, len(messages)))

    # ---- 4+5. APPEND-ONLY (the objective's own window) and NO-DROP (the
    # whole history), graded PER ENTRY. One pass over the commits that touched
    # the chat; each violating commit is reported under ONE tag — inside the
    # window as APPEND-ONLY, older than it as NO-DROP — because the old pair
    # flagged the same sha twice and the Lead's triage counted 31 refs that way.
    base = objective_base(root, control_text)
    if base is None:
        raise CannotRun("agent-team/CONTROL.org never carried the TEST-CHAIN objective "
                        "(`#+OBJECTIVE: TEST-CHAIN`) — this harness grades THAT objective")
    cur_records = entry_records(chat_text)
    history = git(root, "log", "--format=%H", "--", CHAT_REL).split()
    in_window = set(sha for sha in history
                    if subprocess.run(("git", "merge-base", "--is-ancestor", base, sha),
                                      cwd=root, capture_output=True).returncode == 0)
    cur_by_stamp = {record["identity"][3] for record in cur_records}
    facts = {}
    for sha in history:
        facts[sha] = audit_version(root, sha, chat_text, cur_records, cur_by_stamp)

    # One FACT may survive in several commits' versions (the entry sat
    # unrepaired for 20 commits), and the old legs printed it once per commit —
    # that is how 31 refs became 115 lines. Findings are keyed by what happened
    # to which entry, and the commit list rides along in one line.
    findings = {}
    repairs_exercised = set()
    rewritten_dispositions = set()
    fold_splits, rewords, interleaved = {}, {}, []

    def add_finding(kind, sha, win, identity, line, payload=None):
        key = (kind, identity, line, payload)
        finding = findings.setdefault(key, {"kind": kind, "identity": identity, "line": line,
                                            "payload": payload, "shas": [], "win": False})
        finding["shas"].append(sha)
        finding["win"] = finding["win"] or win

    for sha in history:
        fact = facts[sha]
        win = sha in in_window
        for record in fact["dropped"]:
            add_finding("dropped", sha, win, record["identity"], record["line"])
        for record in fact["reordered"]:
            add_finding("reordered", sha, win, record["identity"], record["line"])
        for edit in fact["edits"]:
            old, cur = edit["old"], edit["cur"]
            if edit["kind"] == "fold-split":
                fold_splits.setdefault(old["line"], set()).add(sha)
                continue
            previous, corrected = (edit["payload"] if edit["kind"] == "one-line"
                                   else (None, None))
            row = next((r for r in ACCEPTED_REPAIRS
                        if edit["kind"] == "one-line" and r[0] == old["identity"]
                        and r[1] == corrected and previous in r[2]), None)
            if row is not None:
                repairs_exercised.add(row[0])
                continue
            if not win:
                rewords.setdefault(cur["line"], set()).add(sha)
                continue
            if edit["kind"] == "one-line":
                add_finding("edited", sha, win, old["identity"], cur["line"],
                            (previous, corrected))
            else:
                disp = next((b for b in REWRITTEN_BASELINES if b[0] == old["identity"]
                             and b[1] in chat_text), None)
                if disp is not None:
                    rewritten_dispositions.add(disp[0])
                    continue
                add_finding("rewritten", sha, win, old["identity"], cur["line"])
        if not fact["prefix"]:
            interleaved.append(sha)

    for finding in sorted(findings.values(),
                          key=lambda f: (f["kind"], f["identity"], f["line"])):
        identity, line, shas = finding["identity"], finding["line"], finding["shas"]
        tag = "APPEND-ONLY" if finding["win"] else "NO-DROP"
        scope = ("inside the objective's window" if finding["win"]
                 else "before the objective's window")
        entry = "`%s -> @%s :%s:` (:WHEN: %s)" % (identity[0], identity[1], identity[2],
                                                  identity[3])
        where = ("line %d" % line) if line else "no line (never in the current file)"
        commits = "%d commit(s): %s" % (len(shas), " ".join(sha[:8] for sha in shas[:6]))
        if finding["kind"] == "dropped":
            problems.append("%s: the entry %s, %s at that commit, is GONE from the current "
                            "file — an entry was dropped %s (%s)"
                            % (tag, entry, where, scope, commits))
        elif finding["kind"] == "reordered":
            problems.append("%s: the entry %s now sits BEHIND an entry that followed it at the "
                            "commit(s) above — an entry was reordered %s (%s)"
                            % (tag, entry, scope, commits))
        elif finding["kind"] == "edited":
            previous, corrected = finding["payload"]
            problems.append("%s: the entry %s at %s was EDITED after it landed — %r -> %r — "
                            "%s (%s). Append-only law: a landed entry is never rewritten; a "
                            "FORMAT-LAW correction is pinned in ACCEPTED_REPAIRS beside the "
                            "line that records the ruling, not applied silently"
                            % (tag, entry, where, previous, corrected, scope, commits))
        else:
            problems.append("%s: the entry %s at %s was REWRITTEN after it landed — more than "
                            "one line of its region differs (%s) — an entry edited in place %s"
                            % (tag, entry, where, commits, scope))

    # The allowance roster is pinned like every other population in this
    # harness: a row that matches nothing in history is not documentation, it
    # is a live permit for the next person who edits that entry.
    if len(ACCEPTED_REPAIRS) != EXPECTED_ACCEPTED_REPAIRS:
        raise CannotRun("ACCEPTED_REPAIRS holds %d row(s), the pin says %d — the roster of "
                        "permitted post-landing edits no longer matches its own promise"
                        % (len(ACCEPTED_REPAIRS), EXPECTED_ACCEPTED_REPAIRS))
    dead = [row for row in ACCEPTED_REPAIRS if row[0] not in repairs_exercised]
    if dead:
        for row in dead:
            print("  DEAD ALLOWANCE %s -> @%s (:WHEN: %s): pinned corrected line %r, accepted "
                  "predecessor(s) %r, cited %s — but no commit differs that way, so the "
                  "allowance no longer records a repair and would permit an edit of that shape"
                  % (row[0][0], row[0][1], row[0][3], row[1], row[2], row[3]))
        raise CannotRun("%d of %d ACCEPTED_REPAIRS row(s) no longer matches any historical byte "
                        "difference — a dead allowance is a permit, not a record (see the DEAD "
                        "ALLOWANCE line(s) above)" % (len(dead), len(ACCEPTED_REPAIRS)))
    if len(REWRITTEN_BASELINES) != EXPECTED_REWRITTEN_BASELINES:
        raise CannotRun("REWRITTEN_BASELINES holds %d row(s), the pin says %d — the roster of "
                        "dispositioned in-window rewrites no longer matches its own promise"
                        % (len(REWRITTEN_BASELINES), EXPECTED_REWRITTEN_BASELINES))
    dead_rw = [b for b in REWRITTEN_BASELINES
               if b[0] not in rewritten_dispositions
               and b[0] not in {k[1] for k in findings if k[0] == "rewritten"}
               and b[0] in {r["identity"] for r in cur_records}]
    # two exemptions keep the refusal honest: (1) the identity's rewrite is
    # ALREADY firing as an undispositioned red — the harness is not silent, it
    # is red, and preempting that red with CANNOT RUN would HIDE a violation
    # (measured: the dropped-entry selftest control deletes the ruling entry,
    # the ruling disappears, and the rewrite must print, not refuse); (2) the
    # identity is GONE from the current file — nothing is left to rewrite, so
    # the row permits nothing and must not preempt the drop red. The true
    # dead-permit shape is unchanged: entry present, no difference anywhere,
    # row still claiming to record one.
    if dead_rw:
        for b in dead_rw:
            print("  DEAD BASELINE %s -> @%s (:WHEN: %s): cited ruling %r — but no historical "
                  "byte difference matches the identity, or the ruling line is gone from the "
                  "chat, so the disposition records nothing and would permit a rewrite"
                  % (b[0][0], b[0][1], b[0][3], b[1]))
        raise CannotRun("%d of %d REWRITTEN_BASELINES row(s) no longer match a historical "
                        "difference plus their visible ruling — a dead baseline is a permit, "
                        "not a record (see the DEAD BASELINE line(s) above)"
                        % (len(dead_rw), len(REWRITTEN_BASELINES)))

    notes.append("APPEND-ONLY: %d commit(s) touched the chat inside the objective's window "
                 "(base %s); every entry each one held is still present, in order, "
                 "byte-identical" % (len(in_window), base[:8]))
    notes.append("NO-DROP: %d message(s) today over %d commit(s) that touched the chat; "
                 "%d reworded historical region(s) outside the window (%s), none ever dropped"
                 % (len(messages), len(history), len(rewords),
                    ", ".join("line %d (%d commit(s))" % (line, len(shas))
                              for line, shas in sorted(rewords.items())[:8]) or "none"))
    if interleaved:
        notes.append("APPEND-ONLY: %d commit(s) are NOT a byte prefix of the current file — "
                     "graded per entry above, that is concurrent-append interleaving plus the "
                     "repair classes below, not an edited or dropped message (the whole-file "
                     "read this harness shipped with called every one of them a violation)"
                     % len(interleaved))
    if fold_splits:
        notes.append("FOLD-SPLIT: %d historical region(s) shrank because a folded sibling's "
                     "drawer tail was re-headed back out of them — verified: each tail's own "
                     ":WHEN: belongs to a headed entry today (Lead merge-repair, not an edit) — "
                     "the region(s) at line(s) %s"
                     % (len(fold_splits),
                        ", ".join("%d (%d commit(s))" % (line, len(shas))
                                  for line, shas in sorted(fold_splits.items()))))
    if repairs_exercised:
        notes.append("ACCEPTED-REPAIR: %d of %d pinned correction(s) exercised — %s"
                     % (len(repairs_exercised), len(ACCEPTED_REPAIRS),
                        "; ".join("%s: %r -> %r (%s)" % (row[0][3], row[2][0], row[1],
                                  row[3]) for row in ACCEPTED_REPAIRS)))
    if rewritten_dispositions:
        notes.append("REWRITTEN-BASELINE: %d of %d dispositioned in-window rewrite(s) exercised "
                     "against their visible ruling(s) — %s"
                     % (len(rewritten_dispositions), len(REWRITTEN_BASELINES),
                        "; ".join("%s (%s)" % (b[0][3], b[1][:58])
                                  for b in REWRITTEN_BASELINES)))
    # ---- 6. LOG: the run log is well-formed, complete and cross-linked
    run_lines, summary = parse_log(log_text)
    if len(run_lines) < LOG_RUN_LINE_FLOOR:
        problems.append("LOG: %d run line(s), floor is %d — the log no longer holds one line "
                        "per turn" % (len(run_lines), LOG_RUN_LINE_FLOOR))
    if not any(section.startswith("Summary") for section in summary_sections(log_text)):
        problems.append("LOG: the closed `## Summary` section is missing — the log was never closed")
    if len(summary) < LOG_SUMMARY_LINE_FLOOR:
        problems.append("LOG: the summary holds %d line(s), floor is %d"
                        % (len(summary), LOG_SUMMARY_LINE_FLOOR))
    for number, line in run_lines:
        match = RUN_LINE_RE.match(line)
        if not match:
            problems.append("LOG line %d: not a run line (`<sha>@<branch> | <seat> | <lane> | "
                            "<date> [| <note>]`): %s" % (number, line[:90]))
            continue
        sha = match.group("sha")
        if subprocess.run(("git", "cat-file", "-e", "%s^{commit}" % sha),
                          cwd=root, capture_output=True).returncode != 0:
            problems.append("LOG line %d: run id %s does not resolve to a commit in this repo"
                            % (number, sha))
    compared = 0
    for turn in TURNS:
        markers = LOG_MARKERS[turn]
        hits = []
        for number, line in run_lines:
            match = RUN_LINE_RE.match(line)
            if not match:
                continue
            note = match.group("note") or ""
            if any(marker in note for marker in markers):
                hits.append((number, match))
        if not hits:
            problems.append("LOG-TURN %s: no run line carries %s — the turn is not in the log"
                            % (turn, " or ".join(repr(m) for m in markers)))
            continue
        dates = {match.group("date") for _number, match in hits}
        chat_dates = turn_dates.get(turn) or set()
        if chat_dates:
            compared += 1
        if chat_dates and not (chat_dates & dates):
            problems.append("LOG-TURN %s: the log's date(s) %s disagree with the chat entry's "
                            "date(s) %s — the two records of the turn are not the same turn"
                            % (turn, sorted(dates), sorted(chat_dates)))
    notes.append("LOG: %d run line(s), every run id resolves to a commit; %d summary line(s)"
                 % (len(run_lines), len(summary)))
    notes.append("LOG-DATE: %d/%d turn(s) cross-checked between the log date and the chat "
                 ":WHEN: (a turn with none is refused above, never skipped)"
                 % (compared, len(TURNS)))

    # ---- 6b. LOG-COVERAGE: a run record outside the region the harness reads
    # is a turn missing from the evidence, not a turn recorded.
    stranded, duplicates, superseded, seen_ids, graded_count = \
        scan_run_line_coverage(log_text, run_lines)
    for ident in SUPERSEDED_RUN_LINES:
        if ident not in seen_ids:
            problems.append("LOG-COVERAGE: the pinned superseded record `%s` is no longer in "
                            "the log — a logged record stays visible (append-only), so the pin "
                            "and the file disagree about what happened" % ident)
    for number, ident, section in stranded:
        problems.append("LOG-COVERAGE line %d (`%s`): a run-shaped record the harness cannot read — it "
                        "sits under `## %s`, and parse_log grades only a section named exactly "
                        "`runs`, so this turn contributes zero evidence. The fix is the "
                        "convention this log already uses: re-open a `## runs` block and "
                        "re-list the line at EOF; never move the original"
                        % (number, ident, section))
    notes.append("LOG-COVERAGE: %d run-shaped record(s) in the log — %d graded, %d re-listed "
                 "duplicate(s), %d pinned-superseded, %d stranded"
                 % (graded_count + len(duplicates) + len(superseded) + len(stranded),
                    graded_count, len(duplicates), len(superseded), len(stranded)))

    # ---- 7. BOARD: the parked order is still restorable
    headlines = board_headlines(board_text)
    headline_text = "\n".join(text for _number, text in headlines)
    for item in BOARD_ITEMS:
        if item not in headline_text:
            problems.append("BOARD: `%s` is no longer a headline on the board — the Lead's "
                            "parked order cannot be restored over a deleted item" % item)
    ongoing = [text for _number, text in headlines if " ONGOING " in text or text.startswith("* ONGOING")]
    notes.append("BOARD: %d parked item(s) present, %d headline(s) total, %d ONGOING, "
                 "TEST-CHAIN item on the board: %s"
                 % (len(BOARD_ITEMS), len(headlines), len(ongoing),
                    "yes" if "TEST-CHAIN" in headline_text else "no"))

    if problems:
        raise Red("\n".join(problems))

    print("CHAIN-TEST CHECK OK — %d turns landed, %d chat messages, %d run lines"
          % (len(TURNS), len(messages), len(run_lines)))
    for note in notes:
        print("  " + note)
    return 0


def summary_sections(text):
    out = []
    for line in text.splitlines():
        if line.startswith("## "):
            out.append(line[3:].strip())
    return out


def objective_base(root, control_text):
    """The commit that switched the chain to the TEST-CHAIN objective.

    Derived from the tree (not pinned to a sha): the first commit whose
    CONTROL.org carries `#+OBJECTIVE: TEST-CHAIN`. A hard-coded sha
    would rot on the first rebase; the objective's own words cannot.
    """
    marker = "#+OBJECTIVE: TEST-CHAIN"
    for sha in git(root, "log", "--format=%H", "--reverse", "--", CONTROL_REL).split():
        try:
            old = git(root, "show", "%s:%s" % (sha, CONTROL_REL))
        except CannotRun:
            continue
        if marker in old:
            return sha
    return None



# ------------------------------------------------------------------ selftest
# A check that cannot FAIL is not a check (ELEVENTH harness law, applied to
# the harness itself). Every control below mutates a COPY of the tree and
# asserts that the leg owning the mutated fact goes RED — or, for a missing
# input, CANNOT RUN. The shipped tree is never written to.
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


def control_dropped_entry(root):
    text = _read_file(root, CHAT_REL)
    cut = text.rfind("\n* MSG ")
    if cut < 0:
        raise CannotRun("control dropped-entry: there is no chat entry to drop")
    _write_file(root, CHAT_REL, text[:cut] + "\n")


def control_edited_entry(root):
    _replace_once(root, CHAT_REL, "TEST-T3 — the chain's own state",
                  "TEST-T3 — the chain's own stat")


def control_broken_drawer(root):
    _replace_once(root, CHAT_REL, ":KIND: report\n", "")


def control_deleted_board_item(root):
    text = _read_file(root, BOARD_REL)
    kept = [line for line in text.splitlines(True) if "FR R-006 page registration" not in line]
    if len(kept) == len(text.splitlines(True)):
        raise CannotRun("control deleted-board-item: the FR-R006 headline is not on the board")
    _write_file(root, BOARD_REL, "".join(kept))


def control_broken_run_id(root):
    text = _read_file(root, LOG_REL)
    lines = text.splitlines(True)
    for index, line in enumerate(lines):
        if RUN_LINE_INTENT_RE.match(line):
            lines[index] = re.sub(r"^[0-9a-f]{7,40}", "deadbee", line)
            break
    else:
        raise CannotRun("control broken-run-id: the log holds no run line")
    _write_file(root, LOG_REL, "".join(lines))


def control_missing_summary(root):
    text = _read_file(root, LOG_REL)
    if "## Summary" not in text:
        raise CannotRun("control unclosed-log-summary: the log holds no `## Summary` heading")
    # EVERY heading, not the first: the log gained a second cycle's Summary on
    # 2026-10-22, so a single replacement left a live "Summary" section behind and
    # this control answered rc 0 over its own rotted premise (measured here).
    _write_file(root, LOG_REL, text.replace("## Summary", "## Notes"))


def control_missing_control_file(root):
    os.remove(os.path.join(root, CONTROL_REL))


def control_no_change(root):
    return None


def control_log_date_disagrees(root):
    """Re-date EVERY graded marker-carrying run line (graded = inside the log's
    `runs` sections, the only region the harness reads).

    All of them, not the first: the leg asks whether a turn's log dates and its
    chat dates INTERSECT, and each turn is logged by three cycles, so one stale
    date still agrees with the chat and answers GREEN — the control would grade
    nothing (measured here)."""
    text = _read_file(root, LOG_REL)
    run_lines, _summary = parse_log(text)
    markers = [m for turn in TURNS for m in LOG_MARKERS[turn]]
    lines = text.splitlines()
    touched = 0
    for number, line in run_lines:
        match = RUN_LINE_RE.match(line)
        if not (match and any(m in (match.group("note") or "") for m in markers)):
            continue
        lines[number - 1] = line.replace(match.group("date"), "2026-01-01")
        touched += 1
    if not touched:
        raise CannotRun("control log-date-disagrees: no marker-carrying run line to re-date")
    _write_file(root, LOG_REL, "\n".join(lines) + "\n")


def control_run_line_outside_runs(root):
    """Relocate a GRADED run record to the end of the log, which sits under a
    prose heading — the exact shape that made a whole cycle invisible to
    parse_log while the harness kept printing a count.

    A marker-free line is chosen so the LOG-TURN legs stay satisfied and the
    only new finding is this leg's own: a control that also fires its siblings
    cannot say which leg caught the mutation. The line is re-filed under a
    PROSE heading, not bare at EOF: the log's tail is now a re-opened `## runs`
    block (the re-list convention this leg itself prescribes), so a bare-EOF
    append lands INSIDE the graded region and proves nothing — measured
    2026-10-25, selftest run on the 0015 union."""
    text = _read_file(root, LOG_REL)
    run_lines, _summary = parse_log(text)
    markers = [mk for turn in TURNS for mk in LOG_MARKERS[turn]]
    target = None
    for number, line in run_lines:
        match = RUN_LINE_RE.match(line)
        if match and not any(mk in (match.group("note") or "") for mk in markers):
            target = (number, line)
            break
    if target is None:
        raise CannotRun("control run-line-outside-runs: the graded log holds no run line that "
                        "is free of a turn marker, so the leg cannot be isolated")
    number, line = target
    lines = text.splitlines(True)
    del lines[number - 1]
    _write_file(root, LOG_REL, "".join(lines).rstrip("\n") + "\n\n## stray prose (not runs)\n\n"
                + line.rstrip("\n") + "\n")


def control_pinned_record_deleted(root):
    """Delete the log line the superseded pin exists to keep visible. The pin
    must grade SOMETHING: an accepted-divergence list nobody checks is a way of
    forgetting a record politely (the same reasoning that pins the CSV twins'
    divergent FLOAT_PARITY rows by identity)."""
    text = _read_file(root, LOG_REL)
    lines = text.splitlines(True)
    hits = [i for i, line in enumerate(lines) if loose_run_id(line) in SUPERSEDED_RUN_LINES]
    if len(hits) != 1:
        raise CannotRun("control pinned-record-deleted: the log carries %d line(s) for the "
                        "pinned superseded record(s), expected exactly 1" % len(hits))
    del lines[hits[0]]
    _write_file(root, LOG_REL, "".join(lines))


def control_unparseable_when(root):
    """Blind the drawer read the way the glued-key parse did: NO :WHEN: value
    yields a date, so the log/chat cross-check has nothing to compare.

    Every value, and the whole `:WHEN: ` label rather than `:WHEN: [`: one entry
    in the live chat carries a bracket-less timestamp, so a bracket-only sweep
    left a readable date behind and the coverage leg never fired."""
    text = _read_file(root, CHAT_REL)
    broken = text.replace(":WHEN: ", ":WHEN: x")
    if broken == text:
        raise CannotRun("control unparseable-when: the chat holds no :WHEN: timestamp to break")
    _write_file(root, CHAT_REL, broken)


def control_folded_entry(root):
    """The MERGE FOLD itself: delete one entry's headline plus its drawer
    header, leaving the `:WHEN:` / `:END:` tail welded onto the previous
    entry — the exact shape merge 3b121ee left at CHAT.org:7731 (and
    4598a81 at :6407). CHAT-FORMAT stays silent over it (the orphan parses
    as body), so this control is the leg's ONLY proof it can see the fold.

    The live folds are neutralised FIRST (each orphan line indented, so the
    copy starts at ZERO orphans): the shipped chat already carries four true
    CHAT-STRUCTURE reds, and a control whose expected text is printed by the
    tree rather than by its own mutation grades nothing (ELEVENTH law)."""
    text = _read_file(root, CHAT_REL)
    lines = text.splitlines()
    for number, _line, _owner in scan_orphan_drawers(text)[0]:
        lines[number - 1] = "  " + lines[number - 1]
    text = "\n".join(lines) + "\n"
    if scan_orphan_drawers(text)[0]:
        raise CannotRun("control folded-entry: the orphan lines could not be neutralised")
    cut = text.rfind("\n* MSG ")
    if cut < 0:
        raise CannotRun("control folded-entry: the chat holds no entry to fold")
    lines = text[cut + 1:].splitlines(True)
    if len(lines) < 7 or not lines[0].startswith("* MSG ") or not lines[1].startswith(":PROPERTIES:"):
        raise CannotRun("control folded-entry: the last entry does not open with a headline "
                        "plus a :PROPERTIES: drawer, so the fold cannot be reproduced")
    _write_file(root, CHAT_REL, text[:cut] + "\n" + "".join(lines[5:]))


def control_blind_drawer_scan(root):
    """Take the orphan scan's own eyes away: indent EVERY column-0 drawer
    field, so no field line sits inside an entry region any more and the leg
    would grade nothing while printing a clean 0 orphans. A sweep of all of
    them, not one key: a single indented key leaves the other four readable
    and the coverage guard would never fire."""
    text = _read_file(root, CHAT_REL)
    lines = text.splitlines()
    rebuilt = ["  " + line if DRAWER_FIELD_RE.match(line) else line for line in lines]
    broken = "\n".join(rebuilt) + "\n"
    if broken == text:
        raise CannotRun("control blind-drawer-scan: the chat holds no column-0 drawer field "
                        "to indent")
    _write_file(root, CHAT_REL, broken)


def control_prose_lookalike(root):
    """The false positive that rejected a clean branch: run 40113340018
    (2026-10-24 17:25Z) REJECTED ai/turn-20261024-1632 — pure additive
    housekeeping — because the relief seat's TEST-T2 body line quoting the
    drawer order sat at column 0 and the prefix read called `:PROPERTIES:`
    an orphan field, going red on prose. The grammar read excludes it. Live
    folds neutralised FIRST — the same base protocol as control_folded_entry
    — so the PAIR grades discrimination from one base: this control asserts
    the problem text is ABSENT for the lookalike (!needle), its sibling
    asserts a real orphan still fires (needle present). BASE NOTE (Lead
    2026-10-25: both live folds repaired + the 22:05 rewrite dispositioned + the
    restructure rulings landed): the clean-base copy now grades GREEN, so this
    control expects rc 0 with the orphan text ABSENT — the discrimination
    assertion is unchanged. MECHANICS NOTE: the lookalike rides inside a NEW
    well-formed entry the fixture appends, NOT as bare EOF prose — under the
    per-entry law a non-headline append at EOF joins the last landed entry's
    region and IS a rewrite (measured: f23966ed's fixture run went red on the
    20:18 ruling entry), so the era's raw-EOF shape is itself illegal now."""
    text = _read_file(root, CHAT_REL)
    lines = text.splitlines()
    for number, _line, _owner in scan_orphan_drawers(text)[0]:
        lines[number - 1] = "  " + lines[number - 1]
    text = "\n".join(lines) + "\n"
    if scan_orphan_drawers(text)[0]:
        raise CannotRun("control prose-lookalike: the orphan lines could not be neutralised")
    text += ("\n* MSG lead -> @all :note:      :msg:lead:all:note:\n"
             ":PROPERTIES:\n:FROM: lead\n:TO: all\n:KIND: note\n"
             ":WHEN: [2027-01-01 Fri 00:00 UTC]\n:END:\n"
             "  control: the next line quotes drawer syntax at column 0, the exact\n"
             ":PROPERTIES:, :WHEN:, :FROM:, :TO:, :KIND:, :END:. — shape that once\n"
             "  false-positived as an orphan field (run 40113340018).\n")
    _write_file(root, CHAT_REL, text)


def _entry_regions(text):
    """(start, end) line indices of every `* MSG` region, in file order."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("* MSG ")]
    if not starts:
        raise CannotRun("control: the chat holds no `* MSG` entry to work on")
    regions = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        regions.append((start, end))
    return lines, regions


INTERLEAVED_ENTRY = (
    "* MSG software-engineer -> @lead :note:      :msg:software-engineer:lead:note:",
    ":PROPERTIES:",
    ":FROM: software-engineer",
    ":TO: lead",
    ":KIND: note",
    ":WHEN: [2027-01-01 Fri 00:00 UTC]",
    ":END:",
    "  control: one entry merged BETWEEN two landed ones, exactly what a",
    "  union-merge of two concurrent EOF appends produces.",
)


def control_interleaved_append(root):
    """The shape the whole-file byte-prefix read could not tell from a
    violation: a well-formed entry inserted between two landed entries, so
    every older version stops being a prefix of today while nothing was
    edited, dropped or reordered. The entry-granularity legs must answer
    rc 0 over it — the false-red class this rewrite exists to remove, graded
    rather than asserted."""
    text = _read_file(root, CHAT_REL)
    lines, regions = _entry_regions(text)
    if len(regions) < 3:
        raise CannotRun("control interleaved-append: fewer than three entries to merge between")
    at = regions[1][0]
    lines[at:at] = list(INTERLEAVED_ENTRY)
    _write_file(root, CHAT_REL, "\n".join(lines) + "\n")


def control_reordered_entry(root):
    """Swap the last two entries: every identity survives, every byte
    survives, only the ORDER moves — the one violation a drop-only read
    cannot see, and the one a rebase of two concurrent branches produces."""
    text = _read_file(root, CHAT_REL)
    lines, regions = _entry_regions(text)
    if len(regions) < 2:
        raise CannotRun("control reordered-entry: fewer than two entries to swap")
    (a_start, a_end), (b_start, b_end) = regions[-2], regions[-1]
    rebuilt = lines[:a_start] + lines[b_start:b_end] + lines[a_start:b_start] + lines[b_end:]
    _write_file(root, CHAT_REL, "\n".join(rebuilt) + "\n")


def control_stale_allowance(root):
    """Retire the pinned correction from the DATA side: re-date the landed
    entry the row describes, so the recorded repair no longer matches the
    bytes and the row's own predecessor never reaches today's line. The
    allowance then permits nothing while still claiming to, so the harness
    must refuse (CANNOT RUN) instead of printing a green that grades nothing.

    Mutated in the chat, not in the copy's roster: the selftest runs the
    PRISTINE script against each copy (see selftest()), so a control that
    edited this harness's own constants would be invisible to the run it is
    supposed to control. The brackets come off and the stamp stays, so the
    entry is still the SAME entry (identity survives the read) and only the
    recorded repair is gone — a drop-shaped mutation would prove nothing here."""
    _replace_once(root, CHAT_REL, ':WHEN: [2026-10-22 Thu 11:24 UTC]',
                  ':WHEN: 2026-10-22 Thu 11:24 UTC')


# (name, mutation, expected exit code, expected text in the output, extra argv)
CONTROLS = (
    ("dropped chat entry", control_dropped_entry, 1, "is GONE from the current file", ()),
    ("edited chat entry", control_edited_entry, 1, "APPEND-ONLY", ()),
    ("broken drawer", control_broken_drawer, 1, "CHAT-FORMAT", ()),
    ("deleted board item", control_deleted_board_item, 1, "is no longer a headline", ()),
    ("broken run id", control_broken_run_id, 1, "does not resolve to a commit", ()),
    ("unclosed log summary", control_missing_summary, 1, "section is missing", ()),
    ("missing control file", control_missing_control_file, 2, "CANNOT RUN", ()),
    ("turns never landed", control_no_change, 1, "none is an ancestor of", "--main",),
    ("log date disagrees", control_log_date_disagrees, 1, "disagree with the chat entry", ()),
    ("no chat date parses", control_unparseable_when, 2, "drawer parse is broken", ()),
    ("folded entry (no headline)", control_folded_entry, 1, "CHAT-STRUCTURE", ()),
    ("blind drawer scan", control_blind_drawer_scan, 2, "grades nothing", ()),
    ("prose lookalike tolerated", control_prose_lookalike, 0, "!sits outside any entry", ()),
    ("run line outside `runs`", control_run_line_outside_runs, 1, "a run-shaped record the "
     "harness cannot read", ()),
    ("pinned record deleted", control_pinned_record_deleted, 1, "pinned superseded record", ()),
    ("concurrent append interleaved", control_interleaved_append, 0, "CHAIN-TEST CHECK OK", ()),
    ("entry reordered", control_reordered_entry, 1, "an entry was reordered", ()),
    ("stale accepted repair", control_stale_allowance, 2, "dead allowance is a permit", ()),
)

# The control roster is PINNED, not derived: a comparison cannot see its own
# coverage, and `SELFTEST OK — N control(s)` printed N from len(CONTROLS), so
# deleting a control deleted the proof and still answered OK (landing_gate's
# MERGE_ROSTER law, applied to this harness's own legs).
EXPECTED_CONTROLS = 18


def selftest(root):
    """Prove each leg can fire, against copies. Returns 0 or raises Red."""
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d entries, the pin says %d — a control "
                        "vanished (or was added without the pin), so `SELFTEST OK` would no "
                        "longer mean every leg was run"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = os.path.join(root, "scripts", "chain_test_check.py")
    base = objective_base(root, read(root, CONTROL_REL))
    failures = []
    for name, mutation, expected_rc, expected_text, extra in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="chain-test-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                          ".pytest_cache", "dist", "build"))
            mutation(target)
            argv = [sys.executable, script, "--root", target]
            if extra == "--main":
                # point the harness at a ref that predates the turns: the
                # turns are real commits, they simply never landed THERE.
                argv += ["--main", base or "ai/main"]
            proc = subprocess.run(argv, capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            # `!needle` = the text must be ABSENT. Under the WHOLE-FILE
            # byte-prefix law every file mutation broke a leg and the copy was
            # always red, so the exclusion rode a red exit. Under the PER-ENTRY
            # law a legal append on a clean base grades green, so an exclusion
            # may now ride a GREEN exit: the assertion is still the problem
            # text's ABSENCE, and the sibling controls prove the leg itself can
            # still fire on a real violation.
            negated = expected_text.startswith("!")
            needle = expected_text[1:] if negated else expected_text
            hit = needle not in out if negated else needle in out
            if proc.returncode == expected_rc and hit:
                print("  control %-24s -> rc %d as expected (%s)" % (name, proc.returncode, expected_text))
            else:
                failures.append("%s: expected rc %d %s %r, got rc %d: %s"
                                % (name, expected_rc, "without" if negated else "containing",
                                   needle, proc.returncode, out.strip()[:300]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise Red("\n".join(failures))
    print("SELFTEST OK — %d control(s), every leg proved able to fail" % len(CONTROLS))
    return 0


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
