#!/usr/bin/env python3
"""Re-runnable check of every `:WHEN:` timestamp the chain writes.

WHY this exists (measured, not assumed). The queue's longest-running branch,
ai/turn-20261024-1632, was REJECTED seven times on 2026-10-24. The two earlier
classes were environmental (a checker false-red, then a fold inherited from a
stale base) and the Lead repaired both; the class that survived the repair is
content, and the duty reviewer had to find it by hand:

  all four new chat entries read `:WHEN: [2026-10-24 Fri …]` and that date is a
  SATURDAY — the only malformed timestamps in an 8339-line file.

The Lead reproduced it in a sandbox (`date -d 2026-10-24` -> Sat) and the
verdict's own transcript confirms no harness ever printed it. Nothing in the
family graded the DAY NAME: `chain_test_check.py`'s CHAT-FORMAT leg asks only
whether a drawer carries a `:WHEN:` KEY (DRAWER_KEYS), and the `WHEN_RE` it
keeps for the log cross-check reads group("date") and stops — so a wrong, or
even an impossible, weekday rode green through every run that reviewed that
branch. Prose law says the FORMAT LAW's timestamp is
`[YYYY-MM-DD Eee HH:MM UTC]` (an Org INACTIVE timestamp); a claim that lives
only in prose is the shape this repo's EIGHTH harness law forbids.

So this harness grades the timestamp itself, over BOTH files that carry it:

  SCAN       each graded file exists, holds `* ` records, and the scan finds
             `:WHEN:` lines to grade — a scan that finds none while records
             exist is CANNOT RUN ("grades nothing"), never a clean 0.
  COVERAGE   every drawer record (`:PROPERTIES:` block) owns EXACTLY ONE
             column-0 `:WHEN:`: none means the record has no timestamp for a
             reader to date its claim, two means one drawer was welded onto
             another record (the fold shape) and the reader cannot tell which
             stamp the record actually carries.
  WHEN-SHAPE the stamp is the literal grammar the FORMAT LAW promises:
             `:WHEN: [YYYY-MM-DD Eee HH:MM UTC]` — brackets, a three-letter
             day name, and the UTC label that makes the time comparable
             across seats. An ACTIVE Org timestamp `<…>`, a bare date, a
             missing zone or a lower-case day is RED naming the shape found.
  WHEN-DATE  the three numbers are a real calendar date (2026-02-30 is not).
  WHEN-CLOCK the hour is 00-23 and the minute 00-59 (99:99 matches the shape
             and means nothing).
  WHEN-DAY   the day name is the weekday that date actually falls on. The
             weekday is read from a PINNED English table indexed by
             `date.weekday()`, never from `strftime("%a")`, because `%a` is
             locale-dependent: a CI box with LC_TIME=fr_FR.UTF-8 would render
             "dim." and every legal stamp would answer RED.

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its own input — never a
false red for a tree it has not measured).

What it deliberately does NOT grade, and why it was measured first:

  * CHRONOLOGY (stamps in non-decreasing order). Real and legal on main: the
    chat tail carries `Sat 10:02 UTC` followed by `Sat 06:24 UTC`, because two
    lanes append at EOF and the merge order is not the clock order. A leg that
    fires on correct entries is worse than no leg (the ruling that kept the
    doc-citation leg off prose).
  * `:WHEN:` values quoted INSIDE a body. The FORMAT LAW indents every body
     line, so only column-0 `:WHEN:` lines are drawer fields; control 11 pins
     that an indented prose quote carrying a deliberately impossible stamp is
     NOT flagged.
  * the board (agent-team/TODOS.org) and docs/CHAIN-TEST.md — measured: zero
    column-0 `:WHEN:` lines in either, so grading them would be a claim about
    a shape that does not exist there.

Baseline measured on the delivered tree, not assumed: 362 drawer records
(154 chat + 208 review-log), 362 column-0 stamps, 362 legal, 0 red — the leg
lands green and stays green until somebody writes a wrong day name, and from
then on it is a printed line rather than a Lead sandbox.

Controls run against copies via --root, so the shipped tree is only read:
  cp -r . /tmp/x && python3 scripts/chat_when_check.py --root /tmp/x

And the harness proves it can FAIL, against a copy, with no hand-holding:
  python3 scripts/chat_when_check.py --selftest

It is deliberately NOT named `*_diff.py`: that glob is the landing gate's twin
roster (scripts/landing_gate.py EXPECTED_TWINS), and a harness its roster does
not run is refused by its own cross-check. This one grades the CHAIN's
timestamps, so it stands beside chain_test_check.py and chain_session_check.py
and is run by hand.
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ------------------------------------------------------------ pinned inputs
# The files carrying the chain's timestamps, with the record floor each one
# must still hold (the files only GROW, so a floor is the population promise:
# the evidence graded here must still be THERE — an exact count would rot the
# day someone appends a message).
FILES = (
    ("agent-team/TEAM-CHAT.org", 154),
    ("agent-team/REVIEW-LOG.org", 208),
)

# The pinned English day abbreviations, index = date.weekday() (Monday=0).
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# The grammar the FORMAT LAW writes. Deliberately PERMISSIVE on the ranges
# (dd, HH, MM are any two digits) and on the day name (any three letters), so
# an impossible value reaches the leg that owns it — WHEN-DATE, WHEN-CLOCK,
# WHEN-DAY — and is reported as THAT, not as a parse failure.
WHEN_STRICT_RE = re.compile(
    r"^:WHEN:[ \t]+\[(?P<date>\d{4}-\d{2}-\d{2}) (?P<day>[A-Za-z]{3}) "
    r"(?P<hm>\d{2}:\d{2}) UTC\][ \t]*$"
)
WHEN_LINE_RE = re.compile(r"^:WHEN:")
HEADLINE_RE = re.compile(r"^\* ")
PROPERTIES_RE = re.compile(r"^:PROPERTIES:")


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


def read(root, rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        raise CannotRun("%s is missing — it is one of the files whose :WHEN: stamps "
                        "this harness grades, so there is nothing to measure" % rel)
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def scan_records(text):
    """Every `* ` record and its drawer region.

    Returns a list of dicts: {"line", "head", "props", "stamps": [(line, raw)]}.
    A record's region is its headline line up to the next headline, so a stamp
    that belongs to no record is invisible HERE and is chain_test_check.py's
    CHAT-STRUCTURE orphan class instead — the two legs do not overlap.
    """
    lines = text.split("\n")
    heads = [i for i, line in enumerate(lines, 1) if HEADLINE_RE.match(line)]
    records = []
    for index, start in enumerate(heads):
        stop = heads[index + 1] - 1 if index + 1 < len(heads) else len(lines)
        region = lines[start:stop]
        stamps = [(start + offset + 1, line)
                  for offset, line in enumerate(region) if WHEN_LINE_RE.match(line)]
        records.append({
            "line": start,
            "head": lines[start - 1],
            "props": any(PROPERTIES_RE.match(line) for line in region),
            "stamps": stamps,
        })
    return records


def stamp_problems(rel, line, raw):
    """Grade one stamp line: shape, then date, clock and day name.

    A line that fails the SHAPE is reported once and stops there — a value the
    grammar does not accept cannot also be asked for its weekday, and printing
    three reds for one typo would hide which rule was broken.
    """
    match = WHEN_STRICT_RE.match(raw)
    if not match:
        return ["%s:%d WHEN-SHAPE: %r is not the FORMAT LAW's inactive timestamp "
                "`:WHEN: [YYYY-MM-DD Eee HH:MM UTC]` — brackets, a three-letter day "
                "name and the UTC label are what make a seat's claim dateable and "
                "comparable across lanes" % (rel, line, raw)]
    problems = []
    date_text, day_name, clock = match.group("date"), match.group("day"), match.group("hm")
    year, month, day = (int(part) for part in date_text.split("-"))
    try:
        real = datetime.date(year, month, day)
    except ValueError as exc:
        return ["%s:%d WHEN-DATE: %s is not a real calendar date (%s) — the day name "
                "and clock cannot be checked against a date that does not exist"
                % (rel, line, date_text, exc)]
    hour, minute = (int(part) for part in clock.split(":"))
    if hour > 23 or minute > 59:
        problems.append("%s:%d WHEN-CLOCK: %s:%s is outside a UTC clock (hours 00-23, "
                        "minutes 00-59) — the shape matched, so a typo like 25:70 would "
                        "otherwise carry a legal-looking timestamp"
                        % (rel, line, clock.split(':')[0], clock.split(':')[1]))
    expected = WEEKDAYS[real.weekday()]
    if day_name != expected:
        problems.append("%s:%d WHEN-DAY: %s is a %s, the stamp says %s — the FORMAT LAW's "
                        "`Eee` must be the weekday the date actually falls on (this is the "
                        "defect that rejected ai/turn-20261024-1632 seven times, hand-found "
                        "each time)" % (rel, line, date_text, expected, day_name))
    return problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="tree to grade (a copy for controls)")
    parser.add_argument("--selftest", action="store_true",
                        help="prove every leg can fire, against copies")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)

    if args.selftest:
        return selftest(root)

    roster = list(FILES)

    problems = []
    notes = []
    total_stamps = 0
    for rel, floor in roster:
        text = read(root, rel)
        records = scan_records(text)
        drawer_records = [r for r in records if r["props"]]
        stamps = [(rel, line, raw) for r in drawer_records
                  for line, raw in r["stamps"]]
        total_stamps += len(stamps)

        if not records:
            raise CannotRun("%s carries no `* ` record at all — either the file moved or "
                            "the scan lost its shape; a timestamp check that reads "
                            "nothing must say so, not report 0 problems" % rel)
        if not drawer_records:
            raise CannotRun("%s has %d headlines but NONE opens a :PROPERTIES: drawer — "
                            "the record shape is gone, so there is no stamp region to "
                            "grade" % (rel, len(records)))
        if not stamps:
            raise CannotRun("%s has %d drawer record(s) and ZERO column-0 `:WHEN:` lines — the scan "
                            "grades nothing here, and a comparison cannot see its own "
                            "coverage: either every record lost its timestamp or the field "
                            "scan is blind"
                            % (rel, len(drawer_records)))
        if len(drawer_records) < floor:
            problems.append("SCAN %s: %d drawer record(s), the floor is %d — records were "
                            "removed, and a timestamp roster that shrank silently proves "
                            "nothing about the ones left" % (rel, len(drawer_records), floor))

        # ---- COVERAGE: exactly one stamp per drawer record
        for record in drawer_records:
            count = len(record["stamps"])
            if count == 0:
                problems.append("WHEN-COVERAGE %s:%d `%s`: the record opens a "
                                ":PROPERTIES: drawer but carries NO `:WHEN:` — its claims "
                                "have no date, and the reader cannot order them"
                                % (rel, record["line"], record["head"][:60]))
            elif count > 1:
                problems.append("WHEN-COVERAGE %s:%d `%s`: %d `:WHEN:` lines in one drawer "
                                "region (at %s) — one record cannot carry two timestamps, "
                                "and this is the shape a fold leaves behind"
                                % (rel, record["line"], record["head"][:60], count,
                                   ", ".join(str(line) for line, _ in record["stamps"])))
        unreadable = 0
        for rel2, line, raw in stamps:
            found = stamp_problems(rel2, line, raw)
            if any("WHEN-SHAPE" in p or "WHEN-DATE" in p for p in found):
                unreadable += 1
            problems.extend(found)
        notes.append("%s: %d record(s), %d stamp(s) graded%s"
                     % (rel, len(drawer_records), len(stamps),
                        "" if not unreadable else " (%d unreadable by shape/date)" % unreadable))

    for note in notes:
        print("  " + note)
    if problems:
        raise Red("\n".join(problems))
    print("WHEN OK — %d :WHEN: stamp(s) over %d file(s): every drawer record owns exactly "
          "one, and every stamp is a real date, a legal UTC clock and the weekday that "
          "date falls on" % (total_stamps, len(roster)))
    return 0


# ------------------------------------------------------------------ controls
def _copy_workspace(root):
    """A copy of the tree with a synthetic roster, so controls never touch main."""
    tmp = tempfile.mkdtemp(prefix="chat-when-control-")
    tree = os.path.join(tmp, "tree")
    shutil.copytree(root, tree, symlinks=True,
                    ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                  ".pytest_cache", "dist", "build"))
    return tmp, tree


def _write(tree, rel, text):
    path = os.path.join(tree, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _load(tree, rel):
    with open(os.path.join(tree, rel), encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _replace_once(tree, rel, old, new):
    text = _load(tree, rel)
    if old not in text:
        raise Red("control needle not found in %s: %r" % (rel, old))
    _write(tree, rel, text.replace(old, new, 1))


CHAT = "agent-team/TEAM-CHAT.org"
LOG = "agent-team/REVIEW-LOG.org"


def _first_stamp(tree, rel):
    text = _load(tree, rel)
    for line in text.split("\n"):
        if WHEN_LINE_RE.match(line) and WHEN_STRICT_RE.match(line):
            return line
    raise Red("no strict :WHEN: line in %s" % rel)


def _mutate_day(tree, rel):
    """Flip one stamp's day name to one the date cannot be."""
    raw = _first_stamp(tree, rel)
    match = WHEN_STRICT_RE.match(raw)
    date_text = match.group("date")
    year, month, day = (int(p) for p in date_text.split("-"))
    real = datetime.date(year, month, day)
    wrong = WEEKDAYS[(real.weekday() + 1) % 7]
    _replace_once(tree, rel, raw, raw.replace(match.group("day"), wrong, 1))


