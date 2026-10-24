#!/usr/bin/env python3
"""queue_replay_check.py — can a queued branch's verdict be attributed to ITS content?

WHY (measured 2026-10-24, seat software-engineer, run 40117823054/40118604637 window).
A REJECTED branch stays queued for re-review by review law, and the re-review runs in a
container whose checkout is the branch's OWN tree. So the branch re-grades itself with
the harnesses IT carries — and every branch cut before a checker repair keeps re-firing
the reds that repair removed on main. ai/turn-20261024-1632 is the proof: rejected three
times, and on its tip `python3 scripts/chain_test_check.py` prints 7 CHAT-STRUCTURE reds,
of which 6 are folded chat headers that main ALREADY repaired (5147249) and 1 is the
column-0 prose line that main's grammar fix (5acbc81) no longer reads as a drawer field.
Measured in a throwaway clone: that branch's delta over main today is purely additive
(TEAM-CHAT +57/-0, CHAIN-TEST +11/-0), it merges CLEAN, its merged tree prints
CHAT-STRUCTURE 0 and 158 headlines = 158 drawers = 158 closes, and the only reds left are
the two families the Lead has already ruled merge-as-prefix noise. Two of its seven
rejection reasons are therefore about the base, not the branch — and 8 of the 9 queued
branches carry that pre-fix checker.

This harness turns that reading into a command. It grades the QUEUE, read-only, per
branch:

  LAW      — what the AUTHOR owns: deletions inside the one chat (append-only law),
             edits to Lead-owned files, harness scratch committed into the tree.
  REPLAY   — what the MERGER owns: does the branch still merge onto main cleanly (a
             conflict is a Lead union-merge cost, never a false claim about the author,
             so it prints as COST, not RED).
  VANTAGE  — what the REVIEWER owns: is the checker on the branch the checker main ships,
             and does the branch's chat tree carry orphan drawers main no longer carries?
             Both equal -> a verdict from that tree grades the same thing main grades.
             Either differs -> red, naming the repairs the branch predates and the repair
             door (replay the branch onto main, or grade the merge, not the tip).
  BASE     — how far main moved under the branch (the size of that predating window).

Verdicts follow house law (docs/DEVGUIDE.md *EIGHTH* + *ELEVENTH*): 0 = every claim holds,
1 = a claim is false, 2 = CANNOT RUN (no queue, no main ref, a chat blob that will not
read — the harness never wears a tree it did not measure as red). The leg roster is
pinned, so a vanished leg is a refusal, not a quieter green, and the queue population is
pinned against the refs actually discovered, so a truncated scan says "grades less than it
claims" instead of printing a smaller red list.

  python3 scripts/queue_replay_check.py                  # grade the live queue
  python3 scripts/queue_replay_check.py --main ai/main   # grade against another ref
  python3 scripts/queue_replay_check.py --expect 9       # pin how many branches are due
  python3 scripts/queue_replay_check.py --selftest       # controls, every leg able to fail

Deliberately NOT named `*_diff.py`: that glob IS the landing gate's twin roster
(`scripts/landing_gate.py` EXPECTED_TWINS cross-checks every `scripts/*_diff.py` on disk
against the legs it runs), and this grades the QUEUE, not a pair of cross-language
artifacts — same ruling as scripts/chain_test_check.py and scripts/chain_slot_check.py.
"""

import argparse
import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_REF = "ai/main"
QUEUE_GLOB = "ai/turn-"
CHAT = "agent-team/TEAM-CHAT.org"
CHECKER = "scripts/chain_test_check.py"
LEAD_OWNED = (".github/workflows/", ".github/scripts/", "agent-team/TEAM-CONTROL.org", ".gitattributes")
SCRATCH_RE = re.compile(r"(\.git/)?\.turn-[a-z-]*\.txt$|\.turn-inside\.sh$|\.turn-review\.txt$")

# The one chat is append-only law, so a branch-authored deletion inside it is a claim
# about the AUTHOR. Everywhere else a deletion is legitimate edits to the branch's own
# work, and the numstat simply reports it.
DELETION_LAW_FILES = (CHAT,)

EXPECTED_LEGS = 3
LEGS = ("LAW", "REPLAY", "VANTAGE")

# Controls are mutations of a MEASURED branch record, not of the tree: the legs read
# git objects that only a real repo carries, so the selftest feeds each leg the shape of
# input it is supposed to refuse and asserts the refusal names the right claim. The
# chat-side mutation runs the REAL scanner (imported from the checker it mirrors), so the
# orphan rule is not re-spelled here and cannot drift.
EXPECTED_CONTROLS = 10


