#!/usr/bin/env python3
"""Which turn refs still hold work, and which are debt the repo can delete — as ONE command.

WHY this exists (measured on the delivered tree, 2026-10-26, seat platform-engineer).
Every chain turn leaves a branch ref behind, and `origin/` carries 47 of them. The Lead
prunes them by hand, one beat at a time, and the hand measure is a `git rev-list` question
the chain cannot ask itself:

  * 1236 / 2307 / 0050 / 1929 were pruned as "the tip is an ancestor of main, 0 unique
    commits" — proved per branch, in prose, in the control file.
  * 2024 was pruned on a premise (its fold-repair target had already been re-headed six
    minutes before the branch was cut) the Lead had to reconstruct.
  * 1946 is the expensive one: SQUASH-landed, so no ancestry test can see it, and the
    register keeps re-parking it — the tail of REVIEW-LOG.org is nine verdicts on that
    one ref (seven `approved+gate-conflict-branch-kept`, one `:review-missing:`, one
    `:rejected:` at 90eeb58), all spent on a ref whose payload main already carries.

`review_preflight_check.py` asks "is a LANE worth paying" and answers for the QUEUE only:
its `queue_branches()` deliberately drops every already-merged ref, and its landed-echo leg
applies to the register's single slot. Nothing in the family answers the adjacent question
— for EVERY turn ref, does it hold anything main lacks? — which is the sentence the prune
law is written in. So this harness dispositions the whole population and reads the
Lead-owned register as data.

FIVE LEGS to produce the dispositions, ONE to grade the register against them:

  ref-population  every ref named `ai/turn-*` (the remote wins over a seat's local copy of
                  the same branch, exactly as the shipped queue reader keys them), plus a
                  COVERAGE door: the merged set this harness derives by ancestry and the
                  queued set `queue_branches()` derives by ahead-count must partition the
                  population EXACTLY. Two readers of one ref set disagreeing is CANNOT
                  RUN, never a shorter list — a comparison cannot see its own coverage
                  (*ELEVENTH harness law*).
  merged-ancestry the tip is an ancestor of main -> `PRUNE-READY MERGED` (1236 / 2307 /
                  0050 / 1929).
  landing-record  the tip is NOT an ancestor, but main's history carries a landing record
                  for the branch that is not older than the tip -> `PRUNE-READY RECORD`,
                  read with the shipped `landing_records()` / `echo_record()` imported
                  from the preflight, never re-spelled. That is the squash class no
                  ancestry test sees, and the ordering rule keeps a tip NEWER than its
                  record queued as a post-landing rework.
  content-landed  no record: every line the ref ADDS over its own merge base is already in
                  main's copy of that file, it removes no line main still carries, and it
                  adds no file main lacks -> `PRUNE-READY CONTENT`. The refusals are
                  deliberate: a removal is content main has NOT accepted, a file main
                  does not carry is content this read cannot confirm, and a binary delta
                  has no lines to compare — each lands as `KEEP` with the reason printed.
  unlanded        anything else -> `KEEP`, naming the file(s) and what main lacks.
  slot-disposition  the register's `#+PENDING-REVIEW` branch graded against the
                  dispositions above. The register parking a ref this harness calls
                  PRUNE-READY is the stale-echo class LIVE in the control file, and it is
                  the only RED this harness issues — ref debt is a queue the Lead clears
                  at leisure, not a defect.

Read-only over git: no `merge-tree`, no ref written, no verdict issued, no file deleted —
deletion is the Lead's prune law; this names candidates.

Usage: python3 scripts/ref_prune_check.py [--main REF] [--repo DIR] [--branch NAME]
       [--since YYYYMMDD] [--selftest]
"""

import argparse
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAIN_REF = "origin/ai/main"
BRANCH_PREFIX = "ai/turn-"

