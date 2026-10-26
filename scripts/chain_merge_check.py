#!/usr/bin/env python3
"""chain_merge_check.py — what the MERGER will actually produce, before it is spent.

THE QUESTION THIS HARNESS ASKS, AND WHY THE QUEUE NEEDS IT ASKED
----------------------------------------------------------------
`scripts/review_preflight_check.py` answers a LANE question: is the queued branch
worth a reviewer's time (stale base, inherited reds, leak file, clean merge-tree).
Its merge-preview leg reports only WHETHER `git merge-tree` conflicts. Nobody in the
family answers the next question, which is the one the objective dies on tonight:
**if the verdict is APPROVED, what does the merged tree hold?**

Measured on the live queue (2026-10-25, against origin/ai/main @ 8514175):

    origin/ai/turn-20261024-2326   merge-tree rc 0  (NO conflict at all)
                                   headlines in main    : 163
                                   headlines in merged  : 163   (+0!)
                                   orphan drawers merged: 2      (+2)

    i.e. the branch appended one legal `* MSG` entry, the merge is CLEAN, the merger
    commits it, and the entry's HEADER IS GONE: the body lands under somebody else's
    headline, so the FORMAT LAW's FROM stops travelling. Exit 0 is the green that
    hides it. The same measurement holds for turn-20261025-0320 (+0 headlines, +2
    orphans) and turn-20261025-0607 (+1 headline for 2 appends, +2 orphans).

WHY IT HAPPENS — THE MECHANISM, NOT THE MYSTERY
-----------------------------------------------
`.gitattributes:1` declares `agent-team/TEAM-CHAT.org merge=union` (and `:2` for
REVIEW-LOG.org) so concurrent EOF appends merge instead of stopping the chain. The
union driver's rule is "keep every added line from both sides, but a line that is
IDENTICAL on both sides is written ONCE". And the FORMAT LAW makes the first five
lines of every report byte-identical between two appends by the same seat:

    * MSG <seat> -> @lead :report:      :msg:<seat>:lead:report:
    :PROPERTIES:
    :FROM: <seat>
    :TO: lead
    :KIND: report

Only `:WHEN:` and the body differ. So the union dedups the five header lines, they
collapse into the previous entry's copy, and the `:WHEN:` / `:END:` tail is left
ownerless. That is the fold `scripts/chain_test_check.py` scan_orphan_drawers()
documents as a landed fact (merge 3b121ee took 81 appended lines and dropped 5 of
them), and it is why the Lead's merge notes read "re-insert the 5 authored header
lines" — a hand repair, repeated per branch, with the queue 13 deep tonight.

WHAT THIS HARNESS DOES
----------------------
Read-only over git (`merge-tree --write-tree` writes objects, not refs; nothing is
checked out, nothing is pushed, no verdict is issued). For a target branch it
pre-computes the merge and grades five claims, then PRINTS THE REPAIR: the exact
header block to re-insert and the merged-file line it belongs above, recovered by
matching the surviving `:WHEN:` value back to the branch's own entry.

LEGS (pinned roster — one per claim):
  preview-runs    `git merge-tree` produced a tree for every target; a target that
                  does not resolve, or a merge the plumbing cannot run, is
                  CANNOT RUN (never a quieter green).
  chat-fidelity   every entry this BRANCH appends must still carry its own `* MSG`
                  headline in the merged tree. Two findings: entries whose headline
                  folds (authored > survived) and orphan drawers the merge creates;
                  plus any headline the branch DELETES from the chat (an append-only
                  violation the author can fix before the merge, not after).
  conflict-paths  the conflicted path list, with each path classified (append-only
                  log / code or doc / Lead-owned) — the union scope the merger needs
                  before it touches anything. Preflight says "conflicts"; it does
                  not say WHERE, so the Lead discovers it mid-merge.
  pin-union       a conflicted python file that carries `EXPECTED_* = <int>` on all
                  three sides gets its arithmetic printed: both sides bumping the
                  same pin is ADDITIVE, so the merged literal is main + (branch -
                  base) — measured on the registered pending branch
                  turn-20261024-2244: EXPECTED_CONTROL_CLAIMS base 5 / main 10 /
                  branch 6 -> UNION 11, which is the number the objective's note
                  asked the Lead to retype by hand.
  main-loss       landing is cumulative: a merge may not silently un-land work that
                  is already on main. Nothing in the family answered this — pin-union
                  speaks only for a CONFLICTED path and only about `EXPECTED_*`
                  integers, conflict-paths says WHERE not WHAT, and preflight says
                  "conflicts" without naming the landed content a hand resolution is
                  about to eat. The leg reads main's OWN post-base diff (`--unified=0`,
                  keyed on its `+++ b/<path>` headers, so every number is a landed line
                  rather than a guess) and dispositions each text/code path three ways:
                  DROPPED from the predicted merged tree (the machine's own union driver
                  writes an identical both-side append ONCE — the only shape that eats a
                  landed line without a conflict), AT RISK because the path conflicts or
                  the branch DELETES it while main landed on it (modify/delete: git keeps
                  main's version in the tree, so the landing dies exactly when a human
                  answers the path from one side), or SAFE, counted in the note. The
                  precedent is landed, not hypothetical: the 1520 union re-materialised
                  the `sha_map` line a delivered branch had removed, and its resolution
                  ate a `docs/CHAIN-TEST.md` record the same way — both were manual
                  repairs discovered AFTER the merge was spent. Measured 2026-10-26 over
                  the live queue: 13 targets, 0 landed lines dropped by the machine, 28
                  AT-RISK findings over 10 of them (5,718 landed lines counted — the very
                  stale 2026-10-22 branches own most of that, and the number is the point:
                  a five-day-old base is not "a few commits", it is a thousand landed
                  lines sitting under a hand resolution), and the register's own pending
                  branch fires —
                  ai/turn-20261026-1556 is based on 8774021 (before the 1520 landing) and
                  conflicts at `docs/CHAIN-TEST.md`, where the line under the conflict IS
                  the 1520 run record: a take-branch-side resolve un-lands the landing
                  that repaired the very file it collides in. The same read answers the
                  part a hand cannot: that branch's AGENTS.md still says `17 controls`
                  while the merged tree carries main's 18 and `_LEG_LEDGER` 3/3, i.e.
                  auto-merge preserved the landing there — proven by reading the merged
                  blob, never assumed.

Exit codes, the family's three: 0 = every target merges AS AUTHORED (the entry
survives, no conflict, no pin decision) / 1 = a finding, with the repair printed /
2 = CANNOT RUN (a leg that cannot evaluate is never a green).

Deliberately NOT `*_diff.py`: that glob is `scripts/landing_gate.py`'s twin roster
and a file in it must be wired into `EXPECTED_TWINS` — this compares a branch's
PREDICTED MERGE against main, which is not an artifact-and-its-twin identity.

    python3 scripts/chain_merge_check.py                     # the registered pending branch
    python3 scripts/chain_merge_check.py --branch ai/turn-20261024-2326
    python3 scripts/chain_merge_check.py --all               # every unmerged queued branch
    python3 scripts/chain_merge_check.py --selftest          # controls: every leg able to fail

SECRET LAW: reads no credential, echoes no value. Lead-owned files are read and
cited only; this harness writes nothing outside a fixture dir it creates itself.
"""

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_REF = "origin/ai/main"
BRANCH_PREFIX = "ai/turn-"
CHAT_REL = "agent-team/TEAM-CHAT.org"
LOG_REL = "docs/CHAIN-TEST.md"
LOG_BASE = "# fixture run log\n## runs\noriginal run line\n"
LOG_RELISTED = "re-listed run line (identical on both sides)\n"

