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

A THIRD state had no reader at all until the platform seat measured it
(ai/turn-20261025-0830, 2026-10-25 08:47Z): the chat MERGE FOLD. `.gitattributes`
gives agent-team/TEAM-CHAT.org the `merge=union` driver, so two appends whose
leading lines are identical — every entry of one seat to one addressee with one
kind opens with the SAME five lines — are read as common context and folded into
one header. Measured on ai/turn-20261024-1956: merge base 0 orphan drawer lines,
branch tip 0, main 0, `git merge-tree --write-tree` 2 (the software entry's
`:WHEN:`/`:END:` welded onto the platform entry, its headline eaten) — and that
command answered rc 0, CONFLICT-FREE, which is why the merge-preview leg below
passed it and the lane was spent anyway. The defect lives in NO tree either side
carries, so the only read that can see it is the merged blob itself, taken from
the merge-tree output and scanned with chain_test_check's OWN
`scan_orphan_drawers` — the same reader the shipped CHAT-STRUCTURE leg uses, not
a re-spelled grammar (DEVGUIDE *EIGHTH law*).

That read is now made TWICE, on opposite sides of the lane. The Lead landed a
finalize-side guard (f3e0f63, LEAD 10-ci): after the auto-merge it runs
chain_test_check on the merged tree and undoes the merge on any CHAT-STRUCTURE
ground. Correct, and it is why a fold can no longer LAND silently — but it fires
AFTER a ~30-minute review lane has been paid for a branch that was never going
to merge. This leg is the pre-lane half of the same claim: it predicts the fold
before the register is flipped, names it INHERITED (the author's content is
legal; the repair is a fresh base, not a rework), and the two readers stay
independent because they use different mechanisms (a workflow grep of the
shipped harness's output vs this harness's direct read of the merge-tree blob).

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
  landed-echo      the branch the register parks is not already LANDED. A
                   squash landing keeps the branch's commits out of main's
                   ancestry ON PURPOSE (Lead 10-do: defective ancestry stays
                   on the branch ref as evidence), so slot-live's main..branch
                   count cannot see it and the slot can be written back to a
                   CLOSED branch — the 10-dp write-cross, where the machinery
                   re-registered 1946@93e0f45 seconds after the Lead landed the
                   same sha and a parallel review lane was dispatched over it.
                   The record this leg reads is the repo's own landing
                   convention: a commit whose SUBJECT opens with the landing
                   verb and names the branch as its object.
  merged-fold      when that merge IS conflict-free, its chat blob is scanned:
                   orphan drawer lines or a missing `* MSG` headline that NEITHER
                   side authored are the union driver folding two appends onto one
                   header — `MERGE-ONLY FOLD`, INHERITED, repair = rebase.

Verdicts follow the house convention (docs/DEVGUIDE.md *EIGHTH* + *ELEVENTH*
harness laws): 0 = every queued branch is review-ready, 1 = a branch is not
(each line names the class, and says INHERITED or AUTHORED so the disposition
is obvious: rebase versus rework), 2 = CANNOT RUN (the harness no longer
understands its input — never a false red for a tree it has not measured).
TWO coverage doors refuse before any verdict is printed, because a harness that
quietly grades less is the one class of red a green cannot show: a roster leg
that NEVER ran, and a leg marked PAST its code paths — the second is the
union-fold class this file itself carried (slot-live written twice by 49f63f3,
the duplicate re-initialising the accumulators so the first copy's findings were
eaten), and a set cannot see a repeat, so the marks are counted.

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

LEG_ROSTER = ("slot-live", "landed-echo", "stale-base", "chat-structure",
              "tree-hygiene", "merge-preview", "merged-fold")
EXPECTED_LEGS = 7

# The legs the per-branch loop runs ONCE PER queued branch, hoisted out of that
# loop so the loop and the double-mark door below read ONE roster — otherwise the
# door would invent its own list of who is allowed to repeat.
PER_BRANCH_LEGS = ("stale-base", "chat-structure", "tree-hygiene",
                   "merge-preview", "merged-fold")