# The leg roster is this harness's own expectation (review_preflight_check's LEG_ROSTER
# law): the run must execute exactly these, in this order, or its dispositions do not
# cover what its docstring claims.
LEG_ROSTER = ("ref-population", "merged-ancestry", "landing-record", "content-landed",
              "unlanded", "slot-disposition")
EXPECTED_LEGS = 6

DISPOSITIONS = ("PRUNE-READY MERGED", "PRUNE-READY RECORD", "PRUNE-READY CONTENT", "KEEP")


class CannotRun(Exception):
    pass


def _rpc():
    """The shipped queue / register / landing-record reads, imported — never re-spelled.

    Forking the landing-verb grammar or the register line into this file would put two
    readers of one class in the tree that can drift (the EIGHTH law's whole point), and
    the value here is that a squash landing is named by the SAME grammar that caught the
    1946 slot.
    """
    path = os.path.join(ROOT, "scripts", "review_preflight_check.py")
    if not os.path.exists(path):
        raise CannotRun("scripts/review_preflight_check.py is missing — the queue, "
                        "register and landing-record reads this harness grades against "
                        "live there")
    spec = importlib.util.spec_from_file_location("review_preflight_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        for name in ("git", "resolve", "show", "queue_branches", "pending_slot",
                     "landing_records", "echo_record", "branch_tail"):
            getattr(mod, name)
    except Exception as exc:
        raise CannotRun("scripts/review_preflight_check.py cannot be imported: %s" % exc)
    return mod


# ------------------------------------------------------------------ git plumbing
def merge_base(rpc, repo, main_sha, sha):
    rc, out = rpc.git(repo, "merge-base", main_sha, sha)
    if rc != 0:
        return None
    return out.strip() or None


def is_ancestor(rpc, repo, sha, main_sha):
    rc, _out = rpc.git(repo, "merge-base", "--is-ancestor", sha, main_sha)
    return rc == 0


def name_status(rpc, repo, base, sha):
    """{path: A|M|D|X} for the ref's own delta; X = a move/copy this read cannot follow."""
    rc, out = rpc.git(repo, "diff", "--name-status", base, sha)
    if rc != 0:
        raise CannotRun("git diff --name-status %s..%s failed" % (base[:7], sha[:7]))
    status = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        code = parts[0][0]
        status[parts[-1]] = code if code in ("A", "M", "D") else "X"
    return status


def line_delta(rpc, repo, base, sha):
    """{path: (added, removed)} read from a -U0 diff.

    A file with no `+++ b/<path>` header — a binary change — is absent from the result,
    and the caller must NOT call that "nothing to report".
    """
    rc, out = rpc.git(repo, "diff", "--unified=0", base, sha)
    if rc != 0:
        raise CannotRun("git diff --unified=0 %s..%s failed" % (base[:7], sha[:7]))
    deltas = {}
    current = None
    for line in out.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = target[2:] if target.startswith("b/") else None
            if current is not None:
                deltas.setdefault(current, ([], []))
            continue
        if line.startswith("--- ") or line.startswith("@@") or line.startswith("diff ") \
                or line.startswith("index ") or line.startswith("Binary files"):
            continue
        if current is None:
            continue
        if line.startswith("+"):
            deltas[current][0].append(line[1:])
        elif line.startswith("-"):
            deltas[current][1].append(line[1:])
    return deltas


