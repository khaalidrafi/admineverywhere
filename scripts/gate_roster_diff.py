#!/usr/bin/env python3
"""gate_roster_diff.py — the MACHINE merge gate vs the gate every seat runs.

AGENTS.md's LANDING GATE bullet and the seat laws say the gate `finalize` replays on
every merge and `python3 scripts/landing_gate.py` "run the same". That is a claim about
TWO WRITERS of one contract, and each side is green about itself:

  * `.github/scripts/gate.sh` — Lead-owned, invoked by the `test` job and the finalize
    "Landing gate" step. It exits 0 for whatever it runs and has never been asked how
    many legs it ran.
  * `scripts/landing_gate.py` — what a seat runs before it pushes, now pinned by
    roster and by count.

Eleventh-law applied to the last unpinned member of the family: the seat gate's roster
is graded against its own literal, and a literal is a second copy of the intent it
claims to check (measured three times in this repo — the twins, the parent gate, the
count legs). The machine gate is NOT a copy: a different author, a different language,
and the file that actually decides whether red work lands. So the two are diffed here,
command by command, and the source of truth is `MERGE_COMMANDS`, because
`landing_gate.py`'s merge legs EXECUTE that spec — seat behaviour, seat expectation and
machine behaviour become one compare instead of three prose claims.

Three doors this leg closes, each measured with a COPY of gate.sh (the Lead-owned file
is opened read-only and never written — see `--gate`):

  1. A DELETED LEG. Drop the `makemigrations` command and `gate.sh` still answers
     `GATE: GREEN`; the seat's own roster pin cannot see it, because it pins the seat
     file. Here it is RED naming `MISSING migrations`.
  2. A LEG THAT RUNS BUT CANNOT FAIL. Remove `|| FAIL=1` from one command and the leg
     still executes, still prints its output, and can no longer redden the gate — a
     red tree lands with the verdict leg still running. RED, naming the command.
  3. A CHANGED COMMAND. `plugin/tests` -> `plugin/tests/unit`, or a dropped
     `-p no:cacheprovider`, silently narrows what the merge gate proves. RED with both
     spellings, and an extra command the seat gate does not advertise is UNDECLARED.

Exit codes follow docs/DEVGUIDE.md FIFTH law, same as the other three twins:
0 = identical, 1 = DIVERGENCE (a real drift between the two gates), 2 = CANNOT RUN
(no gate.sh, a gate.sh this parser reads zero commands in, an unimportable
landing_gate — a tool that cannot read its input has no opinion about it).

Usage (from the repo root):
  python3 scripts/gate_roster_diff.py                     # the shipped gate.sh
  python3 scripts/gate_roster_diff.py --gate /tmp/x.sh    # a control copy
"""
import argparse
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GREEN, RED, CANNOT = 0, 1, 2
MACHINE_GATE = ".github/scripts/gate.sh"
PYTHON_LAUNCHERS = ("python", "python3", "python3.11", "python3.12", "python3.13")
# Lines that are shell plumbing, not a leg: variable assignment, flow control, echo.
NOT_A_LEG = ("set", "if", "then", "else", "fi", "echo", "exit", "cd", "#",
             "export", "FAIL=", "trap", "wait")


class CannotRun(Exception):
    pass


