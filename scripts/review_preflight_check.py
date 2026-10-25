#!/usr/bin/env python3
"""Is a queued branch actually REVIEWABLE, or is the lane about to grade state
it never authored? Re-runnable, read-only, git-only.

WHY this exists (measured, not assumed). On 2026-10-24 the chain spent NINE
review lanes on one branch, ai/turn-20261024-1632. The Lead's own triage
(LEAD 10-bb / 10-bc / 10-bf / 10-bh) sorted those nine: #1 and #2 were a
checker false-red main has since fixed, #3 and #4 were INHERITED — the branch's
base predated the chat fold repair 5147249, so the branch TREE carried the six
orphan drawer lines main had already fixed — #5 lost its transcript, and #6
through #8 graded real authored defects. The class this harness can see at zero
lane cost is #3/#4: the review brief's step 4 grades "TEAM-CHAT entries legal
format" against the branch tree, so a reviewer reads main's stale state as the
author's defect and rejects, and it did so before anyone knew the cause (the
Lead diagnosed it by hand and repaired the branch mechanically, rebase
2842a7c -> 950f71e).

Nothing in the repo re-asks that question for the REST of the queue, so the
same waste is scheduled to repeat. Measured by this harness on 2026-10-24
21:1xZ, over the 11 queued branches the OBJECTIVE lists:

    0633 inherited-orphans 2  MERGE-CONFLICT  <- the REGISTERED pending review
    0731 inherited-orphans 2  MERGE-CONFLICT
    1037 inherited-orphans 4
    1403 inherited-orphans 4
    1511 inherited-orphans 4
    1552 inherited-orphans 4
    1736 inherited-orphans 6
    1804 / 1828 / 1956 / 2033 clean (based after the repair)

Seven doomed-or-awkward reviews are already in the queue, and the one pinned in
#+PENDING-REVIEW is mine and is the worst of them: inherited reds AND a
conflict against main, i.e. the two dispositions the merger turns into
"rejected" and "approved+gate-conflict-branch-kept" (a manual Lead union-merge,
the 0607 class).

Two other standing rejection classes are graded here because they are cheap to
see before a lane is spent, not after: a harness-leak file committed into the
tree (0339 / 0454 / 0527 / 20261022-2340 — reviewers rejected for
`.turn-review.txt` in the tree), and a branch that edits a Lead-owned file
(auto-REJECT by the brief).

LEGS (pinned roster, one per claim a queued branch must satisfy):

  slot-live        the #+PENDING-REVIEW branch exists on the remote, carries
                   commits main does not (an already-merged branch means the
                   duty is SKIPPED and the lane spent on nothing), and its
                   head sha still matches the sha the register parked.
  stale-base       main has moved since the branch's merge base AND the branch
                   touched a file main also changed since then — the region
                   where an inherited repair reads as an author defect, and
                   where a merge conflict is expected.
  chat-structure   orphan drawer lines, ATTRIBUTED: (branch > base) is the
                   author's own fold, (branch == base > 0) is main's stale
                   state that the reviewer will see but the author never
                   wrote. The repair for the second is a rebase, not a rework.
  tree-hygiene     no harness-leak file in the tree, no Lead-owned file in the
                   branch's own delta.
  merge-preview    `git merge-tree` main+branch is conflict-free; a conflict
                   means an APPROVED verdict still will not land without a
                   manual union-merge.

Verdicts follow the house convention (docs/DEVGUIDE.md *EIGHTH* + *ELEVENTH*
harness laws): 0 = every queued branch is review-ready, 1 = a branch is not
(each line names the class, and says INHERITED or AUTHORED so the disposition
is obvious: rebase versus rework), 2 = CANNOT RUN (the harness no longer
understands its input — never a false red for a tree it has not measured).

This grades BRANCH STATE only. It never issues a verdict: author, reviewer and
merger stay separate roles (Owner 2026-10-22 18:14Z), so the output is evidence
for the Lead's register/disposition and for each author's rebase decision — it
writes nothing, touches nothing, and reads Lead-owned files the way seats are
allowed to: as data.

  python3 scripts/review_preflight_check.py              # grade this repo's queue
  python3 scripts/review_preflight_check.py --main <ref> # grade against another ref
  python3 scripts/review_preflight_check.py --branch ai/turn-20261024-0633   # one branch
  python3 scripts/review_preflight_check.py --since 20261024   # that day's queue only
  python3 scripts/review_preflight_check.py --selftest   # controls: every leg able to fail

Deliberately NOT named `*_diff.py`: that glob IS the landing gate's twin roster
(scripts/landing_gate.py EXPECTED_TWINS), and this compares a branch against
main, not one artifact against its twin.
"""