def content_problems(rpc, repo, main_sha, base, sha):
    """Why this ref is NOT content-landed — or [] when main already carries every line."""
    status = name_status(rpc, repo, base, sha)
    deltas = line_delta(rpc, repo, base, sha)
    if not status:
        return ["its delta over the merge base touches no file at all — nothing can be "
                "confirmed landed, so the ref is not called prunable on an empty read"]
    problems = []
    added_total = 0
    for path, code in sorted(status.items()):
        if code in ("D", "X"):
            problems.append("%s: the ref %s it — a removal or a move is content main has "
                            "not accepted" % (path, "deletes" if code == "D"
                                              else "renames/retypes"))
            continue
        main_text = rpc.show(repo, main_sha, path)
        if main_text is None:
            problems.append("%s: main carries no such file" % path)
            continue
        if path not in deltas:
            problems.append("%s: no line-level delta to read (a binary change) — the "
                            "compare is blind to it" % path)
            continue
        added, removed = deltas[path]
        added_total += len(added)
        main_lines = set(main_text.splitlines())
        missing = [ln for ln in added if ln not in main_lines]
        stranded = [ln for ln in removed if ln in main_lines]
        if missing:
            problems.append("%s: %d added line(s) main does not carry (first: %.70s)"
                            % (path, len(missing), missing[0].strip()))
        if stranded:
            problems.append("%s: removes %d line(s) main still carries (first: %.70s)"
                            % (path, len(stranded), stranded[0].strip()))
    return problems


def added_line_count(rpc, repo, base, sha):
    deltas = line_delta(rpc, repo, base, sha)
    return sum(len(added) for added, _removed in deltas.values())


# ------------------------------------------------------------------------- grading
def turn_refs(rpc, repo, main, main_sha, prefix, since):
    """EVERY turn ref, merged ones included — the population queue_branches drops.

    The remote-wins keying is the shipped reader's (a seat's workspace carries one branch
    twice and the chain reviews what was PUSHED); only the ahead-count filter is removed,
    because a prunable ref is exactly the kind that reader excludes.
    """
    rc, out = rpc.git(repo, "for-each-ref", "--format=%(refname:short)")
    main_tail = main.split("/")[-1]
    by_tail = {}
    for short in sorted(out.split()):
        remote = short.startswith("origin/")
        tail = short.split("/", 1)[-1] if remote else short
        if tail == main or tail == main_tail or not tail.startswith(prefix):
            continue
        if since and tail[len(prefix):][:8] < since:
            continue
        sha = rpc.resolve(repo, short)
        if sha is None:
            continue
        if not remote and tail in by_tail:
            continue
        by_tail[tail] = (short, sha)
    return [(tail, by_tail[tail][0], by_tail[tail][1]) for tail in sorted(by_tail)]