def load_spec():
    """MERGE_COMMANDS + MERGE_ROSTER, imported from the gate under test (never retyped).

    A copy of the expectation inside the checker would be the weakest pin this law was
    measured for: the harness and the gate could drift together and still agree.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import landing_gate as lg
    except Exception as exc:
        raise CannotRun("cannot import scripts/landing_gate.py to read the spec: %s"
                        % exc)
    for name in ("MERGE_COMMANDS", "MERGE_ROSTER", "ALLOWED_MACHINE_ABSENCE"):
        if not hasattr(lg, name):
            raise CannotRun("landing_gate.py carries no %s — the machine-gate contract "
                            "has no source of truth to diff against (rename it here in "
                            "the SAME commit)" % name)
    return lg


def parse_commands(text):
    """Every executed command in gate.sh, as (cwd, argv, captured, raw).

    The parse is shape-based, not line-based: a leg is any statement that is not shell
    plumbing. A command wrapped in `( cd X && cmd )` runs in X; the `|| FAIL=1` suffix is
    the failure capture, and a leg WITHOUT it still runs but cannot redden the gate.
    """
    legs = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or any(line.startswith(tok) for tok in NOT_A_LEG):
            continue
        # A leg is failure-captured ONLY when its own `||` branch writes FAIL. The
        # default is False: a bare command that exits non-zero and is never looked at
        # is door 2 — measured, and the first cut of this parser defaulted to True and
        # read GATE-IDENTICAL over a leg whose `|| FAIL=1` had been deleted.
        captured = False
        cmd = line
        if "||" in cmd:
            head, _, tail = cmd.partition("||")
            cmd = head.strip()
            captured = "FAIL=" in tail
        cwd = "."
        body = cmd
        if body.startswith("(") and body.endswith(")"):
            body = body[1:-1].strip()
        if body.startswith("cd "):
            dirpart, sep, rest = body.partition("&&")
            if not sep:
                raise CannotRun("gate.sh line `cd` is not followed by `&&` — cannot "
                                "tell which command it runs: %s" % line)
            cwd = dirpart[3:].strip()
            body = rest.strip()
        try:
            argv = shlex.split(body)
        except ValueError as exc:
            raise CannotRun("cannot tokenize a gate.sh command (%s): %s" % (exc, line))
        if not argv:
            continue
        legs.append({"cwd": cwd, "argv": argv, "captured": captured, "raw": line})
    return legs


def norm_argv(argv):
    """The command's IDENTITY: its interpreter stripped, its args in order.

    `python` vs `/usr/bin/python3.11` is not a drift in WHAT the gate proves — the seat
    gate re-spells argv[0] with `--python` on purpose — so only argv[1:] is compared and
    the interpreter is checked separately for being a python launcher at all.
    """
    return tuple(argv[1:])


def is_python(argv):
    head = os.path.basename(argv[0])
    return head in PYTHON_LAUNCHERS or head.startswith("python")


def spec_for(leg, lg):
    """Which advertised leg this command is, or None. cwd + argv[1:] must both match."""
    got = norm_argv(leg["argv"])
    for label, (cwd, argv) in lg.MERGE_COMMANDS.items():
        if leg["cwd"] == cwd and got == norm_argv(list(argv)):
            return label
    return None


def label_legs(legs, lg):
    labeled, unknown, uncaptured = [], [], []
    for leg in legs:
        if not is_python(leg["argv"]):
            unknown.append((leg, "not a python launcher: %s" % leg["argv"][0]))
            continue
        label = spec_for(leg, lg)
        if label is None:
            unknown.append((leg, "a command MERGE_COMMANDS does not advertise"))
            continue
        if not leg["captured"]:
            uncaptured.append(leg)
        labeled.append((label, leg))
    return labeled, unknown, uncaptured


def diff_roster(labeled, unknown, uncaptured, lg):
    """Ordered compare: identity, population, order and failure capture in one verdict."""
    owed = [l for l in lg.MERGE_ROSTER if l not in lg.ALLOWED_MACHINE_ABSENCE]
    got = [label for label, _ in labeled]
    findings = []
    missing = [l for l in owed if l not in got]
    if missing:
        findings.append("MISSING %s — the merge gate finalize replays would not run "
                        "leg(s) the seat gate advertises, and gate.sh still prints "
                        "GATE GREEN over their absence (an unpinned leg prints no "
                        "count to argue with)" % ", ".join(missing))
    if unknown:
        findings.append("UNDECLARED %s — gate.sh runs command(s) no seat is told about: "
                        "%s" % (len(unknown),
                                "; ".join("`%s` (%s)" % (" ".join(l["argv"]), why)
                                          for l, why in unknown)))
    if got and got != [l for l in owed if l in got]:
        findings.append("ORDER changed — gate.sh runs %s, MERGE_ROSTER declares %s. A "
                        "reordered gate can print a verdict after the leg that was "
                        "supposed to gate it" % (", ".join(got), ", ".join(owed)))
    if uncaptured:
        findings.append("FAILURE NOT CAPTURED %s — the leg still RUNS but `|| FAIL=1` "
                        "is gone, so its red can never redden the gate: %s"
                        % (len(uncaptured),
                           "; ".join("`%s`" % " ".join(l["argv"]) for l in uncaptured)))
    return owed, got, findings


def selfcheck(lg, log):
    """The seat file's own two views must agree before a verdict about the machine."""
    owed = [l for l in lg.MERGE_ROSTER if l not in lg.ALLOWED_MACHINE_ABSENCE]
    if sorted(lg.MERGE_COMMANDS) != sorted(owed):
        raise CannotRun("landing_gate.py is internally inconsistent: MERGE_ROSTER's "
                        "verdict legs (%s) are not MERGE_COMMANDS (%s) — the spec being "
                        "diffed is not the roster being pinned, so there is one "
                        "contract to compare" % (", ".join(owed),
                                                 ", ".join(sorted(lg.MERGE_COMMANDS))))
    log("spec       %d verdict leg(s) from scripts/landing_gate.py MERGE_COMMANDS (%s)"
        % (len(lg.MERGE_COMMANDS), ", ".join(owed)))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gate", default=MACHINE_GATE,
                    help="path to the machine gate (default: %s)" % MACHINE_GATE)
    opts = ap.parse_args(argv)

    def log(line):
        print(line)

    lg = load_spec()
    gate = ROOT / opts.gate
    if not gate.is_file():
        raise CannotRun("%s is missing — the machine merge gate has no input to read "
                        "(a deleted gate.sh is a merge that runs NOTHING and reports "
                        "nothing)" % opts.gate)
    text = gate.read_text()
    legs = parse_commands(text)
    if not legs:
        raise CannotRun("%s parsed to ZERO commands — this harness does not understand "
                        "its own input, so it has no verdict. Either gate.sh changed "
                        "shape or the parser did; do not treat this as green."
                        % opts.gate)
    selfcheck(lg, log)
    labeled, unknown, uncaptured = label_legs(legs, lg)
    owed, got, findings = diff_roster(labeled, unknown, uncaptured, lg)
    log("gate.sh    %d command(s): %s" % (len(legs), ", ".join(
        " ".join(l["argv"]) for l in legs)))
    if findings:
        print("ROSTER-DIVERGENCE — %s" % "; ".join(findings))
        return RED
    print("ROSTER-IDENTICAL — %d/%d verdict leg(s) in the same order, each with its "
          "failure captured (%s); gate.sh and scripts/landing_gate.py execute the same "
          "commands, so \"the landing gate runs the same\" is measured, not asserted"
          % (len(got), len(owed), ", ".join(got)))
    return GREEN


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        sys.exit(CANNOT)
    except Exception as exc:  # a crash is not a verdict: 2, never 1
        print("CANNOT RUN — harness failure %s: %s" % (type(exc).__name__, exc))
        sys.exit(CANNOT)