def run_git(args, cwd=None):
    proc = subprocess.run(("git",) + tuple(args), cwd=cwd or ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


SLOT_FILE = os.path.join(ROOT, "agent-team", "TEAM-CONTROL.org")


def read_slot():
    """The branch the register currently holds (agent-team/TEAM-CONTROL.org, READ ONLY).

    Seats may read and cite that file, never write it — and this harness only ever
    opens it, so the queue's one actionable slot is known without editing anything.
    """
    try:
        with open(SLOT_FILE, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\#\+PENDING-REVIEW:\s*(?:branch=)?(\S+)", line)
                if m:
                    branch = m.group(1).strip()
                    return branch if branch and branch != "none" else None
    except OSError:
        return None
    return None


def resolve(ref):
    rc, out, _ = run_git(("rev-parse", "--verify", "-q", ref))
    return out.strip() if rc == 0 else None


def discover_queue(main):
    """Every ai/turn-* ref whose tip is not already inside `main` — the queue.

    Annotated tags, husks and merged branches are not queue members: the first because
    it is not a branch, the rest because their tip is an ancestor of main and a reviewer
    has nothing left to grade. Husks (a ref with zero content delta over main) ARE
    returned, because "the queue holds an empty branch" is a fact the Lead acts on
    (prune), and a scan that hid them would under-report the queue.
    """
    rc, out, _ = run_git(("for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin"))
    if rc != 0:
        raise CannotRun("git for-each-ref failed: %s" % out.strip())
    names = set()
    for line in out.splitlines():
        short = line.strip()
        if short.startswith("origin/"):
            short = short[len("origin/"):]
        if short.startswith(QUEUE_GLOB) and not short.endswith("/HEAD"):
            names.add(short)
    queue = []
    for name in sorted(names):
        tip = resolve("origin/%s" % name) or resolve(name)
        if not tip:
            continue
        rc, _, _ = run_git(("merge-base", "--is-ancestor", tip, main))
        if rc == 0:
            continue
        rc, base, _ = run_git(("merge-base", main, tip))
        queue.append({"branch": name, "tip": tip, "base": base.strip() if rc == 0 else None})
    return queue


def numstat(main, tip):
    """Additions, deletions and the touched file list of the branch's OWN delta."""
    rc, out, _ = run_git(("diff", "--numstat", "%s...%s" % (main, tip)))
    if rc != 0:
        raise CannotRun("git diff %s...%s failed: %s" % (main, tip, out.strip()))
    adds = dels = 0
    files = []
    per_file = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], "\t".join(parts[2:])
        a_n = 0 if a == "-" else int(a)
        d_n = 0 if d == "-" else int(d)
        adds += a_n
        dels += d_n
        files.append(path)
        per_file[path] = (a_n, d_n)
    return adds, dels, files, per_file


def blob_hash(ref, path):
    rc, out, _ = run_git(("show", "%s:%s" % (ref, path)))
    if rc != 0:
        return None
    return hashlib.sha256(out.encode("utf-8", "replace")).hexdigest(), out


def measure(entry, main, slot):
    """Everything the legs read, gathered once per branch (the legs stay pure)."""
    tip = entry["tip"]
    adds, dels, files, per_file = numstat(main, tip)
    deleted_in_law = {p: per_file[p][1] for p in DELETION_LAW_FILES if per_file.get(p, (0, 0))[1] > 0}
    lead_edits = [p for p in files if any(p == o or p.startswith(o) for o in LEAD_OWNED)]
    scratch = [p for p in files if SCRATCH_RE.search(p)]

    rc, out_mt, _ = run_git(("merge-tree", "--write-tree", "--name-only", "--no-messages", main, tip))
    merge_clean = rc == 0
    # --name-only --no-messages prints the merged tree OID, then one conflicted path
    # per line — the informational "Auto-merging" chatter would otherwise be read as
    # a conflict, which is exactly the false-positive class this harness exists to kill.
    conflicts = [ln.strip() for ln in out_mt.splitlines()[1:] if ln.strip()] if not merge_clean else []

    own = blob_hash(tip, CHECKER)
    theirs = blob_hash(main, CHECKER)
    checker_same = own is not None and theirs is not None and own[0] == theirs[0]

    own_chat = blob_hash(tip, CHAT)
    main_chat = theirs_chat = blob_hash(main, CHAT)
    orphans_tip = orphans_main = None
    if own_chat is not None and theirs_chat is not None:
        orphans_tip = len(scan_orphan_drawers(own_chat[1])[0])
        orphans_main = len(scan_orphan_drawers(theirs_chat[1])[0])

    rc_n, ahead_txt, _ = run_git(("rev-list", "--count", "%s..%s" % (tip, main)))
    base_lag = int(ahead_txt.strip()) if rc_n == 0 and ahead_txt.strip().isdigit() else None

    return {
        "branch": entry["branch"],
        "due": entry["branch"] == slot,
        "tip": tip,
        "base": entry["base"],
        "adds": adds,
        "dels": dels,
        "nfiles": len(files),
        "deleted_in_law": deleted_in_law,
        "lead_edits": lead_edits,
        "scratch": scratch,
        "merge_clean": merge_clean,
        "conflicts": conflicts,
        "checker_same": checker_same,
        "orphans_tip": orphans_tip,
        "orphans_main": orphans_main,
        "base_lag": base_lag,
    }


class CannotRun(Exception):
    pass


def leg_law(b):
    """What the AUTHOR owns: a claim the branch itself made false."""
    reds = []
    for path, n in sorted(b["deleted_in_law"].items()):
        reds.append("LAW %s: %d deleted line(s) inside %s — the one chat is append-only law"
                    % (b["branch"], n, path))
    for path in b["lead_edits"]:
        reds.append("LAW %s: edits the Lead-owned %s — seats read and cite it, never write it"
                    % (b["branch"], path))
    for path in b["scratch"]:
        reds.append("LAW %s: commits harness scratch %s — another seat's session state lands in history"
                    % (b["branch"], path))
    return reds


def leg_replay(b):
    """What the MERGER owns. A conflict is a union-merge cost, not a false claim."""
    cost = []
    if not b["merge_clean"]:
        cost.append("REPLAY %s: does NOT merge onto %s cleanly (%s) — needs the Lead's union-merge, "
                    "not another review of the same tip"
                    % (b["branch"], MAIN_REF, ", ".join(b["conflicts"][:4]) or "conflict files unresolved"))
    if b["adds"] == 0 and b["dels"] == 0:
        cost.append("REPLAY %s: zero content delta over %s — a husk; the queue item is a prune, "
                    "not a review" % (b["branch"], MAIN_REF))
    return cost


def leg_vantage(b):
    """What the REVIEWER owns: does the branch's tree grade what main grades?"""
    reds = []
    if b["orphans_tip"] is None or b["orphans_main"] is None:
        raise CannotRun("VANTAGE %s: %s unreadable on the branch or on %s — the orphan scan has no input"
                        % (b["branch"], CHAT, MAIN_REF))
    if not b["checker_same"]:
        reds.append("VANTAGE %s: ships a %s main no longer ships — a verdict produced on this tree "
                    "grades the pre-fix checker, so its %s findings are not attributable to this branch "
                    "(main moved %s commit(s) over its base)"
                    % (b["branch"], CHECKER, CHECKER, b["base_lag"] if b["base_lag"] is not None else "?"))
    if b["orphans_tip"] > b["orphans_main"]:
        reds.append("VANTAGE %s: its chat tree carries %d orphan drawer line(s) while %s carries %d — "
                    "%d of them are folds %s already repaired, and re-reviewing this tip re-fires them"
                    % (b["branch"], b["orphans_tip"], MAIN_REF, b["orphans_main"],
                       b["orphans_tip"] - b["orphans_main"], MAIN_REF))
    return reds


def grade(branches):
    """Severity follows WHO can act: the branch the register holds is DUE and any finding
    on it is RED (it is the one costing the chain this minute); every other unmerged ref
    is BACKLOG — the same facts, named, for the Lead's replay-or-prune pass."""
    reds, costs, backlog = [], [], []
    for b in branches:
        found = leg_law(b) + leg_vantage(b)
        cost = leg_replay(b)
        costs += cost
        if b["due"]:
            reds += found
        else:
            backlog += found
    return reds, costs, backlog


def report(branches, reds, costs, backlog, main, slot):
    print("queue     %d unmerged %s* branch(es) against %s; register holds %s"
          % (len(branches), QUEUE_GLOB, main, slot or "nobody"))
    for b in branches:
        verdict = "STALE" if (not b["checker_same"] or (b["orphans_tip"] or 0) > (b["orphans_main"] or 0)) else "CURRENT"
        print("  %-28s %s..%s  +%d/-%d over %d file(s)  base lag %s  checker %s  orphans %s/%s  merges %s  -> %s"
              % (b["branch"], (b["base"] or "?")[:7], b["tip"][:7], b["adds"], b["dels"], b["nfiles"],
                 "?" if b["base_lag"] is None else b["base_lag"],
                 "same" if b["checker_same"] else "DIFFERS",
                 b["orphans_tip"], b["orphans_main"],
                 "clean" if b["merge_clean"] else "CONFLICT",
                 verdict))
    for line in costs:
        print("    COST  " + line)
    for line in backlog:
        print("    BACKLOG  " + line)
    if reds:
        print("RED —")
        for line in reds:
            print("    " + line)
        return 1
    print("QUEUE REPLAY OK — the DUE branch (%s) is additive-legal and grades with the "
          "checker and the chat state %s ships; %d backlog ref(s) reported above"
          % (slot or "empty slot", main, len(branches) - 1))
    return 0


# --------------------------------------------------------------------------- controls

def sample_branch(**over):
    """One measured record, shaped like real 1632 output, for the controls to mutate."""
    base = {
        "branch": "ai/turn-20261024-1632",
        "tip": "f" * 40,
        "base": "0" * 40,
        "adds": 68,
        "dels": 0,
        "nfiles": 2,
        "deleted_in_law": {},
        "lead_edits": [],
        "scratch": [],
        "merge_clean": True,
        "conflicts": [],
        "checker_same": True,
        "orphans_tip": 0,
        "orphans_main": 0,
        "base_lag": 24,
        "due": True,
    }
    base.update(over)
    return base


def synthetic_chat(with_prose_line):
    """Two intact entries; optionally the column-0 prose line that quotes the drawer
    order — the exact shape the 1632 TEST-T2 entry contains, and the shape the grammar
    fix (main 5acbc81) stopped reading as a field."""
    head = (
        "* MSG relief-engineer -> @lead :dispatch:\n"
        ":PROPERTIES:\n:FROM: relief-engineer\n:TO: lead\n:KIND: dispatch\n"
        ":WHEN: [2026-10-24 Sat 16:38 UTC]\n:END:\n"
        "  ONE concrete improvement noticed, indented as the FORMAT LAW requires.\n\n"
    )
    tail = (
        "* MSG relief-engineer -> @lead :report:\n"
        ":PROPERTIES:\n:FROM: relief-engineer\n:TO: lead\n:KIND: report\n"
        ":WHEN: [2026-10-24 Sat 16:40 UTC]\n:END:\n  RESULT: DONE\n"
    )
    prose = ":PROPERTIES:, :WHEN:, :FROM:, :TO:, :KIND:, :END:.\n"
    # the fold shape: the headline and the four drawer HEADER lines are what the
    # three-way merge ate, so only the :WHEN:/:END: tail survives at column 0
    folded = ":WHEN: [2026-10-24 Sat 16:41 UTC]\n:END:\n  body\n"
    if with_prose_line == "prose":
        return head + prose + tail
    if with_prose_line == "fold":
        return head + folded
    return head + tail


CONTROLS = [
    ("queue clean", "clean", {}, []),
    ("law: chat deletion", "red", {"deleted_in_law": {CHAT: 12}}, "LAW"),
    ("law: Lead-owned edit", "red", {"lead_edits": [".github/scripts/turn_segment.sh"]}, "LAW"),
    ("law: scratch committed", "red", {"scratch": [".turn-review.txt"]}, "LAW"),
    ("vantage: stale checker", "red", {"checker_same": False}, "VANTAGE"),
    ("vantage: repaired folds", "red", {"orphans_tip": 6, "orphans_main": 0}, "VANTAGE"),
    ("replay: conflict cost", "cost", {"merge_clean": False, "conflicts": [CHAT]}, "REPLAY"),
    ("replay: husk", "cost", {"adds": 0, "dels": 0}, "REPLAY"),
    ("vantage: unreadable chat", "cannot", {"orphans_tip": None, "orphans_main": 0}, "VANTAGE"),
    # who can act decides the severity: the SAME stale-checker fact is RED on the branch
    # the register holds and BACKLOG on a ref nobody is about to review. Without this row
    # the harness would either flood every run with ancient refs or hide them entirely.
    ("severity: due vs backlog", "grade", {}, "VANTAGE"),
]


def selftest():
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d entries, the pin says %d — a control "
                        "vanished and SELFTEST OK would mean less than it claims"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    if len(LEGS) != EXPECTED_LEGS:
        raise CannotRun("LEGS lists %d leg(s), the pin says %d — a leg vanished"
                        % (len(LEGS), EXPECTED_LEGS))
    for name, kind, over, tag in CONTROLS:
        b = sample_branch(**over)
        if kind == "cannot":
            try:
                leg_vantage(b)
            except CannotRun as exc:
                print("  [x] %-24s CANNOT RUN: %s" % (name, str(exc)[:78]))
                continue
            print("  [ ] %-24s graded a tree it could not read instead of refusing" % name)
            return 1
        if kind == "grade":
            due = sample_branch(checker_same=False)
            late = sample_branch(branch="ai/turn-20261021-0011", due=False, checker_same=False)
            r, _c, bk = grade([due, late])
            if len(r) != 1 or len(bk) != 1 or not bk[0].startswith(tag):
                print("  [ ] %-24s severity did not route: %d red, %d backlog" % (name, len(r), len(bk)))
                return 1
            print("  [x] %-24s DUE finding is RED, the identical BACKLOG fact is not: %s"
                  % (name, r[0][:60]))
            continue
        reds = leg_law(b) + leg_vantage(b)
        costs = leg_replay(b)
        if kind == "clean":
            if reds or costs:
                print("  [ ] %-24s the baseline record is not clean: %s" % (name, (reds + costs)[0][:70]))
                return 1
            print("  [x] %-24s no red, no cost — the controls mutate a green record" % name)
            continue
        if kind == "red":
            if not reds:
                print("  [ ] %-24s printed no red — the leg cannot fail" % name)
                return 1
            if not any(line.startswith(tag) for line in reds):
                print("  [ ] %-24s red came from the wrong leg: %s" % (name, reds[0][:70]))
                return 1
            print("  [x] %-24s %s" % (name, reds[0][:88]))
            continue
        if not costs:
            print("  [ ] %-24s printed no COST — the merger's view is blind" % name)
            return 1
        if any(line.startswith(tag) for line in reds):
            print("  [ ] %-24s scored a merge cost as a claim about the author: %s" % (name, reds[0][:70]))
            return 1
        print("  [x] %-24s COST only: %s" % (name, costs[0][:80]))
    folded = len(scan_orphan_drawers(synthetic_chat("fold"))[0])
    prose = len(scan_orphan_drawers(synthetic_chat("prose"))[0])
    clean = len(scan_orphan_drawers(synthetic_chat("clean"))[0])
    print("  scanner replay: folded header -> %d orphan(s), prose quoting the drawer order -> "
          "%d orphan(s), intact entries -> %d orphan(s)" % (folded, prose, clean))
    if folded != 2 or prose != 0 or clean != 0:
        print("  [ ] the imported orphan rule no longer matches the two shapes this harness "
              "was written for — it must see a fold and must NOT see the prose line")
        return 1
    print("SELFTEST OK — %d control row(s) over %d leg(s) (%s), each landing its own verdict"
          % (len(CONTROLS), len(LEGS), ", ".join(LEGS)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--main", default=MAIN_REF, help="the ref the queue is measured against")
    parser.add_argument("--expect", type=int, default=None, help="pin how many branches the queue must hold")
    parser.add_argument("--selftest", action="store_true", help="prove every leg can fail")
    args = parser.parse_args(argv)

    global scan_orphan_drawers
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from chain_test_check import scan_orphan_drawers  # the orphan rule, never re-spelled
    except Exception as exc:
        print("CANNOT RUN — the checker's own orphan scan is not importable (%s), so this "
              "harness would grade a rule of its own invention" % exc)
        return 2

    if args.selftest:
        try:
            return selftest()
        except CannotRun as exc:
            print("CANNOT RUN — %s" % exc)
            return 2

    main_sha = resolve(args.main) or resolve("origin/" + args.main)
    if not main_sha:
        print("CANNOT RUN — %s does not resolve; the queue has nothing to be measured against" % args.main)
        return 2
    slot = read_slot()
    try:
        queue = discover_queue(main_sha)
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        return 2
    if not queue:
        print("CANNOT RUN — zero unmerged %s* refs: either the queue drained or the scan lost it. "
              "A queue check that measures nothing never prints red." % QUEUE_GLOB)
        return 2
    if args.expect is not None and len(queue) != args.expect:
        print("CANNOT RUN — the scan found %d queued branch(es), --expect pins %d: this harness is "
              "no longer reading the queue it claims to grade" % (len(queue), args.expect))
        return 2
    try:
        branches = [measure(entry, main_sha, slot) for entry in queue]
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        return 2
    if len(LEGS) != EXPECTED_LEGS:
        print("CANNOT RUN — LEGS lists %d leg(s), the pin says %d: a leg vanished and the report "
              "would silently claim less coverage than it grades" % (len(LEGS), EXPECTED_LEGS))
        return 2
    reds, costs, backlog = grade(branches)
    return report(branches, reds, costs, backlog, args.main, slot)


if __name__ == "__main__":
    sys.exit(main())