def grade(repo=ROOT, main=MAIN_REF, only=None, since=None):
    rpc = _rpc()
    main_sha = rpc.resolve(repo, main)
    if main_sha is None:
        raise CannotRun("main ref %s does not resolve in %s — no ref can be called "
                        "prunable against a main nobody can read" % (main, repo))
    legs = []

    population = turn_refs(rpc, repo, main, main_sha, BRANCH_PREFIX, since)
    if only:
        want = rpc.branch_tail(only)
        population = [row for row in population if row[0] == want]
        if not population:
            raise CannotRun("--branch %s is not in the turn-ref population — grading an "
                            "absent ref would report missing work as prunable work" % only)
    if not population:
        raise CannotRun("no %s* refs resolve in %s — a prune read over zero refs is "
                        "CANNOT RUN, never a clean queue" % (BRANCH_PREFIX, repo))
    tails = [row[0] for row in population]
    if len(tails) != len(set(tails)):
        raise CannotRun("the turn-ref population names one branch twice — remote-wins "
                        "keying broke, so a ref would be dispositioned twice")
    legs.append("ref-population")

    # The coverage door, in both directions.
    _queued_sha, queued_rows = rpc.queue_branches(repo, main, BRANCH_PREFIX, since)
    # branch_tail() is the shipped normaliser: a queue row's refname is the SHORT ref
    # ("origin/ai/turn-X"), so a naive split("/")[-1] would key "turn-X" and silently
    # disagree with the population's own "ai/turn-X" keys — a coverage door that fires on
    # its own bookkeeping is worse than no door.
    queued_tails = set(rpc.branch_tail(row[0]) for row in queued_rows)
    if only:
        queued_tails = set(t for t in queued_tails if t == rpc.branch_tail(only))
    merged_rows, queued_set = [], []
    for tail, short, sha in population:
        ancestor = is_ancestor(rpc, repo, sha, main_sha)
        in_queue = tail in queued_tails
        if ancestor == in_queue:
            raise CannotRun("%s: ancestry says %s but the shipped queue reader says %s — "
                            "two readers of one ref disagree, so no disposition here can "
                            "be trusted and pruning on a disagreement deletes work"
                            % (tail, "merged" if ancestor else "queued",
                               "queued" if in_queue else "merged"))
        (queued_set if in_queue else merged_rows).append((tail, short, sha))
    if len(merged_rows) + len(queued_set) != len(population):
        raise CannotRun("merged %d + queued %d != population %d — a ref fell out of both "
                        "reads and would be reported as neither debt nor work"
                        % (len(merged_rows), len(queued_set), len(population)))
    legs.append("merged-ancestry")

    slot = rpc.pending_slot(repo, main)
    slot_tail = rpc.branch_tail((slot or {}).get("branch", ""))

    records = rpc.landing_records(repo, main_sha)
    rows = []
    prunable = {}
    graded = set()

    # The LIVE guard: the ref this workspace is standing on is never named prunable.
    # A freshly cut turn branch IS an ancestor of main (its tip equals it), so without
    # this rule the harness would hand the chain a delete list containing the ground it
    # runs on — and the chain's own seat checks do exactly that by instruction.
    live = ""
    rc, head = rpc.git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc == 0:
        live = rpc.branch_tail(head.strip())

    def classify(tail, klass, why):
        graded.add(tail)
        if tail == live:
            rows.append((tail, "KEEP",
                         "LIVE — the current HEAD of this workspace is the ref; naming it "
                         "PRUNE-READY would put the ground the chain runs on into a delete "
                         "list, so the disposition is refused regardless of ancestry"))
            return
        prunable[tail] = klass
        rows.append((tail, "PRUNE-READY " + klass, why))

    for tail, _short, sha in merged_rows:
        classify(tail, "MERGED",
                 "tip %s is an ancestor of %s — the ref carries no commit main lacks"
                 % (sha[:7], main))

    rework = []
    for tail, short, sha in queued_set:
        record = rpc.echo_record(repo, sha, tail, records)
        if record is not None:
            classify(tail, "RECORD",
                     "swallowed by landing record %s '%s' (its tip %s is not newer) — the "
                     "squash class no ancestry test can see"
                     % (record[0][:7], record[2][:60], sha[:7]))
        elif records.get(tail) is not None:
            rework.append((tail, short, sha, records[tail]))
    legs.append("landing-record")

    for tail, _short, sha, record in rework:
        graded.add(tail)
        rows.append((tail, "KEEP",
                     "a landing record exists (%s) but it PREDATES the tip %s — "
                     "post-landing rework, genuinely queued" % (record[0][:7], sha[:7])))

    for tail, _short, sha in queued_set:
        if tail in graded:
            continue
        base = merge_base(rpc, repo, main_sha, sha)
        if base is None:
            graded.add(tail)
            rows.append((tail, "KEEP", "no merge base with main — nothing to compare"))
            continue
        problems = content_problems(rpc, repo, main_sha, base, sha)
        if problems:
            graded.add(tail)
            shown = "; ".join(problems[:3])
            if len(problems) > 3:
                shown += " (+%d more file(s) diverging)" % (len(problems) - 3)
            rows.append((tail, "KEEP", shown))
        else:
            classify(tail, "CONTENT",
                     "%d added line(s) over its merge base, every one already in "
                     "main's copy of those files, and it removes nothing main carries"
                     % added_line_count(rpc, repo, base, sha))
    legs.append("content-landed")
    legs.append("unlanded")

    notes = []
    problems = []
    if not slot:
        notes.append("register: #+PENDING-REVIEW is empty — nothing parked, so there is "
                     "no slot to grade against the dispositions")
    elif slot_tail not in tails:
        notes.append("register: names %s, which is NOT in the turn-ref population — the "
                     "slot-live leg of review_preflight_check owns that finding and this "
                     "harness refuses to disposition a ref it cannot read" % slot_tail)
    elif slot_tail in prunable:
        # A finding, not an exception: the hazard and the disposition table are BOTH what
        # the Lead needs on one screen — a RED that hides the prune list would cost the
        # beat it saves.
        problems.append("the register parks %s (sha %s), which this harness dispositions "
                        "PRUNE-READY %s — the stale-echo class is LIVE in the control "
                        "file: the next review lane is dispatched over work main already "
                        "carries. Clear or re-point the slot, then prune the ref per the "
                        "prune law." % (slot_tail, (slot or {}).get("sha", "")[:8],
                                        prunable[slot_tail]))
    else:
        notes.append("register: %s is parked and holds unlanded content — a real lane"
                     % slot_tail)
    legs.append("slot-disposition")

    if tuple(legs) != LEG_ROSTER or len(LEG_ROSTER) != EXPECTED_LEGS:
        raise CannotRun("the run executed %d leg(s) [%s] while this harness pins %d as "
                        "[%s] — a leg skipped, reordered or retitled means the "
                        "dispositions above do not cover what the roster claims"
                        % (len(legs), ",".join(legs), EXPECTED_LEGS, ",".join(LEG_ROSTER)))
    return len(population), rows, prunable, notes, problems