LEG_ROSTER = ("preview-runs", "chat-fidelity", "conflict-paths", "pin-union", "main-loss")
EXPECTED_LEGS = 5

PIN_ASSIGN = re.compile(r"^(EXPECTED_[A-Z0-9_]+)\s*=\s*(\d+)\s*$", re.M)
TREE_OID = re.compile(r"^[0-9a-f]{40}$")
WHEN_FIELD = re.compile(r"^:WHEN:\s*(.*)$")


class CannotRun(Exception):
    pass


_LOADED = {}


def _load(name):
    """Import a sibling harness by file, so a grammar is never re-spelled here.
    Memoised: classify() asks for the Lead-owned law per conflicted path, and a
    700-line module reload per path is not reading a law, it is re-parsing one."""
    if name in _LOADED:
        return _LOADED[name]
    path = os.path.join(ROOT, "scripts", name)
    if not os.path.exists(path):
        raise CannotRun("scripts/%s is missing — this harness reads its law from there" % name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        raise CannotRun("scripts/%s cannot be imported: %s" % (name, exc))
    _LOADED[name] = mod
    return mod


def _ctc():
    mod = _load("chain_test_check.py")
    for attr in ("scan_orphan_drawers", "parse_messages", "HEADLINE_LINE"):
        if not hasattr(mod, attr):
            raise CannotRun("scripts/chain_test_check.py has no %s — the drawer grammar "
                            "this harness grades with moved or vanished" % attr)
    return mod


def _rpc():
    """review_preflight_check's queue + register readers: the same two grammars,
    imported. Re-spelling "which branch is queued" here would fork the lane law
    from the merge law (the EIGHTH law's hazard)."""
    mod = _load("review_preflight_check.py")
    for attr in ("queue_branches", "pending_slot", "is_lead_owned"):
        if not hasattr(mod, attr):
            raise CannotRun("scripts/review_preflight_check.py has no %s — the queue and "
                            "register reading this harness depends on moved" % attr)
    return mod


# ------------------------------------------------------------------ git plumbing
def git(repo, *args):
    proc = subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout


def resolve(repo, ref):
    rc, out = git(repo, "rev-parse", "--verify", "%s^{commit}" % ref)
    return out.strip() if rc == 0 else None


def blob(repo, rev, rel):
    """A file's text at a commit OR at a merge-tree's tree object, or None."""
    rc, out = git(repo, "cat-file", "blob", "%s:%s" % (rev, rel))
    return out if rc == 0 else None


def merge_preview(repo, main_sha, sha):
    """(rc, tree_oid, [conflicted paths]). rc 0 = clean, 1 = conflicts, >1 = no answer."""
    rc, out = git(repo, "merge-tree", "--write-tree", "--name-only", main_sha, sha)
    lines = out.split("\n")
    tree = lines[0].strip() if lines else ""
    if rc > 1 or not TREE_OID.match(tree):
        raise CannotRun("`git merge-tree --write-tree %s %s` answered rc %d with no tree "
                        "object — the merge cannot be previewed, so nothing below is "
                        "known about it" % (main_sha[:7], sha[:7], rc))
    paths = []
    for line in lines[1:]:
        if not line.strip():
            break
        paths.append(line.strip())
    return rc, tree, paths


def headlines(text):
    return len(re.findall(r"^\* MSG ", text, re.M))


def diff_headlines(repo, base, sha):
    """(+headline, -headline) lines this branch's own edits moved in the chat."""
    rc, out = git(repo, "diff", "--unified=0", base, sha, "--", CHAT_REL)
    if rc != 0:
        raise CannotRun("git diff %s..%s -- %s failed" % (base[:7], sha[:7], CHAT_REL))
    added = removed = 0
    for line in out.splitlines():
        if line.startswith("+") and not line.startswith("++"):
            if line[1:].startswith("* MSG "):
                added += 1
        elif line.startswith("-") and not line.startswith("--"):
            if line[1:].startswith("* MSG "):
                removed += 1
    return added, removed


def orphan_texts(orphan_list):
    return Counter(text for _n, text, _o in orphan_list)


def new_orphans(main_orphans, merged_orphans):
    """Merged orphans that main does not already carry — the merge's own damage,
    multiset-matched on the field text so an inherited orphan is not blamed here."""
    pool = orphan_texts(main_orphans)
    fresh = []
    for number, text, owner in merged_orphans:
        if pool[text] > 0:
            pool[text] -= 1
        else:
            fresh.append((number, text, owner))
    return fresh


def when_of(text):
    match = WHEN_FIELD.match(text)
    return match.group(1).strip() if match else None


def branch_entries(repo, sha, ctc):
    """This branch's own chat entries: {WHEN value: (headline, header block lines)}.

    The fold leaves `:WHEN:` and `:END:` behind and eats the five lines above them,
    so WHEN is the only surviving key that identifies WHICH message lost its header
    — that is how the repair below is recovered instead of guessed.
    """
    text = blob(repo, sha, CHAT_REL)
    if text is None:
        raise CannotRun("%s does not carry %s" % (sha[:7], CHAT_REL))
    out = {}
    for message in ctc.parse_messages(text):
        drawer = message["drawer"]
        when = (drawer.get("WHEN") or "").strip()
        if not when:
            continue
        block = [message["headline"]]
        keys = ["PROPERTIES"] + [k for k in ("FROM", "TO", "KIND") if k in drawer]
        for key in keys:
            if key == "PROPERTIES":
                block.append(":PROPERTIES:")
            else:
                block.append(":%s: %s" % (key, drawer[key]))
        block.append(":WHEN: %s" % when)
        block.append(":END:")
        out.setdefault(when, block)
    return out


def when_near_merged(merged_lines, number):
    """The WHEN value governing an orphan tail: the orphan itself, else the nearest
    `:WHEN:` within a few lines either way (the fold leaves WHEN above `:END:`, and
    `:END:` right below it)."""
    own = when_of(merged_lines[number - 1]) if 0 < number <= len(merged_lines) else None
    if own is not None:
        return own
    for offset in (-1, 1, -2, 2, -3, 3):
        index = number - 1 + offset
        if 0 <= index < len(merged_lines):
            when = when_of(merged_lines[index])
            if when is not None:
                return when
    return None


# ------------------------------------------------------------------------ legs
def classify(repo, main_sha, path):
    rpc = _rpc()
    if rpc.is_lead_owned(path):
        return "LEAD-OWNED (a seat cannot resolve it; the merger must)"
    if path.endswith(".org"):
        return "append-only log (union the two appends, keep every headline)"
    if path.endswith(".py") and blob(repo, main_sha, path) is not None:
        return "code"
    return "doc/text"


MAIN_LOSS_EXTS = (".py", ".md", ".ts", ".json", ".txt", ".sh", ".yml", ".toml", ".scm")


def _deleted_paths(repo, mb, sha):
    """Paths this commit removed since the base — the modify/delete half of the
    resolver's hazard: git leaves the OTHER side in the tree and announces it, so a
    one-sided `checkout` answers it by destroying the surviving landings."""
    rc, out = git(repo, "diff", "--diff-filter=D", "--name-only", "--no-renames", mb, sha)
    if rc != 0:
        return set()
    return set(p for p in out.splitlines() if p.strip())


def _added_lines(repo, mb, sha):
    """{path: Counter(lines this side ADDED since the base)} — multiplicity kept,
    so a line that legitimately appears twice is not read as one lost line. The
    `+++ b/<path>` header is the only reliable key: a unified diff carries no other
    per-hunk filename."""
    rc, out = git(repo, "diff", "--unified=0", "--no-color", "--no-renames", mb, sha)
    if rc != 0:
        return None
    by_path = {}
    current = None
    for line in out.split("\n"):
        if line.startswith("+++ b/"):
            current = line[6:].rstrip("\r")
            if current == "/dev/null":
                current = None
            else:
                by_path.setdefault(current, Counter())
        elif line.startswith("--- "):
            continue
        elif line.startswith("+") and not line.startswith("+++") and current:
            text = line[1:].rstrip("\r")
            if text.strip():
                by_path[current][text] += 1
    return by_path


def _lost_lines(main_text, merged_text):
    """Lines main carries that the merged tree drops, by multiplicity."""
    if main_text is None:
        return Counter()
    if merged_text is None:
        return Counter(l.rstrip("\r") for l in main_text.splitlines() if l.strip())
    return Counter(l.rstrip("\r") for l in main_text.splitlines() if l.strip()) - \
        Counter(l.rstrip("\r") for l in merged_text.splitlines() if l.strip())


def grade_branch(repo, ctc, main_sha, sha, short):
    """All five claims for one target. Returns (findings, notes)."""
    findings = []
    notes = []
    ran = set()

    rc, tree, conflicts = merge_preview(repo, main_sha, sha)
    ran.add("preview-runs")
    notes.append("merge-tree %s" % ("CLEAN" if rc == 0 else "CONFLICTS(%d)" % len(conflicts)))

    mb_rc, mb_out = git(repo, "merge-base", main_sha, sha)
    if mb_rc != 0:
        raise CannotRun("no merge base between main and %s" % short)
    mb = mb_out.strip()

    # ---- chat-fidelity: does the branch's own entry survive its own merge?
    chat_main = blob(repo, main_sha, CHAT_REL)
    chat_merged = blob(repo, tree, CHAT_REL)
    if chat_main is None or chat_merged is None:
        raise CannotRun("the merged tree or main does not carry %s — the chat-fidelity "
                        "leg has nothing to compare" % CHAT_REL)
    if headlines(chat_main) == 0:
        raise CannotRun("main's %s holds 0 `* MSG` headlines — the orphan scan would "
                        "grade nothing and call a silent merge clean" % CHAT_REL)
    authored, deleted = diff_headlines(repo, mb, sha)
    h_main, h_merged = headlines(chat_main), headlines(chat_merged)
    survived = h_merged - h_main
    main_orphans, _ = ctc.scan_orphan_drawers(chat_main)
    merged_orphans, _ = ctc.scan_orphan_drawers(chat_merged)
    fresh = new_orphans(main_orphans, merged_orphans)

    if deleted:
        findings.append("AUTHORED  chat-fidelity: this branch DELETES %d `* MSG` headline "
                        "line(s) from %s — append-only is broken by the author, before any "
                        "merge runs (the fold class the Lead then has to re-head)"
                        % (deleted, CHAT_REL))
    if authored and survived < authored:
        folded = authored - survived
        blind = ("the merge is CLEAN (rc 0), so a merger that reads only merge-tree "
                 "commits it blind" if rc == 0 else
                 "the merge conflicts too (rc %d), so the fold is discovered mid-union "
                 "unless it is printed beforehand" % rc)
        findings.append("INHERITED chat-fidelity: this branch appends %d chat entr%s and "
                        "the MERGE KEEPS %d headline(s) — %d header block(s) fold away, "
                        "because the union driver declared at `.gitattributes:1` writes a "
                        "line once when both sides add it identically, and the FORMAT LAW's "
                        "first five lines of a same-seat report ARE identical. %s."
                        % (authored, "y" if authored == 1 else "ies", survived, folded, blind))
    if fresh:
        entries = branch_entries(repo, sha, ctc) if authored else {}
        merged_lines = chat_merged.splitlines()
        claimed = {}
        for number, text, owner in fresh:
            when = when_near_merged(merged_lines, number)
            if when in claimed:
                findings.append("  merged line %d (`%s`) is the rest of the SAME folded "
                                "entry as merged line %d — one header block covers both"
                                % (number, text.strip(), claimed[when]))
                continue
            claimed[when] = number
            block = entries.get(when)
            head = ("  REPAIR merged line %d (`%s`, owner headline at line %d)"
                    % (number, text.strip(), owner))
            if block:
                findings.append(head + " — re-insert this header block, verbatim from this "
                                "branch's own entry, above the surviving tail:\n    "
                                + "\n    ".join(block))
            else:
                findings.append(head + " — no branch entry carries `:WHEN: %s`; the tail "
                                "cannot be attributed by this harness, so name the message "
                                "by hand before the merge" % (when or "?"))
    notes.append("chat: main %d headlines / merged %d / this branch authored %d"
                 % (h_main, h_merged, authored))
    ran.add("chat-fidelity")

    # ---- conflict-paths
    if conflicts:
        for path in conflicts:
            findings.append("INHERITED conflict-paths: `%s` conflicts at merge (%s) — an "
                            "APPROVED verdict lands as approved+gate-conflict-branch-kept "
                            "and the merger resolves this path by hand"
                            % (path, classify(repo, main_sha, path)))
    else:
        notes.append("conflicts: none")
    ran.add("conflict-paths")

    # ---- pin-union
    py_conflicts = [p for p in conflicts if p.endswith(".py")]
    for path in py_conflicts:
        text_base = blob(repo, mb, path)
        text_main = blob(repo, main_sha, path)
        text_branch = blob(repo, sha, path)
        if not (text_base and text_main and text_branch):
            findings.append("CANNOT SELF-GRADE pin-union: `%s` conflicts but one of the "
                            "three sides does not carry it, so no arithmetic can be "
                            "printed — resolve it by reading the hunks" % path)
            continue
        base_pins = dict(PIN_ASSIGN.findall(text_base))
        main_pins = dict(PIN_ASSIGN.findall(text_main))
        branch_pins = dict(PIN_ASSIGN.findall(text_branch))
        for name in sorted(set(base_pins) & set(main_pins) & set(branch_pins)):
            b, m, s = int(base_pins[name]), int(main_pins[name]), int(branch_pins[name])
            if s == b and m == b:
                continue
            if s != b and m != b:
                union = m + (s - b)
                findings.append("INHERITED pin-union: `%s` %s moved on both sides "
                                "(base %d -> main %d, base %d -> branch %d); both bumps "
                                "are additive claims, so the merged literal is %s = %d — "
                                "not main's %d and not the branch's %d. Resolve to %d and "
                                "re-run the harness that owns the pin."
                                % (path, name, b, m, b, s, name, union, m, s, union))
            elif s != b:
                notes.append("pin %s: take the branch value %d (main left it at %d)"
                             % (name, s, m))
            else:
                notes.append("pin %s: keep main's %d (branch left it at base %d)"
                             % (name, m, b))
    ran.add("pin-union")

    # ---- main-loss: does this merge put main's already-landed work in the way of a
    # hand resolution? Landing is cumulative, and the loss vector is NOT git's
    # auto-merge — measured 2026-10-26 in throwaway repos: a neighbouring-hunk edit, a
    # whole-file rewrite from the branch's own base and a tail append ALL merge with
    # main's added lines kept (rc 0, no conflicted path). What does drop landed work is
    # the resolver's hand: a path that CONFLICTS (the 1520 union re-materialised the
    # `sha_map` line a delivered branch had deleted, and ate a `CHAIN-TEST.md` record
    # the same way), and a path one side DELETES while the other landed on it (git
    # leaves main's version in the tree and announces modify/delete — a
    # `checkout --theirs` answers it by destroying it). Both are graded here by line
    # COUNT, never by guess: the diff is read with `--unified=0` and its `+++ b/<path>`
    # headers, so every number names lines main added after this branch's own base.
    main_added = _added_lines(repo, mb, main_sha)
    branch_added = _added_lines(repo, mb, sha)
    branch_deleted = _deleted_paths(repo, mb, sha)
    rpc = _rpc()
    if main_added is None or branch_added is None:
        findings.append("CANNOT SELF-GRADE main-loss: a side diff would not parse, so "
                        "nothing about landed lines in this target is known")
        main_added = {}
        branch_added = {}
        main_landing_paths = []
    else:
        main_landing_paths = sorted(
            p for p, added in main_added.items()
            if added and p != CHAT_REL and p.endswith(MAIN_LOSS_EXTS)
            and not rpc.is_lead_owned(p))
    at_risk = 0
    kept_here = 0
    for path in main_landing_paths:
        landed = main_added[path]
        merged_text = blob(repo, tree, path)
        lost = _lost_lines(blob(repo, main_sha, path), merged_text) & landed
        if lost:
            at_risk += sum(lost.values())
            findings.append(
                "%s main-loss: `%s` — the predicted merged tree DROPS %d landed line(s) "
                "main added since base %s (the union driver at `.gitattributes` writes "
                "an identical both-side append ONCE). Lines already gone: %s"
                % ("INHERITED" if path in conflicts else "AUTHORED", path,
                   sum(lost.values()), mb[:7],
                   " / ".join("`%s`" % t.strip()[:70] for t in list(lost)[:3])))
        elif path in conflicts or path in branch_deleted:
            at_risk += sum(landed.values())
            if path in branch_deleted:
                how = ("is DELETED by the branch while main landed on it "
                       "(modify/delete; git leaves main's version in the tree, so the "
                       "landing dies only when the resolver answers the path from the "
                       "branch)")
            else:
                how = "conflicts at merge"
            findings.append(
                "INHERITED main-loss: `%s` %s and main added %d landed line(s) there "
                "since base %s. They survive only if the resolution keeps BOTH sides: "
                "`checkout --ours/--theirs <path>` un-lands them — the `sha_map` "
                "re-materialise on the 1520 union was this exact hazard resolved by "
                "hand. Landings: %s"
                % (path, how, sum(landed.values()), mb[:7],
                   " / ".join("`%s`" % t.strip()[:70] for t in list(landed)[:3])))
        else:
            kept_here += sum(landed.values())
    branch_only_paths = sorted(p for p in (set(main_added) - set(branch_added)
                                           - set(branch_deleted))
                               if main_added[p] and p.endswith(MAIN_LOSS_EXTS)
                               and not rpc.is_lead_owned(p) and p != CHAT_REL)
    branch_only_lines = sum(sum(main_added[p].values()) for p in branch_only_paths)
    if not at_risk:
        notes.append("main-loss: %d landed line(s) across %d path(s) sit in NO "
                     "resolver's way (auto-merged or untouched); %d landed line(s) "
                     "main added since base %s on paths this branch never moved"
                     % (kept_here, len(main_landing_paths), branch_only_lines, mb[:7]))
    ran.add("main-loss")

    verdict = "MERGES AS AUTHORED" if not findings else "%d FINDING(S)" % len(findings)
    notes.append(verdict)
    return findings, notes, ran


# --------------------------------------------------------------------- grading
def pick_targets(repo, main, main_sha, branch_args, want_all, rpc):
    _sha, queued = rpc.queue_branches(repo, main, BRANCH_PREFIX)
    index = dict((short, (short, sha)) for short, sha in queued)
    by_tail = {}
    for short, sha in queued:
        by_tail.setdefault(short.split("/")[-1], (short, sha))
    if want_all:
        return list(queued)
    if not branch_args:
        slot = rpc.pending_slot(repo, main_sha)
        if slot is None or not slot["branch"]:
            raise CannotRun("no target: the register's pending slot is empty and neither "
                            "--branch nor --all was given — an empty grade is not a green")
        branch_args = [slot["branch"]]
    rows = []
    for want in branch_args:
        ref = want.replace("refs/heads/", "")
        row = index.get(ref) or by_tail.get(ref.split("/")[-1])
        if row is None:
            live = resolve(repo, ref if "/" in ref else "origin/" + ref)
            if live is None:
                raise CannotRun("--branch %s does not resolve in this repo (no such ref, "
                                "or it carries no commit main lacks)" % want)
            row = (ref, live)
        rows.append(row)
    return rows


def grade(repo, main=MAIN_REF, branch_args=None, want_all=False):
    if len(LEG_ROSTER) != EXPECTED_LEGS:
        raise CannotRun("LEG_ROSTER lists %d leg(s), EXPECTED_LEGS pins %d — the roster of "
                        "this harness changed without its pin" % (len(LEG_ROSTER), EXPECTED_LEGS))
    ctc = _ctc()
    rpc = _rpc()
    main_sha = resolve(repo, main)
    if main_sha is None:
        raise CannotRun("main ref %s does not resolve in %s — the merge preview has no "
                        "first parent" % (main, repo))
    rows = pick_targets(repo, main, main_sha, list(branch_args or []), want_all, rpc)
    if not rows:
        raise CannotRun("the target list is empty — with --all that means no queued "
                        "branch carries a commit main does not, so there is nothing to "
                        "merge and reporting OK would be a lie about the queue")

    problems = []
    notes = []
    ran = set()
    for short, sha in rows:
        findings, bnotes, bring = grade_branch(repo, ctc, main_sha, sha, short)
        ran |= bring
        tail = short.split("/")[-1]
        for text in findings:
            problems.append("%s  %s" % (tail, text))
        notes.append("%-24s %s" % (tail, "  ".join(bnotes)))

    missing = [leg for leg in LEG_ROSTER if leg not in ran]
    if missing:
        raise CannotRun("leg(s) %s never ran over %d target(s) — the harness is not "
                        "grading what its roster claims" % (", ".join(missing), len(rows)))
    return len(rows), problems, notes


def report(n, problems, notes, main, out=sys.stdout):
    for line in notes:
        print(line, file=out)
    print("", file=out)
    if problems:
        print("CHAIN MERGE PREVIEW RED — %d target(s) previewed against %s, %d finding(s):"
              % (n, main, len(problems)), file=out)
        for p in problems:
            print("  " + p, file=out)
        print("  INHERITED = the merge itself does it (union fold / stale base), the "
              "author's content is not in question: resolve per the printed repair. "
              "AUTHORED = the branch must rework before any merge. The register and the "
              "merge stay the Lead's.", file=out)
        return 1
    print("CHAIN MERGE PREVIEW OK — %d target(s) merge AS AUTHORED against %s: every "
          "appended chat entry keeps its own headline in the merged tree, no path "
          "conflicts, no pin needs reconciling" % (n, main), file=out)
    return 0


# -------------------------------------------------------------------- fixtures
# One seat's report header, the five lines every same-seat report shares verbatim.
ENTRY = ("* MSG %(seat)s -> @lead :report:      :msg:%(seat)s:lead:report:\n"
         ":PROPERTIES:\n"
         ":FROM: %(seat)s\n"
         ":TO: lead\n"
         ":KIND: report\n"
         ":WHEN: [%(when)s]\n"
         ":END:\n"
         "  %(body)s\n")

CONTROL_TMPL = ("#+TITLE: fixture control (Lead-owned in the real repo)\n"
                "#+PENDING-REVIEW: %s\n")
GATE_PY = "# fixture pin carrier (stands in for scripts/release_readiness.py)\n" \
          "EXPECTED_X = %d\nEXPECTED_Y = %d\n"
LANDED_LINE = "LANDED_BY_MAIN = 1  # a fix a later landing put on main\n"
TURN_BRANCH = "ai/turn-20991231-0000"
ATTR_UNION = "agent-team/TEAM-CHAT.org merge=union\n"


def sh(repo, *args):
    rc, out = git(repo, *args)
    if rc != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), out.strip()[:200]))
    return out


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def repo_fixture(main_entry=None, branch_entry=True, main_bumps_pin=False,
                 branch_bumps_pin=False, union=True, branch_deletes=False,
                 extra_note_conflict=False, register=True, branch_deletes_notes=False,
                 main_lands_notes=False):
    """A two-sided queue: main and one turn branch, both legal, then whatever the
    control needs. Real `git commit` objects, real `git merge-tree` — the fold is a
    property of the merge machinery, so the control must run the machinery."""
    tmp = tempfile.mkdtemp(prefix="chain-merge-")
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    sh(repo, "init", "-q", "-b", "main", ".")
    sh(repo, "config", "user.email", "fixture@invalid")
    sh(repo, "config", "user.name", "fixture")
    sh(repo, "config", "commit.gpgsign", "false")
    base_chat = ("#+TITLE: fixture chat\n"
                 + ENTRY % {"seat": "lead", "when": "2026-10-24 Sat 09:00 UTC",
                            "body": "the entry both sides descend from"})
    write(repo, ".gitattributes", ATTR_UNION if union else "")
    write(repo, CHAT_REL, base_chat)
    write(repo, "agent-team/TEAM-CONTROL.org",
          CONTROL_TMPL % (("branch=%s | author=software-engineer | sha=0" % TURN_BRANCH)
                          if register else ""))
    write(repo, "scripts/fake_gate.py", GATE_PY % (5, 3))
    write(repo, "notes.md", "shared prose\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "base")
    sh(repo, "checkout", "-q", "-b", TURN_BRANCH)
    if branch_entry:
        write(repo, CHAT_REL, base_chat + ENTRY % {
            "seat": "software-engineer", "when": "2026-10-25 Sun 10:00 UTC",
            "body": "the branch's own report"})
    if branch_deletes:
        write(repo, CHAT_REL, base_chat.split("\n", 2)[0] + "\n")
    if branch_bumps_pin:
        write(repo, "scripts/fake_gate.py", GATE_PY % (6, 3))
    if extra_note_conflict:
        write(repo, "notes.md", "shared prose\nbranch line\n")
    if branch_deletes_notes:
        os.remove(os.path.join(repo, "notes.md"))
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "turn")
    sh(repo, "checkout", "-q", "main")
    if main_entry:
        # Same seat, same kind: every line above `:WHEN:` is byte-identical to the
        # branch's append. That is the shape the union driver folds.
        write(repo, CHAT_REL, base_chat + main_entry)
    if main_bumps_pin:
        write(repo, "scripts/fake_gate.py", GATE_PY % (7, 3))
    if extra_note_conflict:
        write(repo, "notes.md", "shared prose\nmain line\n")
    if main_lands_notes:
        write(repo, "notes.md", "shared prose\nmain landed record\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "main moved")
    return repo


SAME_SEAT_MAIN = ENTRY % {"seat": "software-engineer",
                          "when": "2026-10-25 Sun 11:30 UTC",
                          "body": "main's own report, appended at the same EOF"}
OTHER_SEAT_MAIN = ENTRY % {"seat": "platform-engineer",
                           "when": "2026-10-25 Sun 11:30 UTC",
                           "body": "main appended a DIFFERENT headline, no fold"}


def c_clean():
    # main never appends at EOF, so nothing competes with the branch's entry.
    return repo_fixture(main_entry=None, branch_bumps_pin=True)


def c_fold():
    return repo_fixture(main_entry=SAME_SEAT_MAIN)


def c_union_off():
    # Without the union driver the same double append is a LOUD conflict; the
    # control proves the attribute is what makes the fold silent.
    return repo_fixture(main_entry=SAME_SEAT_MAIN, union=False)


def c_note_conflict():
    return repo_fixture(main_entry=OTHER_SEAT_MAIN, extra_note_conflict=True)


def c_pinunion():
    return repo_fixture(main_entry=OTHER_SEAT_MAIN, branch_bumps_pin=True,
                        main_bumps_pin=True)


def c_deleted():
    return repo_fixture(main_entry=OTHER_SEAT_MAIN, branch_deletes=True)


def c_blind_chat():
    repo = repo_fixture(main_entry=OTHER_SEAT_MAIN)
    write(repo, CHAT_REL, "#+TITLE: fixture chat\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "blind")
    return repo


def c_missing_main():
    return repo_fixture(main_entry=OTHER_SEAT_MAIN)


def c_roster_drift():
    global LEG_ROSTER
    if len(LEG_ROSTER) != EXPECTED_LEGS:
        raise AssertionError("the drift control needs the intact roster to drift from")
    old = LEG_ROSTER
    LEG_ROSTER = old[:-1]
    try:
        grade(".", main=MAIN_REF, branch_args=["nope"])
    except CannotRun:
        LEG_ROSTER = old
        raise
    LEG_ROSTER = old
    raise AssertionError("roster drift was not refused")


def c_empty_register():
    # No --branch, no --all, and the register slot is blank: refusing is the only
    # honest answer (a grade over zero targets would print as OK).
    return repo_fixture(main_entry=SAME_SEAT_MAIN, register=False)


def c_queue_empty():
    # A branch fully merged into main is not queued: --all must refuse rather than
    # report a green over zero targets.
    repo = repo_fixture(main_entry=OTHER_SEAT_MAIN)
    tip = git(repo, "rev-parse", TURN_BRANCH)[1].strip()
    sh(repo, "merge", "-q", "--no-ff", "-m", "merged", tip)
    write(repo, CHAT_REL, git(repo, "show", "HEAD:%s" % CHAT_REL)[1] +
          ENTRY % {"seat": "lead", "when": "2026-10-25 Sun 12:00 UTC", "body": "tail"})
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "after merge")
    return repo


def c_mainland_conflict():
    # notes.md moves on both sides with DIFFERENT text and main's side carries a
    # landed record, with no chat append competing: the conflict-paths leg already
    # calls this RED, and main-loss must name how much already-delivered work the
    # hand resolution is standing on.
    return repo_fixture(main_entry=None, extra_note_conflict=True)


def c_mainland_delete():
    # The branch deletes a path main landed on after the base: git leaves main's
    # version in the tree (modify/delete), so the ONLY way the landing dies is the
    # resolver answering the path from the branch — which is what must be printed.
    return repo_fixture(main_entry=OTHER_SEAT_MAIN, branch_deletes_notes=True,
                        main_lands_notes=True)


CONTROLS = [
    ("branch merges as authored (no competing EOF append)", c_clean,
     dict(branch_args=[TURN_BRANCH]), 0, "CHAIN MERGE PREVIEW OK", ()),
    ("union fold eats the branch's chat header", c_fold,
     dict(branch_args=[TURN_BRANCH]), 1, "chat-fidelity",
     ("MERGE KEEPS 0 headline", "REPAIR merged line", ":FROM: software-engineer")),
    ("without merge=union the same fold is a loud conflict", c_union_off,
     dict(branch_args=[TURN_BRANCH]), 1, "conflict-paths",
     (CHAT_REL,)),
    ("a non-chat path conflict is listed and classified", c_note_conflict,
     dict(branch_args=[TURN_BRANCH]), 1, "conflict-paths", ("notes.md",)),
    ("both sides bump one pin -> the union is printed", c_pinunion,
     dict(branch_args=[TURN_BRANCH]), 1, "pin-union",
     ("base 5 -> main 7", "EXPECTED_X = 8")),
    ("a conflicted path carries main's landed lines -> named", c_mainland_conflict,
     dict(branch_args=[TURN_BRANCH]), 1, "main-loss",
     ("notes.md", "landed line(s)")),
    ("the branch deletes a path main landed on -> modify/delete named",
     c_mainland_delete,
     dict(branch_args=[TURN_BRANCH]), 1, "main-loss",
     ("notes.md", "modify/delete")),
    ("the branch itself deletes a headline -> AUTHORED", c_deleted,
     dict(branch_args=[TURN_BRANCH]), 1, "chat-fidelity", ("DELETES",)),
    ("chat holds no headline (blind scan)", c_blind_chat,
     dict(branch_args=[TURN_BRANCH]), 2, "CANNOT RUN", ()),
    ("main ref unresolvable", c_missing_main,
     dict(branch_args=[TURN_BRANCH], main="no-such-ref"), 2, "CANNOT RUN", ()),
    ("leg roster drift", c_roster_drift,
     dict(), 2, "CANNOT RUN", ()),
    ("no target and an empty register", c_empty_register,
     dict(), 2, "CANNOT RUN", ("pending slot is empty",)),
    ("--all over a queue with nothing left to merge", c_queue_empty,
     dict(want_all=True), 2, "CANNOT RUN", ("target list is empty",)),
]
EXPECTED_CONTROLS = 13


def _capture(build, kwargs):
    from io import StringIO
    try:
        repo = build()
    except CannotRun as exc:
        return 2, "CANNOT RUN — %s" % exc
    buf = StringIO()
    main = kwargs.get("main", "main")
    try:
        n, problems, notes = grade(repo, main=main,
                                   branch_args=kwargs.get("branch_args"),
                                   want_all=kwargs.get("want_all", False))
        rc = report(n, problems, notes, main, out=buf)
    except CannotRun as exc:
        return 2, "CANNOT RUN — %s" % exc
    finally:
        subprocess.run(["rm", "-rf", os.path.dirname(repo)], capture_output=True)
    return rc, buf.getvalue()


def selftest():
    if len(CONTROLS) != EXPECTED_CONTROLS:
        print("CANNOT RUN — CONTROLS lists %d, EXPECTED_CONTROLS pins %d: the roster this "
              "docstring and the docs publish moved without the pin"
              % (len(CONTROLS), EXPECTED_CONTROLS))
        return 2
    failures = 0
    for name, build, kwargs, want_rc, needle, extras in CONTROLS:
        try:
            rc, text = _capture(build, kwargs)
        except Exception as exc:  # a control that cannot even build is red, never silent
            rc, text = 1, "BUILD ERROR — %s" % exc
        ok = rc == want_rc and needle in text
        for extra in extras:
            ok = ok and extra in text
        if ok:
            print("  %-56s ok (rc %d, %s)" % (name, rc, needle))
        else:
            failures += 1
            print("  %-56s FAIL rc=%d want=%d text=%s"
                  % (name, rc, want_rc, text.replace("\n", " | ")[:300]))
    if failures:
        print("SELFTEST RED — %d control(s) did not land their rc" % failures)
        return 1
    print("SELFTEST OK — %d controls, every leg proved able to fail" % len(CONTROLS))
    return 0


def main(argv):
    repo, main, branch_args, want_all = ROOT, MAIN_REF, [], False
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
            branch_args.append(args[i])
        elif a == "--all":
            want_all = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print("unknown argument %r" % a)
            return 2
        i += 1
    try:
        n, problems, notes = grade(repo, main=main, branch_args=branch_args,
                                   want_all=want_all)
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        return 2
    return report(n, problems, notes, main)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