PENDING_RE = re.compile(r"^\#\+PENDING-REVIEW:[ \t]*(.*)$", re.M)
# [ \t]* not \s*: \s eats the newline under re.M, so a BARE register line made
# group(1) swallow the next control line (measured: group(1) == the #+TURN:
# line -> truthy -> the return-None guard never fired -> a phantom pending slot
# with no branch/author/sha -> false RED naming nothing). Found by the
# software-engineer TEST-T2 turn 0544@0de7f0f; Lead-measured reproduction and
# fix (populated lines parse identically under both patterns).
FIELD_RE = re.compile(r"\b(branch|author|sha)=([^ |\s]+)")


# A landing record, as this repo actually writes one: the verb OPENS the
# subject and the branch ref is its object — "union landing of ai/turn-...
# (squash)", "Merge branch 'ai/turn-...' into ai/main", "merge ai/turn-...
# (Lead union-merge)". Co-occurrence anywhere in the subject is NOT enough:
# main's own history carries prose like "control: re-queue ai/turn-20261022-1904
# (...) Lead audit-merge owed", which names a live branch next to a merge word —
# firing on that would red a genuinely queued slot, and a leg that fires on a
# correct state is worse than no leg (DEVGUIDE *ELEVENTH law*).
LANDING_RECORD_RE = re.compile(
    r"^(?:[A-Za-z]+ )?(?:landing|merge)\b(?:\s+of)?(?:\s+remote-tracking)?"
    r"(?:\s+branch)?\s+'?(?:origin/)?(?:refs/heads/)?(ai/turn-\d{8}-\d{4})'?\b",
    re.I)


class CannotRun(Exception):
    pass


class LegRed(Exception):
    pass


class _LegMarks:
    """Which legs ran, counted — not just which ran.

    The coverage door below reads a set, and a set cannot see a repeat. That is
    how this harness carried the union-fold class in its own source: 49f63f3 left
    the whole slot-live block written TWICE, and the second copy re-initialised
    the three accumulators before running it, so the first copy's findings were
    eaten before the door ever saw them. Both copies add the SAME member, so the
    set read identically either way — the fold was invisible to every leg of the
    harness whose job is to grade leg coverage.
    """

    def __init__(self):
        self.counts = {}

    def add(self, leg):
        self.counts[leg] = self.counts.get(leg, 0) + 1

    def __contains__(self, leg):
        return leg in self.counts


def doubled_legs(counts, branch_runs):
    """Legs marked past their code paths. `branch_runs` is the queue size, not a
    pin: the per-branch roster legitimately marks once per queued branch, so a
    second branch is never mistaken for a second copy of a block."""
    out = []
    for leg, n in sorted(counts.items()):
        owed = branch_runs if leg in PER_BRANCH_LEGS else 1
        if n > owed:
            out.append("%s (%d mark(s), %d code path(s) owed)" % (leg, n, owed))
    return out


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


def merged_chat(ctc, repo, tree):
    """The same scan over the MERGE RESULT — the one state a fold can live in.

    Neither parent carries it (measured on ai/turn-20261024-1956: base 0,
    branch 0, main 0 orphans, merged 2), so this read is not a repeat of
    `orphan_row`: it is the only read of a state the chain merges into. The
    population rule is the shipped one — a scan that finds no headline is
    grading nothing, so it refuses rather than printing a green.
    """
    text = show(repo, tree, CHAT_REL)
    if text is None:
        raise CannotRun("the merge tree %s carries no %s — the merged-fold leg "
                        "has nothing to scan" % (tree[:7], CHAT_REL))
    orphans, _owned = ctc.scan_orphan_drawers(text)
    headlines = len(re.findall(r"^\* MSG ", text, re.M))
    if headlines == 0:
        raise CannotRun("merged %s holds 0 `* MSG` headlines — a merged-fold scan "
                        "over nothing is CANNOT RUN, never a green" % CHAT_REL)
    return len(orphans), headlines