def report(n, rows, prunable, notes, problems, main, out=sys.stdout):
    for tail, dispo, why in rows:
        print("  %-24s %-19s %s" % (tail, dispo, why), file=out)
    counts = {}
    for _tail, dispo, _why in rows:
        counts[dispo] = counts.get(dispo, 0) + 1
    print("", file=out)
    print("  DISPOSITIONS %s" % ", ".join("%s=%d" % (key, counts[key])
                                          for key in DISPOSITIONS if key in counts),
          file=out)
    print("  DEBT         %d of %d turn ref(s) against %s are PRUNE-READY — this harness "
          "names candidates and removes none; deletion is the Lead's prune law"
          % (len(prunable), n, main), file=out)
    for note in notes:
        print("  NOTE         %s" % note, file=out)
    if problems:
        for problem in problems:
            print("REF PRUNE RED — %s" % problem, file=out)
        return 1
    print("REF PRUNE OK — %d turn ref(s) dispositioned against %s, and the register parks "
          "no prunable ref" % (n, main), file=out)
    return 0


# ------------------------------------------------------------------------ fixture
TURN_MAIN = "main"
CHAT_REL = "agent-team/CHAT.org"
CONTROL_REL = "agent-team/CONTROL.org"
WORK_REL = "docs/fixture-work.md"

CHAT_BASE = ("* MSG software-engineer -> @lead :report:      "
             ":msg:software-engineer:lead:report:\n"
             ":PROPERTIES:\n:FROM: software-engineer\n:TO: lead\n:KIND: report\n"
             ":WHEN: [2026-01-01 Thu 09:00 UTC]\n:END:\n  base entry body\n")
ENTRY_LANDED = ("* MSG software-engineer -> @lead :report:      "
                ":msg:software-engineer:lead:report:\n"
                ":PROPERTIES:\n:FROM: software-engineer\n:TO: lead\n:KIND: report\n"
                ":WHEN: [2026-01-01 Thu 09:30 UTC]\n:END:\n  bytes main carries verbatim\n")
ENTRY_UNLANDED = ("* MSG software-engineer -> @lead :report:      "
                  ":msg:software-engineer:lead:report:\n"
                  ":PROPERTIES:\n:FROM: software-engineer\n:TO: lead\n:KIND: report\n"
                  ":WHEN: [2026-01-01 Thu 10:00 UTC]\n:END:\n  work main has never seen\n")
CONTROL_EMPTY = ("#+TITLE: fixture control (Lead-owned in the real repo)\n"
                 "#+KILL-SWITCH: OFF\n#+PENDING-REVIEW:\n")