import importlib.util
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAIN_REF = "origin/ai/main"
BRANCH_PREFIX = "ai/turn-"
CHAT_REL = "agent-team/TEAM-CHAT.org"
CONTROL_REL = "agent-team/TEAM-CONTROL.org"

# The reviewer's own reject classes, spelled out because the brief does not
# enumerate them — it only refuses Lead-owned edits and un-legal chat entries.
LEAK_FILES = (".turn-review.txt", ".turn-inside.sh", ".turn-result.txt")
LEAD_OWNED_PREFIXES = (".github/workflows/", ".github/scripts/")
LEAD_OWNED_FILES = ("agent-team/TEAM-CONTROL.org", ".gitattributes")

LEG_ROSTER = ("slot-live", "stale-base", "chat-structure", "tree-hygiene",
              "merge-preview")
EXPECTED_LEGS = 5

PENDING_RE = re.compile(r"^\#\+PENDING-REVIEW:\s*(.*)$", re.M)
FIELD_RE = re.compile(r"\b(branch|author|sha)=([^ |\s]+)")


class CannotRun(Exception):
    pass


class LegRed(Exception):
    pass


def _ctc():
    """chain_test_check's own drawer scan, imported — never re-implemented.

    Re-spelling the orphan grammar here would fork the FORMAT LAW into two
    readers that can drift (the EIGHTH law's whole point), so the attribution
    leg reads the SAME lines the shipped CHAT-STRUCTURE leg reads.
    """
    path = os.path.join(ROOT, "scripts", "chain_test_check.py")
    if not os.path.exists(path):
        raise CannotRun("scripts/chain_test_check.py is missing — the drawer "
                        "grammar this harness attributes orphans with lives there")
    spec = importlib.util.spec_from_file_location("chain_test_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        mod.scan_orphan_drawers
    except Exception as exc:
        raise CannotRun("scripts/chain_test_check.py cannot be imported: %s" % exc)
    return mod


# ------------------------------------------------------------------ git plumbing
def git(repo, *args):
    proc = subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout


def resolve(repo, ref):
    rc, out = git(repo, "rev-parse", "--verify", "%s^{commit}" % ref)
    if rc != 0:
        return None
    return out.strip()


def show(repo, ref, rel):
    """A file's text at a rev, or None when the rev does not carry it."""
    rc, out = git(repo, "show", "%s:%s" % (ref, rel))
    if rc != 0:
        return None
    return out


def changed_files(repo, left, right):
    rc, out = git(repo, "diff", "--name-only", "%s..%s" % (left, right))
    if rc != 0:
        raise CannotRun("git diff %s..%s failed" % (left, right))
    return set(out.split())


def count(repo, rev):
    rc, out = git(repo, "rev-list", "--count", rev)
    return out.strip() if rc == 0 else "?"


def queue_branches(repo, main, prefix, since=None):
    """Every live branch of this chain: a ref with the turn prefix that still
    carries commits main does not. An already-merged branch is not queued — the
    review arm skips it too (turn_segment.sh 'REVIEW DUTY SKIPPED'), so grading
    it would report work the queue no longer holds."""
    main_sha = resolve(repo, main)
    if main_sha is None:
        raise CannotRun("main ref %s does not resolve in %s" % (main, repo))
    rc, out = git(repo, "for-each-ref", "--format=%(refname:short)")
    main_tail = main.split("/")[-1]
    # A seat's workspace carries the same branch twice — once as a local head, once
    # as its remote ref — so rows are keyed by branch name and the remote wins: the
    # chain reviews and merges what was PUSHED, never what a laptop still holds.
    by_tail = {}
    for short in sorted(out.split()):
        remote = short.startswith("origin/")
        tail = short.split("/", 1)[-1] if remote else short
        if tail == main or tail == main_tail or not tail.startswith(prefix):
            continue
        if since and tail[len(prefix):][:8] < since:
            continue
        sha = resolve(repo, short)
        if sha is None:
            continue
        rc, ahead = git(repo, "rev-list", "--count", "%s..%s" % (main_sha, sha))
        if rc != 0 or int(ahead.strip()) == 0:
            continue
        if not remote and tail in by_tail:
            continue
        by_tail[tail] = (short, sha)
    return main_sha, [by_tail[k] for k in sorted(by_tail)]


def pending_slot(repo, main):
    """The register line, read from main's tree (Lead-owned: read, never written)."""
    text = show(repo, main, CONTROL_REL)
    if text is None:
        return None
    match = PENDING_RE.search(text)
    if not match or not match.group(1).strip():
        return None
    fields = dict(FIELD_RE.findall(match.group(1)))
    return {"raw": match.group(1).strip(),
            "branch": fields.get("branch", ""),
            "author": fields.get("author", ""),
            "sha": fields.get("sha", "")}


def orphan_row(ctc, repo, ref):
    """(orphans, headlines) for the chat as that rev carries it."""
    text = show(repo, ref, CHAT_REL)
    if text is None:
        raise CannotRun("%s does not carry %s" % (ref, CHAT_REL))
    orphans, _owned = ctc.scan_orphan_drawers(text)
    headlines = len(re.findall(r"^\* MSG ", text, re.M))
    return len(orphans), headlines


# ---------------------------------------------------------------------- legs
def is_lead_owned(path):
    return (path.startswith(LEAD_OWNED_PREFIXES) or path in LEAD_OWNED_FILES)


def grade_branch(ctc, repo, main, main_sha, short, sha):
    """Every branch-level claim, as a list of tagged findings for one branch."""
    findings = []
    notes = []
    rc, mb_out = git(repo, "merge-base", main_sha, sha)
    if rc != 0:
        raise CannotRun("no merge base between %s and %s" % (main, short))
    mb = mb_out.strip()
    stale = mb != main_sha

    # stale-base — staleness alone is harmless; what dooms a review is main
    # having moved INSIDE a region the branch also edited.
    overlap = set()
    if stale:
        own = changed_files(repo, mb, sha)
        theirs = changed_files(repo, mb, main_sha)
        overlap = own & theirs
        if overlap:
            findings.append(("STALE", "main moved %d commit(s) since this base and %d "
                             "of them land in file(s) this branch also edited: %s"
                             % (int(count(repo, "%s..%s" % (mb, main_sha))),
                                len(overlap), ", ".join(sorted(overlap)))))
        notes.append("base %s / main +%s / branch +%s"
                     % (mb[:7], count(repo, "%s..%s" % (mb, main_sha)),
                        count(repo, "%s..%s" % (mb, sha))))

    # chat-structure — attributed, because the reviewer cannot tell the two apart
    br_orphans, br_heads = orphan_row(ctc, repo, sha)
    if br_heads == 0:
        raise CannotRun("%s: %s holds 0 `* MSG` headlines — the orphan scan is "
                        "grading nothing and its verdict would be fiction"
                        % (short, CHAT_REL))
    if stale:
        base_orphans, _ = orphan_row(ctc, repo, mb)
    else:
        base_orphans = 0
    authored = br_orphans - base_orphans
    if authored > 0:
        findings.append(("AUTHORED", "chat-structure: this branch put %d orphan "
                         "drawer line(s) in %s (branch %d vs its merge base %d) — a "
                         "message lost its `* MSG` headline in the branch's own edit, "
                         "so the FORMAT LAW's FROM no longer travels with it"
                         % (authored, CHAT_REL, br_orphans, base_orphans)))
    elif br_orphans > 0:
        findings.append(("INHERITED", "chat-structure: %s carries %d orphan drawer "
                         "line(s) that its OWN merge base already carried — the "
                         "reviewer grades this tree and will read main's stale state "
                         "as the author's defect. Repair = rebase onto %s (precedent "
                         "950f71e), NOT a content rework"
                         % (short, br_orphans, main)))

    # tree-hygiene
    rc, out = git(repo, "ls-tree", "-r", "--name-only", sha)
    tree = set(out.split())
    leaks = sorted(f for f in tree if f in LEAK_FILES)
    if leaks:
        findings.append(("AUTHORED", "tree carries harness-leak file(s) %s — the "
                         "standing reject class (0339 / 0454 / 0527 / 20261022-2340)"
                         % ", ".join(leaks)))
    if stale:
        lead = sorted(p for p in changed_files(repo, mb, sha) if is_lead_owned(p))
        if lead:
            findings.append(("AUTHORED", "the branch edits Lead-owned file(s) %s — "
                             "the review brief refuses this on sight (seats may only "
                             "read and cite them)" % ", ".join(lead)))

    # merge-preview
    rc, _out = git(repo, "merge-tree", "--write-tree", main_sha, sha)
    if rc != 0:
        findings.append(("INHERITED", "merge-preview: `git merge-tree %s %s` "
                         "conflicts — an APPROVED verdict here lands as "
                         "'approved+gate-conflict-branch-kept' and waits for a "
                         "manual Lead union-merge (the 0607 class); a rebase "
                         "resolves it before the lane is spent"
                         % (main, short)))
    return findings, notes, stale, br_orphans


def grade(repo, main=MAIN_REF, only=None, since=None):
    if len(LEG_ROSTER) != EXPECTED_LEGS:
        raise CannotRun("LEG_ROSTER lists %d leg(s), EXPECTED_LEGS pins %d — the "
                        "roster of this harness changed without its pin"
                        % (len(LEG_ROSTER), EXPECTED_LEGS))
    ctc = _ctc()
    main_sha, rows = queue_branches(repo, main, BRANCH_PREFIX, since)
    if only:
        rows = [r for r in rows if r[0] == only or r[0] == "origin/" + only
                or r[0].endswith("/" + only)]
        if not rows:
            raise CannotRun("--branch %s is not a queued branch (already merged, "
                            "or not present in this repo)" % only)

    slot = pending_slot(repo, main_sha)
    problems = []
    notes = []
    ran = set()

    # slot-live — the register is the single slot the chain spends a lane on
    if slot is None:
        ran.add("slot-live")
        notes.append("slot-live: register empty — no branch is queued for review")
    else:
        ran.add("slot-live")
        sha_map = dict((s, h) for s, h in rows)
        by_short = slot["branch"].replace("refs/heads/", "")
        full = by_short if by_short.startswith("origin/") else "origin/" + by_short
        live = resolve(repo, full) or resolve(repo, by_short)
        if live is None:
            problems.append("slot-live: %s names %s, which this repo does not have "
                            "— the review arm skips the duty and the run reports "
                            "review-missing, the 0659 / 21:00Z class"
                            % (CONTROL_REL, slot["branch"]))
        elif int(count(repo, "%s..%s" % (main_sha, live)) or 0) == 0:
            problems.append("slot-live: %s is registered for review but is already "
                            "fully merged into %s — the duty would be skipped, so "
                            "the register needs advancing" % (slot["branch"], main))
        elif slot["sha"] and not _same_head(slot["sha"], live):
            problems.append("slot-live: register parks head %s but the branch head is "
                            "%s — the reviewer grades the live tip; a rebase moves it "
                            "(a stale sha is informational until the next writeback)"
                            % (slot["sha"][:7], live[:7]))
        else:
            notes.append("slot-live: %s queued, head %s, author %s"
                         % (slot["branch"], (live or "?")[:7], slot["author"] or "?"))

    for short, sha in rows:
        findings, bnotes, stale, orphans = grade_branch(
            ctc, repo, main, main_sha, short, sha)
        for leg in ("stale-base", "chat-structure", "tree-hygiene", "merge-preview"):
            ran.add(leg)
        for tag, text in findings:
            problems.append("%s [%s] %s" % (short.split("/")[-1], tag, text))
        notes.append("%-22s %s%s" % (short.split("/")[-1],
                                     " ".join(bnotes) if bnotes else "up to date",
                                     "" if findings else "  REVIEW-READY"))

    missing = [leg for leg in LEG_ROSTER if leg not in ran]
    if missing and rows:
        raise CannotRun("leg(s) %s never ran over %d queued branch(es) — the "
                        "harness is not grading what its roster claims"
                        % (", ".join(missing), len(rows)))
    return len(rows), problems, notes


# ------------------------------------------------------------------- reporting
def _same_head(parked, live):
    """Register sha vs live tip, tolerating an abbreviated park (the writeback
    stores 40 hex, Lead notes quote 7)."""
    if not parked or not live:
        return True
    return parked.startswith(live) or live.startswith(parked)


def report(n, problems, notes, main, out=sys.stdout):
    for line in notes:
        print(line, file=out)
    print("", file=out)
    if problems:
        print("REVIEW PREFLIGHT RED — %d queued branch(es) graded, "
              "%d finding(s):" % (n, len(problems)), file=out)
        for p in problems:
            print("  " + p, file=out)
        print("  INHERITED = rebase the branch (author's own content is not in "
              "question); AUTHORED = the branch must rework. Register "
              "dispositions stay the Lead's.", file=out)
        return 1
    print("REVIEW PREFLIGHT OK — %d queued branch(es) graded against %s, every "
          "one review-ready (no inherited reds, no leak file, no Lead-owned "
          "edit, clean merge-preview)" % (n, main), file=out)
    return 0


# ------------------------------------------------------------------- fixtures
ENTRY = ("* MSG software-engineer -> @lead :report:      "
         ":msg:software-engineer:lead:report:\n"
         ":PROPERTIES:\n"
         ":FROM: software-engineer\n"
         ":TO: lead\n"
         ":KIND: report\n"
         ":WHEN: [2026-10-24 Sat 21:00 UTC]\n"
         ":END:\n"
         "  body of a legal entry\n")

# The fold shape: the five header lines eaten, the tail survived.
ORPHAN = (":WHEN: [2026-10-24 Sat 21:00 UTC]\n"
          ":END:\n"
          "  body whose headline was folded away\n")

CONTROL = ("#+TITLE: fixture control (Lead-owned in the real repo)\n"
           "#+PENDING-REVIEW: branch=%s | author=software-engineer | sha=%s\n")

TURN_BRANCH = "ai/turn-20260101-0000"


def sh(repo, *args):
    rc, out = git(repo, *args)
    if rc != 0:
        raise CannotRun("fixture git %s failed: %s" % (" ".join(args), out))
    return out


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, "w") as fh:
        fh.write(text)


