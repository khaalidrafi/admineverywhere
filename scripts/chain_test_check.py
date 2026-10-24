#!/usr/bin/env python3
"""Re-runnable check of the TEST-CHAIN objective's landed evidence.

WHY this exists (measured, not assumed). The Owner ordered a 3-turn
machinery test on 2026-10-22 09:22Z (TEST-T1 check-in, TEST-T2 one
harness improvement, TEST-T3 board/chat verification). Each turn left a
PROSE record: a chat entry and a line in docs/CHAIN-TEST.md. Prose is not
re-runnable. The Lead's next move is to flip #+OBJECTIVE-STATE in
agent-team/TEAM-CONTROL.org and restore the parked feature order, and the
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
               the chain to TEST-CHAIN and everything after it), every
               historical version of the chat is a BYTE prefix of the
               current one: no entry was edited and none was dropped.
  NO-DROP      over the WHOLE history, the sequence of message identities
               (routing + timestamp) never loses a member: an entry can
               be reworded, but it can never be removed. (A body edit is
               reported as a note, not a red — the Lead's own file-rename
               propagation reworded two historical bodies on 2026-10-21.)
  LOG          docs/CHAIN-TEST.md holds one well-formed run line per turn
               (`sha@branch | seat | lane | date [| note]`), every run id
               resolves to a real commit, each turn's line carries that
               turn's marker AND the same date as its chat entry, and the
               log ends with the closed 3-line summary.
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
CHAT_REL = "agent-team/TEAM-CHAT.org"
LOG_REL = "docs/CHAIN-TEST.md"
BOARD_REL = "agent-team/TODOS.org"
CONTROL_REL = "agent-team/TEAM-CONTROL.org"

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


def message_ids(messages):
    return [m["identity"] for m in messages]


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
    agent-team/TEAM-CHAT.org:7731 opens with a bare `:WHEN:`. The same
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
        raise CannotRun("agent-team/TEAM-CHAT.org holds no `* MSG` entry — there is no chat "
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

    # ---- 4. APPEND-ONLY: the objective's own window, byte for byte
    base = objective_base(root, control_text)
    if base is None:
        raise CannotRun("agent-team/TEAM-CONTROL.org never carried the TEST-CHAIN objective "
                        "(`#+OBJECTIVE: TEST-CHAIN`) — this harness grades THAT objective")
    touched = [sha for sha in git(root, "log", "--format=%H", "--", CHAT_REL).split()
               if subprocess.run(("git", "merge-base", "--is-ancestor", base, sha),
                                 cwd=root, capture_output=True).returncode == 0]
    for sha in touched:
        old = git(root, "show", "%s:%s" % (sha, CHAT_REL))
        if not chat_text.startswith(old):
            problems.append("APPEND-ONLY %s: the chat as of this commit is NOT a prefix of the "
                            "current file — an entry was edited or dropped inside the "
                            "objective's window" % sha[:8])
    notes.append("APPEND-ONLY: %d commit(s) touched the chat inside the objective's window "
                 "(base %s), every version is a byte prefix of the current file"
                 % (len(touched), base[:8]))

    # ---- 5. NO-DROP: over the whole history, no entry ever disappears
    current_ids = message_ids(messages)
    edited = []
    for sha in git(root, "log", "--format=%H", "--", CHAT_REL).split():
        old_text = git(root, "show", "%s:%s" % (sha, CHAT_REL))
        old_ids = message_ids(parse_messages(old_text))
        if len(old_ids) > len(current_ids) or old_ids != current_ids[:len(old_ids)]:
            problems.append("NO-DROP %s: the chat's message sequence at this commit is not a "
                            "prefix of today's — an entry was removed or reordered" % sha[:8])
            continue
        for index, old_message in enumerate(parse_messages(old_text)):
            if old_message["body"] != messages[index]["body"]:
                edited.append((sha, messages[index]["line"]))
    if edited:
        seen = sorted({line for _sha, line in edited})
        notes.append("NO-DROP: %d historical bod(y/ies) were reworded after the fact "
                     "(line(s) %s) — an entry may be reworded, never removed"
                     % (len(seen), ", ".join(str(line) for line in seen)))
    notes.append("NO-DROP: %d message(s) over the whole history, none ever dropped"
                 % len(messages))

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
    TEAM-CONTROL.org carries `#+OBJECTIVE: TEST-CHAIN`. A hard-coded sha
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
    entry — the exact shape merge 3b121ee left at TEAM-CHAT.org:7731 (and
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
    asserts a real orphan still fires (needle present)."""
    text = _read_file(root, CHAT_REL)
    lines = text.splitlines()
    for number, _line, _owner in scan_orphan_drawers(text)[0]:
        lines[number - 1] = "  " + lines[number - 1]
    text = "\n".join(lines) + "\n"
    if scan_orphan_drawers(text)[0]:
        raise CannotRun("control prose-lookalike: the orphan lines could not be neutralised")
    text += ":PROPERTIES:, :WHEN:, :FROM:, :TO:, :KIND:, :END:.\n"
    _write_file(root, CHAT_REL, text)


# (name, mutation, expected exit code, expected text in the output, extra argv)
CONTROLS = (
    ("dropped chat entry", control_dropped_entry, 1, "NO-DROP", ()),
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
    ("prose lookalike tolerated", control_prose_lookalike, 1, "!sits outside any entry", ()),
)

# The control roster is PINNED, not derived: a comparison cannot see its own
# coverage, and `SELFTEST OK — N control(s)` printed N from len(CONTROLS), so
# deleting a control deleted the proof and still answered OK (landing_gate's
# MERGE_ROSTER law, applied to this harness's own legs).
EXPECTED_CONTROLS = 13


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
            # `!needle` = the text must be ABSENT: an exclusion (a shape the
            # leg must NOT flag) can only be graded on a copy that is still
            # red for other legs (every file mutation breaks the byte-prefix
            # legs on the copy), so the assertion is the problem text's
            # ABSENCE, never a green exit.
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