def sh(repo, *args, **kwargs):
    env = dict(os.environ)
    # Address-less identity, pinned so a host git config can never bleed into a fixture
    # commit and so the commit choke-point guard has no address shape to match here.
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "fixture"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "fixture"
    stamp = kwargs.get("when")
    if stamp:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "%s +0000" % stamp
    proc = subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                          text=True, env=env)
    if proc.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, "w") as handle:
        handle.write(text)


def commit_all(repo, msg, when=None):
    sh(repo, "add", "-A")
    if when:
        sh(repo, "commit", "-q", "-m", msg, when=when)
    else:
        sh(repo, "commit", "-q", "-m", msg)


def branch(repo, name):
    sh(repo, "checkout", "-q", "-b", name)


def fixture():
    """One main, four turn refs — one per disposition, at fixed clocks.

    0001 MERGED   its tip is an ancestor of main.
    0002 RECORD   squash-landed: main carries the bytes AND a landing record newer than
                  the tip, while the tip itself is NOT an ancestor (the 1946 shape).
    0003 CONTENT  cut BEFORE main carried the entry, so its delta is a real addition of
                  lines main has since taken verbatim — unmerged, no record (the 1236
                  shape: a landing that moved bytes but not commits).
    0004 KEEP     unmerged and holding bytes main lacks.

    Each branch is cut from an explicit start point, not from whatever HEAD a previous
    control left, so one ref's payload can never ride into another's disposition.
    """
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ref-prune-fixture-")
    repo = os.path.join(tmp, "tree")
    os.makedirs(repo)
    sh(repo, "init", "-q", "-b", TURN_MAIN)
    write(repo, CHAT_REL, CHAT_BASE)
    write(repo, CONTROL_REL, CONTROL_EMPTY)
    commit_all(repo, "control: seed the fixture register", when="2026-01-01T09:00:00")

    sh(repo, "checkout", "-q", "-b", "ai/turn-20260101-0001")
    write(repo, WORK_REL, "merged work\n")
    commit_all(repo, "turn(fixture): a branch main already merged",
               when="2026-01-01T09:05:00")
    sh(repo, "checkout", "-q", TURN_MAIN)
    sh(repo, "merge", "-q", "--no-edit", "ai/turn-20260101-0001", when="2026-01-01T09:06:00")
    pre_landing = _tip(repo, TURN_MAIN)

    sh(repo, "checkout", "-q", "-b", "ai/turn-20260101-0002", pre_landing)
    write(repo, CHAT_REL, CHAT_BASE + ENTRY_LANDED)
    commit_all(repo, "turn(fixture): squash-landed payload", when="2026-01-01T09:10:00")
    sh(repo, "checkout", "-q", TURN_MAIN)
    write(repo, CHAT_REL, CHAT_BASE + ENTRY_LANDED + "\n")
    commit_all(repo, "union landing of ai/turn-20260101-0002 (squash)",
               when="2026-01-01T09:20:00")

    sh(repo, "checkout", "-q", "-b", "ai/turn-20260101-0003", pre_landing)
    write(repo, CHAT_REL, CHAT_BASE + ENTRY_LANDED)
    commit_all(repo, "turn(fixture): content main carries verbatim",
               when="2026-01-01T09:12:00")

    sh(repo, "checkout", "-q", "-b", "ai/turn-20260101-0004", pre_landing)
    write(repo, CHAT_REL, CHAT_BASE + ENTRY_UNLANDED)
    commit_all(repo, "turn(fixture): genuinely queued work", when="2026-01-01T09:14:00")

    sh(repo, "checkout", "-q", TURN_MAIN)
    return repo


def park_slot(repo, tail, sha, when="2026-01-01T09:40:00"):
    """The Lead writes the register; a control re-writes it to name one ref."""
    text = CONTROL_EMPTY.replace("#+PENDING-REVIEW:\n",
                                 "#+PENDING-REVIEW: branch=%s | author=software-engineer "
                                 "| sha=%s\n" % (tail, sha))
    write(repo, CONTROL_REL, text)
    commit_all(repo, "control: park %s in the register" % tail, when=when)