# ---------------------------------------------------------------------- legs
def is_lead_owned(path):
    return (path.startswith(LEAD_OWNED_PREFIXES) or path in LEAD_OWNED_FILES)


def branch_tail(ref):
    """ai/turn-YYYYMMDD-HHMM from any spelling of the ref (register, remote,
    refs/heads) — the landing record names the plain branch, the register may
    not."""
    ref = (ref or "").strip().replace("refs/heads/", "").replace("refs/remotes/", "")
    for cut in ("origin/", "heads/"):
        if ref.startswith(cut):
            ref = ref[len(cut):]
    return ref


def landing_records(repo, main_sha):
    """{branch tail: (record sha, commit date, subject)} over main's history.

    One `git log` read, so the scan costs the same whether the queue holds one
    branch or thirty; a history that will not be read is CANNOT RUN, never a
    quieter green.
    """
    rc, out = git(repo, "log", "--format=%H%x09%ct%x09%s", main_sha)
    if rc != 0:
        raise CannotRun("git log over %s failed — the landing-record scan would "
                        "grade nothing and report every slot as queued"
                        % main_sha[:7])
    found = {}
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, when, subject = parts[0], parts[1], parts[2].strip()
        match = LANDING_RECORD_RE.match(subject)
        if not match or not when.isdigit():
            continue
        tail = match.group(1)
        prev = found.get(tail)
        if prev is None or int(when) >= prev[1]:
            found[tail] = (sha, int(when), subject)
    return found


def tip_date(repo, sha):
    rc, out = git(repo, "log", "-1", "--format=%ct", sha)
    if rc != 0 or not out.strip().isdigit():
        raise CannotRun("%s: no committer date on the branch tip — the landing "
                        "record cannot be ordered against it" % sha[:7])
    return int(out.strip())