def control_no_change(tree):
    pass


def control_chat_wrong_day(tree):
    _mutate_day(tree, CHAT)


def control_log_wrong_day(tree):
    _mutate_day(tree, LOG)


def control_impossible_date(tree):
    raw = _first_stamp(tree, CHAT)
    date_text = WHEN_STRICT_RE.match(raw).group("date")
    _replace_once(tree, CHAT, raw, raw.replace(date_text, "2026-02-30", 1))


def control_bad_clock(tree):
    raw = _first_stamp(tree, CHAT)
    clock = WHEN_STRICT_RE.match(raw).group("hm")
    _replace_once(tree, CHAT, raw, raw.replace(clock, "25:70", 1))


def control_broken_shape(tree):
    raw = _first_stamp(tree, CHAT)
    _replace_once(tree, CHAT, raw, raw.replace("[", "<", 1).replace("]", ">", 1))


def control_stamp_dropped(tree):
    """Delete one record's :WHEN: line, leaving its drawer open."""
    _replace_once(tree, CHAT, _first_stamp(tree, CHAT), "")


def control_stamp_duplicated(tree):
    raw = _first_stamp(tree, LOG)
    _replace_once(tree, LOG, raw, raw + "\n" + raw)


def control_all_stamps_gone(tree):
    for rel in (CHAT, LOG):
        text = _load(tree, rel)
        _write(tree, rel, "\n".join(line for line in text.split("\n")
                                   if not WHEN_LINE_RE.match(line)))