def _tip(repo, tail):
    return sh(repo, "rev-parse", "--verify", "%s^{commit}" % tail).strip()


def _capture(repo, main=TURN_MAIN, only=None):
    from io import StringIO
    buf = StringIO()
    try:
        n, rows, prunable, notes, problems = grade(repo=repo, main=main, only=only)
        rc = report(n, rows, prunable, notes, problems, main, out=buf)
    except CannotRun as exc:
        return 2, "CANNOT RUN — %s" % exc
    except AssertionError as exc:
        return 2, "CANNOT RUN — %s" % exc
    return rc, buf.getvalue()


def c_removal_not_prunable():
    repo = fixture()
    branch(repo, "ai/turn-20260101-0005")
    text = open(os.path.join(repo, CHAT_REL)).read().replace("  base entry body\n", "")
    write(repo, CHAT_REL, text)
    commit_all(repo, "turn(fixture): deletes a line main still carries",
               when="2026-01-01T09:16:00")
    sh(repo, "checkout", "-q", TURN_MAIN)
    return repo


def c_new_file_not_prunable():
    repo = fixture()
    branch(repo, "ai/turn-20260101-0006")
    write(repo, "docs/never-landed.md", "a file main does not carry at all\n")
    commit_all(repo, "turn(fixture): adds a file main lacks", when="2026-01-01T09:17:00")
    sh(repo, "checkout", "-q", TURN_MAIN)
    return repo


def c_rework_after_record():
    """A tip NEWER than its landing record stays queued (the shipped ordering rule)."""
    repo = fixture()
    sh(repo, "checkout", "-q", "ai/turn-20260101-0002")
    write(repo, WORK_REL, "post-landing rework main never carried\n")
    commit_all(repo, "turn(fixture): rework after the landing", when="2026-01-01T09:50:00")
    sh(repo, "checkout", "-q", TURN_MAIN)
    return repo


def c_live_head_not_prunable():
    """HEAD standing on a merged turn ref: the guard must refuse to name it deletable."""
    repo = fixture()
    sh(repo, "checkout", "-q", "ai/turn-20260101-0001")
    return repo


def c_slot_parks_prunable():
    repo = fixture()
    park_slot(repo, "ai/turn-20260101-0002", _tip(repo, "ai/turn-20260101-0002"))
    return repo


def c_slot_parks_live_work():
    repo = fixture()
    park_slot(repo, "ai/turn-20260101-0004", _tip(repo, "ai/turn-20260101-0004"))
    return repo


def c_slot_not_in_population():
    repo = fixture()
    park_slot(repo, "ai/turn-20260101-9999", "0" * 40)
    return repo


def c_no_refs():
    repo = fixture()
    for seq in ("0001", "0002", "0003", "0004"):
        sh(repo, "branch", "-q", "-D", "ai/turn-20260101-%s" % seq)
    return repo


def c_roster_drift():
    global LEG_ROSTER
    repo = fixture()
    old = LEG_ROSTER
    LEG_ROSTER = old[:-1]
    try:
        grade(repo=repo, main=TURN_MAIN)
    finally:
        LEG_ROSTER = old
    raise AssertionError("roster drift was not refused")


def c_readers_disagree():
    """Blind the shipped queue reader: the coverage door must refuse, not shrink.

    A queue read that returns nothing would leave this harness grading only the merged
    half of the population and reporting the queued half as absent — the silently-lower-
    count class the whole family exists to refuse, so the run must CANNOT RUN.
    """
    repo = fixture()
    rpc = _rpc()
    original = rpc.queue_branches
    rpc.queue_branches = lambda *args, **kwargs: (args[1] if len(args) > 1 else "", [])
    real_loader = _rpc

    def patched():
        return rpc

    globals()["_rpc"] = patched
    try:
        grade(repo=repo, main=TURN_MAIN)
    finally:
        globals()["_rpc"] = real_loader
        rpc.queue_branches = original
    raise AssertionError("a queue reader returning nothing was not refused")