def commit(repo, msg, force=False):
    sh(repo, "add", "-A", *(["-f"] if force else []))
    sh(repo, "-c", "user.name=f", "-c", "user.email=f@e", "commit", "-qm", msg)


def bump(repo, rel, text):
    with open(os.path.join(repo, rel)) as fh:
        old = fh.read()
    write(repo, rel, old + text)


def fixture(orphan_in_base=False, no_headlines=False):
    """A two-branch repo shaped like the chain: a main ref, one queued turn
    branch, a register line parking it. Every control mutates a fresh fixture,
    so each leg is proven able to fail on real git state rather than on a
    hand-written string."""
    repo = tempfile.mkdtemp(prefix="preflight-")
    sh(repo, "init", "-q", "-b", "main", ".")
    sh(repo, "config", "user.name", "f")
    sh(repo, "config", "user.email", "f@e")
    chat = "#+TITLE: chat\n" + ENTRY + ENTRY
    if orphan_in_base:
        chat += ORPHAN
    if no_headlines:
        chat = "#+TITLE: chat\n" + ORPHAN
    write(repo, CHAT_REL, chat)
    write(repo, "agent-team/TODOS.org", "* TODO an item\n")
    write(repo, ".gitignore", "/.turn-*.txt\n")
    write(repo, CONTROL_REL, CONTROL % (TURN_BRANCH, "0" * 40))
    commit(repo, "base")
    sh(repo, "checkout", "-q", "-b", TURN_BRANCH)
    bump(repo, CHAT_REL, ORPHAN if no_headlines else ENTRY)
    commit(repo, "turn: queued work")
    head = sh(repo, "rev-parse", "HEAD").strip()
    sh(repo, "checkout", "-q", "main")
    write(repo, CONTROL_REL, CONTROL % (TURN_BRANCH, head))
    commit(repo, "control: park the branch")
    return repo