def echo_record(repo, sha, tail, records):
    """The landing record that SWALLOWS this branch, or None.

    One ordering rule, both call sites: a record not older than the tip means the
    branch's content is already shipped and the slot is an echo; a record OLDER
    than the tip means the author delivered NEW work after the landing, so the
    branch is genuinely queued again.
    """
    record = records.get(tail)
    if record is None:
        return None
    if record[1] < tip_date(repo, sha):
        return None
    return record


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
        base_orphans, base_heads = orphan_row(ctc, repo, mb)
    else:
        # mb IS main here, so the base state is main's own state — not zero.
        base_orphans, base_heads = orphan_row(ctc, repo, main_sha)
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

    # main's own chat state: the fold bound starts here, and the owed
    # headline count is main's plus this branch's authored headlines.
    main_orphans, main_heads = orphan_row(ctc, repo, main_sha)
    # merge-preview + merged-fold — ONE `git merge-tree` read, two claims taken
    # off it: whether the merge conflicts, and whether the state it produces is
    # legal. A conflict is the first claim's own finding and its output carries
    # markers rather than a chat, so the fold read runs on the conflict-free half.
    rc, out = git(repo, "merge-tree", "--write-tree", main_sha, sha)
    if rc != 0:
        findings.append(("INHERITED", "merge-preview: `git merge-tree %s %s` "
                         "conflicts — an APPROVED verdict here lands as "
                         "'approved+gate-conflict-branch-kept' and waits for a "
                         "manual Lead union-merge (the 0607 class); a rebase "
                         "resolves it before the lane is spent"
                         % (main, short)))
    else:
        tree = out.split("\n", 1)[0].strip()
        if not re.match(r"^[0-9a-f]{40}$", tree):
            raise CannotRun("merge-tree %s %s answered rc 0 but no tree oid "
                            "(%r) — the merged-fold read has no object to scan"
                            % (main, short, tree[:20]))
        mg_orphans, mg_heads = merged_chat(ctc, repo, tree)
        owed_heads = main_heads + (br_heads - base_heads)
        # A merge may carry orphan lines one side already had: main's own, plus
        # whatever this branch authored. Anything past that bound was put there
        # by the merge, which is the only author of a fold.
        bound = main_orphans + max(authored, 0)
        if mg_orphans > bound or mg_heads < owed_heads:
            findings.append(("MERGE-ONLY FOLD", "INHERITED: merging %s into %s "
                             "folds the chat — the merged blob carries %d orphan "
                             "drawer line(s) against the bound %d (main %d + this "
                             "branch's own %d) and %d `* MSG` headline(s) where %d "
                             "are owed. Neither parent carries this: the "
                             "`merge=union` driver reads two appends that open with "
                             "the SAME header lines as common context and welds them "
                             "onto one headline (measured on ai/turn-20261024-1956: "
                             "base/branch/main 0 orphans, merged 2, merge-tree rc 0). "
                             "Repair = rebase onto current %s so the append lands at "
                             "the moved EOF — NOT a content rework, the entries are "
                             "legal on their own bases; the finalize fold-guard "
                             "f3e0f63 will undo this merge after the lane is spent"
                             % (short.split("/")[-1], main, mg_orphans, bound,
                                main_orphans, max(authored, 0), mg_heads, owed_heads,
                                main)))
        else:
            notes.append("merged-fold clean: %d orphan(s) within bound %d, %d "
                         "headline(s) of %d owed"
                         % (mg_orphans, bound, mg_heads, owed_heads))
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
    ran = _LegMarks()

    # slot-live — the register is the single slot the chain spends a lane on
    if slot is None:
        ran.add("slot-live")
        notes.append("slot-live: register empty — no branch is queued for review")
    else:
        ran.add("slot-live")
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

    records = landing_records(repo, main_sha)

    # landed-echo — the class ancestry tests are blind to by design: a SQUASH
    # landing ships the branch's content onto main and deliberately keeps its
    # commits out of main's history (10-do: "defective ancestry kept out of
    # ai/main, branch ref retained"), so `main..branch` still counts commits and
    # slot-live still calls a CLOSED branch queued. Measured cost of not seeing
    # it: run 40231536995 wrote the slot back to 1946@93e0f45 seconds after the
    # Lead landed that very sha, and 10-dp spent a beat correcting the register
    # plus a dispatched review lane on a branch the ruling had already closed.
    ran.add("landed-echo")
    if slot is None:
        notes.append("landed-echo: register empty — nothing is parked to echo")
    else:
        tail = branch_tail(slot["branch"])
        record = records.get(tail)
        live = resolve(repo, "origin/" + tail) or resolve(repo, tail)
        if record is None:
            notes.append("landed-echo: no landing record on %s names %s — the slot "
                         "is genuinely queued" % (main, tail))
        elif live is None:
            notes.append("landed-echo: %s has a landing record (%s) but the branch "
                         "does not resolve here, so its tip cannot be ordered — "
                         "slot-live already named that" % (tail, record[0][:7]))
        else:
            swallowed = echo_record(repo, live, tail, records)
            if swallowed is None:
                notes.append("landed-echo: %s was landed by %s but its tip is NEWER "
                             "(post-landing rework) — the slot parks live work, not "
                             "an echo" % (tail, record[0][:7]))
            else:
                problems.append("landed-echo: the register parks %s, but %s already "
                                "carries a landing record for it — %s %r — and that "
                                "record is not older than the branch tip: the work "
                                "SHIPPED, the slot is a stale echo. Disposition is "
                                "the Lead's (10-dp): close it and advance the "
                                "register with the landing commit as the receipt — a "
                                "review lane spent here grades state the author "
                                "already delivered"
                                % (slot["branch"], main, swallowed[0][:7],
                                   swallowed[2][:120]))

    for short, sha in rows:
        findings, bnotes, stale, orphans = grade_branch(
            ctc, repo, main, main_sha, short, sha)
        for leg in PER_BRANCH_LEGS:
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
    doubled = doubled_legs(ran.counts, len(rows))
    if doubled:
        raise CannotRun("leg(s) marked past their code paths over %d queued "
                        "branch(es): %s — a leg block written twice re-initialises "
                        "the accumulators and silently eats the first copy's "
                        "findings. That is the union-fold class inside this "
                        "harness's own source (measured on slot-live, where the set "
                        "read above could not see a repeat): delete the second "
                        "copy, never bump a pin over it"
                        % (len(rows), "; ".join(doubled)))
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
ENTRY_SIBLING = ("* MSG software-engineer -> @lead :report:      "
                 ":msg:software-engineer:lead:report:\n"
                 ":PROPERTIES:\n"
                 ":FROM: software-engineer\n"
                 ":TO: lead\n"
                 ":KIND: report\n"
                 ":WHEN: [2026-10-25 Sun 08:47 UTC]\n"
                 ":END:\n"
                 "  the other side's entry, same five header lines\n")