def control_file_missing(tree):
    os.remove(os.path.join(tree, CHAT))


def control_prose_quote(tree):
    """An INDENTED body line quoting an illegal stamp must stay innocent.

    The chat body is 8000+ lines of seats quoting drawer keys; a leg that read
    them as fields would fire on correct entries, which is worse than no leg.
    The assertion is therefore the impossible date's ABSENCE from the verdict,
    on a copy that must still be GREEN.
    """
    _write(tree, CHAT, _load(tree, CHAT) +
           "\n  the drawer order is :PROPERTIES:, :WHEN: [2026-02-30 Fri 99:99 UTC], "
           ":FROM: — quoted prose, indented, NOT a field\n")


CONTROLS = (
    ("baseline tree is legal", control_no_change, 0, "WHEN OK", ()),
    ("chat day name wrong", control_chat_wrong_day, 1, "WHEN-DAY", ()),
    ("review-log day name wrong", control_log_wrong_day, 1, "WHEN-DAY", ()),
    ("impossible date", control_impossible_date, 1, "WHEN-DATE", ()),
    ("clock out of range", control_bad_clock, 1, "WHEN-CLOCK", ()),
    ("active-timestamp shape", control_broken_shape, 1, "WHEN-SHAPE", ()),
    ("record lost its stamp", control_stamp_dropped, 1, "WHEN-COVERAGE", ()),
    ("record carries two stamps", control_stamp_duplicated, 1, "WHEN-COVERAGE", ()),
    ("every stamp stripped", control_all_stamps_gone, 2, "grades nothing", ()),
    ("graded file deleted", control_file_missing, 2, "CANNOT RUN", ()),
    ("indented prose quote excused", control_prose_quote, 0,
     "!2026-02-30", ()),
)

# The control roster is PINNED, not derived: a comparison cannot see its own
# coverage, so deleting a control must not leave `SELFTEST OK` printing a
# number that quietly dropped (chain_test_check.py's MERGE_ROSTER law).
EXPECTED_CONTROLS = 11


def selftest(root):
    """Prove each leg can fire, against copies. Returns 0 or raises Red."""
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d entries, the pin says %d — a control "
                        "vanished (or was added without the pin), so `SELFTEST OK` would "
                        "no longer mean every leg was run"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = os.path.join(root, "scripts", "chat_when_check.py")
    failures = []
    for name, mutation, expected_rc, expected_text, extra in CONTROLS:
        tmp, tree = _copy_workspace(root)
        try:
            mutation(tree)
            argv = [sys.executable, script, "--root", tree]
            proc = subprocess.run(argv, capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            # `!needle` = the text must be ABSENT. An exclusion can only be
            # graded on a copy that is red for some OTHER reason (the appended
            # lines break no leg), so the assertion is the problem text's
            # ABSENCE, never a green exit.
            negated = expected_text.startswith("!")
            needle = expected_text[1:] if negated else expected_text
            hit = needle not in out if negated else needle in out
            if proc.returncode == expected_rc and hit:
                print("  control %-28s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
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