# ------------------------------------------------------------------ controls
def _head(repo, ref=TURN_BRANCH):
    return sh(repo, "rev-parse", ref).strip()


def _on(repo, ref, fn):
    """Run fn() with the repo checked out to ref, then return to ref's parent."""
    sh(repo, "checkout", "-q", ref)
    fn()
    sh(repo, "checkout", "-q", "main")


def c_no_change():
    return fixture()


def c_authored_orphan():
    def work():
        bump(base, CHAT_REL, ORPHAN)
        commit(base, "turn: folded a headline away")
    base = fixture()
    _on(base, TURN_BRANCH, work)
    return base


def c_inherited_orphan():
    return fixture(orphan_in_base=True)


def c_leak_file():
    def work():
        write(base, ".turn-review.txt", "VERDICT: APPROVED\n")
        commit(base, "turn: harness scratch leaked", force=True)
    base = fixture()
    _on(base, TURN_BRANCH, work)
    return base


def c_lead_owned_edit():
    def work():
        bump(base, CONTROL_REL, "#+STALL-COUNT: 7\n")
        commit(base, "turn: edited a Lead-owned file")
    base = fixture()
    _on(base, TURN_BRANCH, work)
    return base


def c_merge_conflict():
    def work():
        bump(base, CHAT_REL, ENTRY)
        commit(base, "turn: both sides appended at EOF")
    base = fixture()
    _on(base, TURN_BRANCH, work)
    bump(base, CHAT_REL, ENTRY)
    commit(base, "main: also appended at EOF")
    return base