# The fold shape: the five header lines eaten, the tail survived.
ORPHAN = (":WHEN: [2026-10-24 Sat 21:00 UTC]\n"
          ":END:\n"
          "  body whose headline was folded away\n")

CONTROL = ("#+TITLE: fixture control (Lead-owned in the real repo)\n"
           "#+PENDING-REVIEW: branch=%s | author=software-engineer | sha=%s\n")

# Mirrors the real .gitattributes: the chat carries the union merge driver, and
# without it a fixture can only ever produce a CONFLICT, never the fold — which
# is the whole class this leg exists to see.
GITATTRIBUTES = ("%s merge=union\n" % CHAT_REL)


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




def commit(repo, msg, force=False, when=None):
    """Commit the tree. `when` is a GIT date string applied to BOTH author and
    committer clocks — the landed-echo controls order a landing record against a
    tip date, and an order decided by wall-clock luck is not a control."""
    sh(repo, "add", "-A", *(["-f"] if force else []))
    env = dict(os.environ)
    if when:
        env["GIT_COMMITTER_DATE"] = when
        env["GIT_AUTHOR_DATE"] = when
    proc = subprocess.run(["git", "-C", repo, "-c", "user.name=f",
                           "-c", "user.email=f@e", "commit", "-qm", msg],
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise CannotRun("fixture commit failed: %s" % proc.stdout)


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
    write(repo, ".gitattributes", GITATTRIBUTES)
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
    """A conflict on a path WITHOUT the union driver — the merge-preview class,
    kept distinct from the fold class so neither control can answer for the
    other. Two identical chat appends do NOT conflict under `merge=union`; they
    fold, which is the next control's job."""
    def branch_edit():
        bump(base, "agent-team/TODOS.org", "** ONGOING an item the branch opened\n")
        commit(base, "turn: edited a non-union file")

    def main_edit():
        bump(base, "agent-team/TODOS.org", "** DONE an item main closed\n")
        commit(base, "main: edited the same non-union file")
    base = fixture()
    _on(base, TURN_BRANCH, branch_edit)
    main_edit()  # `_on` leaves the repo on main
    return base


def c_merge_only_fold():
    """The state ai/turn-20261024-1956 left on main: both sides append an entry
    whose first five lines are identical, `git merge-tree` answers rc 0, and the
    merged blob carries the branch's orphaned drawer tail. Nothing in either
    parent shows it, so this control is the proof the leg reads a state the
    other two reads cannot."""
    def work():
        bump(base, CHAT_REL, ENTRY_SIBLING)
        commit(base, "main: appended a sibling entry at EOF")
    base = fixture()
    _on(base, "main", work)
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


def c_landed_echo():
    """A SQUASH landing, then the register left pointing at the landed branch —
    the 10-dp write-cross, reproduced on real git state. The branch's commits are
    deliberately NOT main's ancestry (that is what a squash means here), so
    slot-live stays green over this fixture and only landed-echo can see the
    work already shipped."""
    base = fixture()
    sh(base, "checkout", "-q", "main")
    sh(base, "merge", "-q", "--squash", TURN_BRANCH)
    commit(base, "union landing of %s (squash) — defective ancestry kept off main"
           % TURN_BRANCH)
    return base


def c_landed_rework():
    """The exemption, graded: an author who ships NEW work on top of the landing
    is queued again, not echoed. The rework commit is dated after the landing
    record on purpose, so the order is decided by the fixture, not by luck."""
    base = c_landed_echo()
    landed = tip_date(base, "main")
    sh(base, "checkout", "-q", TURN_BRANCH)
    sh(base, "reset", "-q", "--hard", "main")
    bump(base, CHAT_REL, ENTRY.replace("21:00 UTC", "21:05 UTC"))
    commit(base, "turn: re-delivered on top of the landing", when=str(landed + 120))
    head = _head(base, TURN_BRANCH)
    sh(base, "checkout", "-q", "main")
    write(base, CONTROL_REL, CONTROL % (TURN_BRANCH, head))
    commit(base, "control: re-park the re-delivered head", when=str(landed + 121))
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


def c_duplicated_leg():
    """The fold this harness carried in its own source (slot-live written twice,
    49f63f3): ONE leg marked from two copies of its block. The block is gone, so
    the control re-creates the SHAPE by letting slot-live mark twice in one pass —
    the doubled-leg door must refuse it, because the set-shaped coverage read saw
    one member either way and never noticed the repeat."""
    base = fixture()
    write(base, CONTROL_REL, "#+TITLE: fixture control\n#+PENDING-REVIEW: \n")
    commit(base, "control: clear the slot")
    old_add = _LegMarks.add
    def add_twice(self, leg):
        old_add(self, leg)
        if leg == "slot-live":
            old_add(self, leg)
    _LegMarks.add = add_twice
    try:
        grade(base, main="main")
    finally:
        _LegMarks.add = old_add
    raise AssertionError("a leg marked twice was not refused")


CONTROLS = [
    ("green queue", c_no_change, 0, "REVIEW PREFLIGHT OK", ()),
    ("branch authored an orphan drawer", c_authored_orphan, 1, "AUTHORED", ("chat-structure",)),
    ("inherited orphan from a stale base", c_inherited_orphan, 1, "INHERITED", ("chat-structure",)),
    ("harness leak file in the tree", c_leak_file, 1, "harness-leak", ()),
    ("Lead-owned file edited by the branch", c_lead_owned_edit, 1, "Lead-owned", ()),
    ("merge-preview conflicts", c_merge_conflict, 1, "merge-preview", ()),
    ("merged chat folds a header (union driver)", c_merge_only_fold, 1,
     "MERGE-ONLY FOLD", ("INHERITED",)),
    ("register names a dead branch", c_slot_branch_gone, 1, "slot-live", ()),
    ("register names an already-merged branch", c_slot_already_merged, 1, "slot-live", ()),
    ("register head sha is stale", c_slot_sha_stale, 1, "slot-live", ()),
    ("register re-parks a squash-landed branch", c_landed_echo, 1, "stale echo",
     ("landed-echo",)),
    ("one leg marked twice (folded leg block)", c_duplicated_leg, 2,
     "marked past their code paths", ()),
    ("rework shipped on top of the landing record", c_landed_rework, 0,
     "post-landing rework", ()),
    ("register empty", c_slot_empty, 0, "register empty", ()),
    ("chat holds no headlines (blind scan)", c_blind_chat, 2, "CANNOT RUN", ()),
    ("main ref unresolvable", c_missing_main_ref, 2, "CANNOT RUN", ()),
    ("leg roster drift", c_roster_drift, 2, "CANNOT RUN", ()),
]
EXPECTED_CONTROLS = 17


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