CONTROLS = [
    ("honest run is green", fixture, 0, "REF PRUNE OK", ()),
    ("merged ref is prunable", fixture, 0, "PRUNE-READY MERGED", ("ai/turn-20260101-0001",)),
    ("squash-landed ref is prunable", fixture, 0, "PRUNE-READY RECORD",
     ("ai/turn-20260101-0002",)),
    ("content landed by hand is prunable", fixture, 0, "PRUNE-READY CONTENT",
     ("ai/turn-20260101-0003",)),
    ("queued work is KEEP", fixture, 0, "KEEP", ("ai/turn-20260101-0004",)),
    ("a removal is not prunable content", c_removal_not_prunable, 0, "removes",
     ("ai/turn-20260101-0005",)),
    ("a file main lacks is not prunable", c_new_file_not_prunable, 0,
     "main carries no such file", ("ai/turn-20260101-0006",)),
    ("post-landing rework stays queued", c_rework_after_record, 0, "post-landing rework",
     ("ai/turn-20260101-0002",)),
    ("the ref HEAD stands on is never prunable", c_live_head_not_prunable, 0, "LIVE —",
     ("ai/turn-20260101-0001",)),
    ("the register parks a prunable ref", c_slot_parks_prunable, 1, "REF PRUNE RED",
     ("ai/turn-20260101-0002",)),
    ("the register parks live work", c_slot_parks_live_work, 0, "a real lane", ()),
    ("the register names a ref outside the population", c_slot_not_in_population, 0,
     "NOT in the turn-ref population", ()),
    ("no turn refs at all", c_no_refs, 2, "CANNOT RUN", ()),
    ("main ref unresolvable", fixture, 2, "CANNOT RUN", ()),
    ("leg roster drift", c_roster_drift, 2, "CANNOT RUN", ()),
    ("the two ref readers disagree", c_readers_disagree, 2, "CANNOT RUN", ()),
]
EXPECTED_CONTROLS = 16


def selftest():
    if len(CONTROLS) != EXPECTED_CONTROLS:
        print("CANNOT RUN — CONTROLS lists %d, EXPECTED_CONTROLS pins %d — this harness's "
              "own population is no longer its expectation"
              % (len(CONTROLS), EXPECTED_CONTROLS))
        return 2
    failures = 0
    for name, build, want_rc, needle, extras in CONTROLS:
        try:
            repo = build()
            if name == "main ref unresolvable":
                rc, text = _capture(repo, main="origin/ai/nope")
            else:
                rc, text = _capture(repo)
        except CannotRun as exc:
            rc, text = 2, "CANNOT RUN — %s" % exc
        ok = rc == want_rc and needle in text
        for extra in extras:
            ok = ok and extra in text
        if ok:
            print("  %-52s ok (rc %d, %s)" % (name, rc, needle))
        else:
            failures += 1
            print("  %-52s FAIL rc=%d want=%d text=%s"
                  % (name, rc, want_rc, text.replace("\n", " | ")[:240]))
    if failures:
        print("SELFTEST RED — %d control(s) did not land their rc" % failures)
        return 1
    print("SELFTEST OK — %d controls, every leg proved able to fail" % len(CONTROLS))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--main", default=MAIN_REF)
    parser.add_argument("--repo", default=ROOT)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--since", default=None)
    parser.add_argument("--help", action="store_true")
    args = parser.parse_args(argv)
    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        return selftest()
    try:
        n, rows, prunable, notes, problems = grade(repo=args.repo, main=args.main,
                                                   only=args.branch, since=args.since)
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        return 2
    return report(n, rows, prunable, notes, problems, args.main)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