def c_slot_branch_gone():
    base = fixture()
    write(base, CONTROL_REL, CONTROL % ("ai/turn-20991231-2359", "1" * 40))
    commit(base, "control: park a branch that does not exist")
    return base


def c_slot_already_merged():
    base = fixture()
    sh(base, "checkout", "-q", "main")
    sh(base, "merge", "-q", "--no-ff", "-m", "main: merged the queued branch",
       TURN_BRANCH)
    return base


def c_slot_sha_stale():
    base = fixture()
    write(base, CONTROL_REL, CONTROL % (TURN_BRANCH, "deadbeef" * 5))
    commit(base, "control: park the wrong head")
    return base


def c_slot_empty():
    base = fixture()
    write(base, CONTROL_REL, "#+TITLE: fixture control\n#+PENDING-REVIEW: \n")
    commit(base, "control: clear the slot")
    return base


def c_blind_chat():
    return fixture(no_headlines=True)


def c_missing_main_ref():
    base = fixture()
    sh(base, "checkout", "-q", TURN_BRANCH)
    sh(base, "branch", "-D", "main")
    return base


def c_roster_drift():
    global LEG_ROSTER
    base = fixture()
    old = LEG_ROSTER
    LEG_ROSTER = old[:-1]
    try:
        grade(base, main="main")
    finally:
        LEG_ROSTER = old
    raise AssertionError("roster drift was not refused")


CONTROLS = [
    ("green queue", c_no_change, 0, "REVIEW PREFLIGHT OK", ()),
    ("branch authored an orphan drawer", c_authored_orphan, 1, "AUTHORED", ("chat-structure",)),
    ("inherited orphan from a stale base", c_inherited_orphan, 1, "INHERITED", ("chat-structure",)),
    ("harness leak file in the tree", c_leak_file, 1, "harness-leak", ()),
    ("Lead-owned file edited by the branch", c_lead_owned_edit, 1, "Lead-owned", ()),
    ("merge-preview conflicts", c_merge_conflict, 1, "merge-preview", ()),
    ("register names a dead branch", c_slot_branch_gone, 1, "slot-live", ()),
    ("register names an already-merged branch", c_slot_already_merged, 1, "slot-live", ()),
    ("register head sha is stale", c_slot_sha_stale, 1, "slot-live", ()),
    ("register empty", c_slot_empty, 0, "register empty", ()),
    ("chat holds no headlines (blind scan)", c_blind_chat, 2, "CANNOT RUN", ()),
    ("main ref unresolvable", c_missing_main_ref, 2, "CANNOT RUN", ()),
    ("leg roster drift", c_roster_drift, 2, "CANNOT RUN", ()),
]
EXPECTED_CONTROLS = 13


def selftest():
    if len(CONTROLS) != EXPECTED_CONTROLS:
        print("CANNOT RUN — CONTROLS lists %d, EXPECTED_CONTROLS pins %d"
              % (len(CONTROLS), EXPECTED_CONTROLS))
        return 2
    failures = 0
    for name, build, want_rc, needle, extras in CONTROLS:
        try:
            repo = build()
            rc, text = _capture(repo)
        except CannotRun as exc:
            rc, text = 2, "CANNOT RUN — %s" % exc
        ok = rc == want_rc and needle in text
        for extra in extras:
            ok = ok and extra in text
        status = "ok" if ok else "FAIL"
        if not ok:
            failures += 1
            print("  %-38s %s rc=%d want=%d text=%s"
                  % (name, status, rc, want_rc, text.replace("\n", " | ")[:260]))
        else:
            print("  %-38s %s (rc %d, %s)" % (name, status, rc, needle))
    if failures:
        print("SELFTEST RED — %d control(s) did not land their rc" % failures)
        return 1
    print("SELFTEST OK — %d controls, every leg proved able to fail"
          % len(CONTROLS))
    return 0


def _capture(repo):
    from io import StringIO
    buf = StringIO()
    try:
        n, problems, notes = grade(repo, main="main")
        rc = report(n, problems, notes, "main", out=buf)
    except CannotRun as exc:
        return 2, "CANNOT RUN — %s" % exc
    except AssertionError as exc:
        return 2, "CANNOT RUN — %s" % exc
    return rc, buf.getvalue()


def main(argv):
    repo, main, only, since = ROOT, MAIN_REF, None, None
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--selftest":
            return selftest()
        elif a == "--main":
            i += 1
            main = args[i]
        elif a == "--repo":
            i += 1
            repo = args[i]
        elif a == "--branch":
            i += 1
            only = args[i]
        elif a == "--since":
            i += 1
            since = args[i]
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print("unknown argument %r" % a)
            return 2
        i += 1
    try:
        n, problems, notes = grade(repo, main=main, only=only, since=since)
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        return 2
    return report(n, problems, notes, main)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


