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
`.gitattributes:1` declares `agent-team/CHAT.org merge=union` (and `:2` for
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

THE SECOND SHAPE OF THE SAME DEFECT (Lead ruling 2026-10-26 19:16Z, union 54d0d0c)
----------------------------------------------------------------------------------
A folded HEADER is visible: the headline count drops, an orphan drawer floats free of
it. A welded BODY is not. The same dedup rule that eats the five header lines also
eats any OTHER block both sides add identically — and every seat's report ends with
the same SECRET LAW / SEGREGATION tail, so two concurrent appends share 13 lines at
the BOTTOM as well as five at the TOP. Measured on the 35th landing: `chain_merge_check`
answered "merge-tree CLEAN / MERGES AS AUTHORED", the headline count and the orphan
scan agreed, and the union still moved three landed entries' bodies — software-engineer
15:45 lost its 13-line tail (83 -> 70 lines), platform-engineer 16:21 gained a block
that is not its own, software-engineer 15:52 grew 20 -> 28. `chain_test_check` caught it
as three APPEND-ONLY REWRITTEN records only AFTER the merge was on the ref. That read
replays here BEFORE the merge is spent, as the `body-ownership` leg: every entry either
side MOVED out of the merge base must appear in the merged tree with the same body, byte
for byte. It is exact — the merged chat blob this harness computes for 187eefb + 0f50d95
is BYTE-IDENTICAL to the landed union 54d0d0c (measured: `diff` empty over 13,814
lines), so what this leg prints is what the merger will commit, not a model of it.

LEGS (pinned roster — one per claim):
  preview-runs    `git merge-tree` produced a tree for every target; a target that
                  does not resolve, or a merge the plumbing cannot run, is
                  CANNOT RUN (never a quieter green).
  chat-fidelity   every entry this BRANCH appends must still carry its own `* MSG`
                  headline in the merged tree. Two findings: entries whose headline
                  folds (authored > survived) and orphan drawers the merge creates;
                  plus any headline the branch DELETES from the chat (an append-only
                  violation the author can fix before the merge, not after).
  body-ownership  every entry either side MOVED from the merge base — a landed entry
                  main repaired, or the append this branch is delivering — must land
                  in the merged tree with its body byte-identical. A shrink is printed
                  with the exact lines to splice back; a growth is printed with the
                  exact lines that belong to another message, and named as the block
                  its donor lost. An entry whose routing+`:WHEN:` cannot be attributed
                  (no WHEN, a malformed headline, the same identity twice) is reported,
                  never skipped silently, and the leg prints how many bodies it
                  compared. When the chat itself conflicts the merged blob holds
                  conflict markers rather than a merge result, so the leg says it
                  skipped instead of grading markers.
  conflict-paths  the conflicted path list, with each path classified (append-only
                  log / code or doc / Lead-owned) — the union scope the merger needs
                  before it touches anything. Preflight says "conflicts"; it does
                  not say WHERE, so the Lead discovers it mid-merge.
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

Exit codes, the family's three: 0 = every target merges AS AUTHORED (the entry survives
with its own headline AND its own body bytes, no conflict, no pin decision) / 1 = a
finding, with the repair printed / 2 = CANNOT RUN (a leg that cannot evaluate is never
a green).

Deliberately NOT `*_diff.py`: that glob is `scripts/landing_gate.py`'s twin roster
and a file in it must be wired into `EXPECTED_TWINS` — this compares a branch's
PREDICTED MERGE against main, which is not an artifact-and-its-twin identity.

    python3 scripts/chain_merge_check.py                     # the registered pending branch
    python3 scripts/chain_merge_check.py --branch ai/turn-20261024-2326
    python3 scripts/chain_merge_check.py --branch 0f50d95     # a commit, not only a ref name
    python3 scripts/chain_merge_check.py --main 187eefb --branch 0f50d95   # replay a past merge
    python3 scripts/chain_merge_check.py --all               # every unmerged queued branch
    python3 scripts/chain_merge_check.py --selftest          # controls: every leg able to fail

A named target resolves by ANY name git answers to — a raw sha, a local ref, or a
bare `ai/turn-<stamp>` under `origin/` — and is REFUSED when main already carries it,
because previewing a commit main holds grades a no-op merge, not a delivery. The
replay form is how the 35th landing's fold is re-measured in one command: the two
parents of union 54d0d0c name the three welded entries (83 -> 70, 20 -> 28, 111 -> 112)
with their SPLICE/REMOVE blocks, which is the proof this paragraph advertises and which
`--branch <sha>` used to reject as "does not resolve".

SECRET LAW: reads no credential, echoes no value. Lead-owned files are read and
cited only; this harness writes nothing outside a fixture dir it creates itself.
"""

import difflib
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
CHAT_REL = "agent-team/CHAT.org"

LEG_ROSTER = ("preview-runs", "chat-fidelity", "body-ownership", "conflict-paths", "pin-union")
EXPECTED_LEGS = 5

PIN_ASSIGN = re.compile(r"^(EXPECTED_[A-Z0-9_]+)\s*=\s*(\d+)\s*$", re.M)
TREE_OID = re.compile(r"^[0-9a-f]{40}$")
SHA_RE = re.compile(r"[0-9a-fA-F]{7,40}$")
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


def resolve_explicit(repo, ref):
    """An explicit `--branch` target, by ANY name git itself answers to.

    The queued-ref index only holds refs that carry a commit main lacks, so a named
    target falls through here — and this is where a raw commit died: a sha contains
    no `/`, so the old read prefixed `origin/` onto it and asked the remote for a
    branch called `d08bba7`. The proof that needs a PAST merge (replay a landed
    union against its own parents) therefore could only be run by importing grade();
    a harness whose documented paragraph proof is import-only is a harness nobody
    re-runs. Order: a sha-shaped token resolves as a commit; anything else tries the
    name as given, then under `origin/`, because the queue and the register both
    print bare `ai/turn-<stamp>` names while a seat container holds only remote refs.
    """
    if SHA_RE.match(ref):
        return resolve(repo, "%s^{commit}" % ref)
    return resolve(repo, ref) or resolve(repo, "origin/" + ref)


def is_ancestor(repo, sha, other_sha):
    return git(repo, "merge-base", "--is-ancestor", sha, other_sha)[0] == 0


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


# ------------------------------------------------------------------ body identity
def entry_index(text, ctc):
    """identity -> (headline line, body), plus the entries NOTHING can attribute.

    `parse_messages` keys a message by its routing plus its `:WHEN:` — the part the
    FORMAT LAW fixes — and that key is what survives a folded headline, which is why
    body ownership can be graded per entry while a headline count cannot. An entry
    with no WHEN, a headline the routing regex refused, or the SAME identity twice is
    returned in `unattributable`: comparing it against a sibling that shares its empty
    key would be a guess, and a guess here prints as a weld the merge never made.
    """
    index = {}
    counts = {}
    unattributable = []
    if text is None:
        return index, unattributable
    for message in ctc.parse_messages(text):
        ident = message["identity"]
        if ident is None or not message["head_ok"] or not ident[3]:
            unattributable.append(ident or message["headline"])
            continue
        counts[ident] = counts.get(ident, 0) + 1
        index[ident] = (message["line"], message["body"])
    for ident, count in counts.items():
        if count > 1:
            # Two entries with ONE routing+`:WHEN:`: which body is this entry's? A
            # collision is a chat defect in itself, and grading either copy against a
            # merged tree that orders them differently would print a weld that is only
            # the collision, so both copies step out of the compare — counted, printed,
            # never quietly dropped.
            index.pop(ident, None)
            unattributable.append(ident)
    return index, unattributable


def describe_identity(ident):
    seat, to, kind, when = ident
    return "`%s -> @%s :%s:` (`:WHEN: %s`)" % (seat, to, kind, when)


def moved_blocks(wanted_body, got_body):
    """(removed, added) line-blocks, each a list of lines, in file order."""
    want = wanted_body.split("\n")
    got = got_body.split("\n")
    removed = []
    added = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, want, got).get_opcodes():
        if tag in ("delete", "replace"):
            removed.append(want[i1:i2])
        if tag in ("insert", "replace"):
            added.append(got[j1:j2])
    return removed, added


def body_ownership(chat_base, chat_main, chat_branch, chat_merged, ctc, conflicted,
                   headers_folded=False):
    """(findings, note). Every body either side MOVED must land byte-identical.

    Authoritative side per entry: the side that moved it away from the merge base.
    That single rule is what keeps a STALE BASE from wearing a fold's clothes — main
    repaired a landed entry at 570fb3e and branch bases older than that repair still
    carry the folded bytes, so comparing the merged tree against the BRANCH's copy
    would blame the merge for main's own fix. Measured: the registered pending branch
    (turn-20261026-1834, base dcdd930, three landed entries it predates) answers ZERO
    welds here, while the same read over the 35th landing's two parents names the three
    bodies that union 54d0d0c actually welded.
    """
    findings = []
    if CHAT_REL in conflicted:
        return findings, ("bodies: SKIPPED — %s conflicts, so the merged blob holds "
                          "conflict markers, not a merge result (conflict-paths owns it)"
                          % CHAT_REL)
    i_base, u_base = entry_index(chat_base, ctc)
    i_main, u_main = entry_index(chat_main, ctc)
    i_branch, u_branch = entry_index(chat_branch, ctc)
    i_merged, u_merged = entry_index(chat_merged, ctc)
    # DISTINCT unattributable entries, not the sum of four side-lists. One collision
    # that main carries sits in the merge base, in main, in the branch that descends
    # from that base AND in the merged tree, so the sum reported the same chat defect
    # four times — measured live: the registered branch 2213 printed
    # `4 unattributable` for the ONE relief-engineer pair at CHAT.org:10658/:10672
    # that the 2044 ruling names, sending a reader to hunt four defects that are one.
    unattributed = []
    seen_unattributed = set()
    for item in list(u_base) + list(u_main) + list(u_branch) + list(u_merged):
        key = (describe_identity(item) if isinstance(item, tuple) and len(item) == 4
               else str(item))
        if key not in seen_unattributed:
            seen_unattributed.add(key)
            unattributed.append(key)

    graded = 0
    welds = []
    for side, index, other_index in (("main", i_main, i_branch),
                                     ("branch", i_branch, i_main)):
        for ident, (line, body) in index.items():
            base_entry = i_base.get(ident)
            moved = base_entry is None or base_entry[1] != body
            if not moved:
                continue
            other = other_index.get(ident)
            other_moved = other is not None and (base_entry is None or other[1] != base_entry[1])
            if other_moved:
                # Both sides carry different bytes for ONE landed entry: the merge base
                # cannot say which is authoritative, so grade it once, from the branch,
                # and call it what it is — an append-only edit by this branch's author.
                if side != "branch":
                    continue
                graded += 1
                findings.append("AUTHORED  body-ownership: this branch rewrites the landed "
                                "entry %s (main holds %d body line(s), the branch %d) — a "
                                "landed message is append-only, so the merge can only weld "
                                "one side's bytes"
                                % (describe_identity(ident),
                                   len(i_main[ident][1].split("\n")) if ident in i_main else 0,
                                   len(body.split("\n"))))
                continue
            graded += 1
            merged_entry = i_merged.get(ident)
            if merged_entry is None:
                findings.append("INHERITED body-ownership: %s — the entry %s delivers "
                                "VANISHES from the merged tree (its routing+`:WHEN:` is in "
                                "no merged entry): the union ate its headline and its body "
                                "landed under a neighbour's%s"
                                % (("this branch appends" if side == "branch" else "main holds"),
                                   describe_identity(ident),
                                   " — the same fold chat-fidelity above prints the header "
                                   "repair for" if headers_folded else ""))
                continue
            if merged_entry[1] != body:
                welds.append((side, line, ident, body, merged_entry))

    weld_blocks = {}
    for side, line, ident, body, merged_entry in welds:
        weld_blocks[ident] = moved_blocks(body, merged_entry[1])

    for side, line, ident, body, merged_entry in welds:
        removed, added = weld_blocks[ident]
        lost = sum(len(block) for block in removed)
        gained = sum(len(block) for block in added)
        who = ("this branch's own append" if side == "branch" else "a landed entry main holds")
        shape = ("its body SHRINKS by %d line(s)" % lost if lost and not gained else
                 "its body GROWS by %d line(s)" % gained if gained and not lost else
                 "%d line(s) are replaced by %d" % (lost, gained))
        findings.append("INHERITED body-ownership: the merged tree welds %s — %s, %s line "
                        "%d -> merged line %d, %d -> %d body line(s): %s. The union driver "
                        "writes a block ONCE when both sides add it identically, and every "
                        "seat's report ends on the same SECRET LAW / SEGREGATION tail, so no "
                        "headline count and no orphan-drawer scan can see this."
                        % (who, describe_identity(ident), side, line, merged_entry[0],
                           len(body.split("\n")), len(merged_entry[1].split("\n")), shape))
        for block in removed:
            findings.append("    SPLICE these %d line(s) back into the entry above (verbatim "
                            "from its own side):\n      %s" % (len(block), "\n      ".join(block)))
        for block in added:
            donor = None
            for other_ident, (other_removed, _other_added) in weld_blocks.items():
                if other_ident == ident:
                    continue
                if block in other_removed:
                    donor = other_ident
                    break
            findings.append("    REMOVE these %d line(s) from the merged entry — they are the "
                            "welded block%s"
                            % (len(block), " that belongs to %s" % describe_identity(donor)
                               if donor else " that is not this message's"))
    note = ("bodies: %d entry(ies) moved on either side compared against the merged tree, "
            "%d welded, %d unattributable — DISTINCT over the 4 chat sides read, since one "
            "collision inherited from the merge base sits in all of them "
            "(no WHEN / malformed headline / identity reused)%s"
            % (graded, len(welds), len(unattributed),
               (": " + "; ".join(unattributed[:3])
                + (" (+%d more)" % (len(unattributed) - 3) if len(unattributed) > 3 else ""))
               if unattributed else ""))
    return findings, note


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

    # ---- body-ownership: does the merge keep every moved entry's BYTES?
    chat_base = blob(repo, mb, CHAT_REL)
    chat_branch = blob(repo, sha, CHAT_REL)
    if chat_base is None or chat_branch is None:
        raise CannotRun("the merge base or the branch does not carry %s — body ownership "
                        "has no authoritative side to compare the merged tree against"
                        % CHAT_REL)
    body_findings, body_note = body_ownership(chat_base, chat_main, chat_branch,
                                              chat_merged, ctc, conflicts,
                                              headers_folded=bool(authored and survived < authored))
    findings.extend(body_findings)
    notes.append(body_note)
    ran.add("body-ownership")

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
            live = resolve_explicit(repo, ref)
            if live is None:
                raise CannotRun("--branch %s does not resolve in this repo (no such ref, "
                                "no such commit)" % want)
            if is_ancestor(repo, live, main_sha):
                raise CannotRun("--branch %s resolves to %s, which %s already carries — "
                                "merging it is a no-op, so a clean answer here would be a "
                                "green about nothing. Name a target main lacks, or point "
                                "--main at the historical parent to replay a past merge"
                                % (want, live[:7], main))
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
          "appended chat entry keeps its own headline AND its own body bytes in the "
          "merged tree, no path conflicts, no pin needs reconciling" % (n, main), file=out)
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
TURN_BRANCH = "ai/turn-20991231-0000"
# Sentinels a control passes in place of a `--branch` value, resolved to the built
# fixture's REAL objectname by `_capture` — a control must exercise the same argv a
# seat types, and for these two controls that argv is a commit sha.
TIP_SHA = "@tip-sha"
MAIN_TIP_SHA = "@main-tip-sha"
ATTR_UNION = "agent-team/CHAT.org merge=union\n"


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
                 extra_note_conflict=False, register=True, base_extra=""):
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
                            "body": "the entry both sides descend from"}
                 + base_extra)
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
        # A str is a fully built entry (the tail-weld control needs its own body);
        # True is this fixture's default single-line append.
        text = base_chat + (branch_entry if isinstance(branch_entry, str) else ENTRY % {
            "seat": "software-engineer", "when": "2026-10-25 Sun 10:00 UTC",
            "body": "the branch's own report"})
        write(repo, CHAT_REL, text)
    if branch_deletes:
        write(repo, CHAT_REL, base_chat.split("\n", 2)[0] + "\n")
    if branch_bumps_pin:
        write(repo, "scripts/fake_gate.py", GATE_PY % (6, 3))
    if extra_note_conflict:
        write(repo, "notes.md", "shared prose\nbranch line\n")
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
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "--allow-empty", "-m", "main moved")
    return repo


SAME_SEAT_MAIN = ENTRY % {"seat": "software-engineer",
                          "when": "2026-10-25 Sun 11:30 UTC",
                          "body": "main's own report, appended at the same EOF"}
OTHER_SEAT_MAIN = ENTRY % {"seat": "platform-engineer",
                           "when": "2026-10-25 Sun 11:30 UTC",
                           "body": "main appended a DIFFERENT headline, no fold"}

# The block every seat's report really ends on, in miniature: byte-identical, and
# added by BOTH sides of a concurrent append. The union driver writes it once, so
# one entry loses its tail while both HEADLINES stay intact — the shape the
# headline count and the orphan-drawer scan are blind to (union 54d0d0c).
SHARED_TAIL = ("\n"
               "  SECRET LAW: env read by NAME only, values never echoed.\n"
               "  SESSION LAW measured, not asserted: the restore mount is empty.\n"
               "  RESULT: DONE. I lay no verdict on my own branch (SEGREGATION) and\n"
               "  do NOT claim OBJECTIVE-STATE: COMPLETE.")


def c_clean():
    # main never appends at EOF, so nothing competes with the branch's entry.
    return repo_fixture(main_entry=None, branch_bumps_pin=True)


def c_fold():
    return repo_fixture(main_entry=SAME_SEAT_MAIN)


def c_tailweld():
    """Two DIFFERENT seats append at once, so no header folds — but their bodies end
    on the identical 4-line tail block, and the union driver writes that block once.
    The headline count and the orphan scan stay clean; only a body read sees it. This
    is the 54d0d0c shape, and it is the claim the 35th landing paid for."""
    main_e = ENTRY % {"seat": "software-engineer", "when": "2026-10-25 Sun 11:30 UTC",
                      "body": "main's report, ending on the shared tail:" + SHARED_TAIL}
    branch_e = ENTRY % {"seat": "platform-engineer", "when": "2026-10-25 Sun 10:00 UTC",
                        "body": "the branch's report, ending on the same tail:"
                        + SHARED_TAIL}
    return repo_fixture(main_entry=main_e, branch_entry=branch_e)


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


# ONE routing + ONE `:WHEN:` carried by two records: the shape main actually holds
# (CHAT.org:10658/:10672, `relief-engineer -> @lead :report:` on 2026-10-25 Sun
# 05:52 UTC, both bodies empty). Inherited by both sides, so it lands in the merge
# base, in main, in the branch AND in the merged tree at once.
SAME_IDENTITY_PAIR = (
    ENTRY % {"seat": "relief-engineer", "when": "2026-10-25 Sun 05:52 UTC",
             "body": "first record of this identity"}
    + ENTRY % {"seat": "relief-engineer", "when": "2026-10-25 Sun 05:52 UTC",
               "body": "second record, same routing and same WHEN"})


def c_collision_in_base():
    return repo_fixture(base_extra=SAME_IDENTITY_PAIR)


CONTROLS = [
    ("branch merges as authored (no competing EOF append)", c_clean,
     dict(branch_args=[TURN_BRANCH]), 0, "CHAIN MERGE PREVIEW OK", ()),
    ("union fold eats the branch's chat header", c_fold,
     dict(branch_args=[TURN_BRANCH]), 1, "chat-fidelity",
     ("MERGE KEEPS 0 headline", "REPAIR merged line", ":FROM: software-engineer")),
    ("without merge=union the same fold is a loud conflict", c_union_off,
     dict(branch_args=[TURN_BRANCH]), 1, "conflict-paths",
     (CHAT_REL, "bodies: SKIPPED")),
    ("a shared tail block welds one entry's body, headers intact", c_tailweld,
     dict(branch_args=[TURN_BRANCH]), 1, "body-ownership",
     ("SPLICE these", "SECRET LAW: env read by NAME only", "main line 10 -> merged line 10")),
    ("one entry's bytes moved while its headline survived: the count read is satisfied",
     c_tailweld, dict(branch_args=[TURN_BRANCH]), 1,
     "chat: main 2 headlines / merged 3 / this branch authored 1", ()),
    ("a non-chat path conflict is listed and classified", c_note_conflict,
     dict(branch_args=[TURN_BRANCH]), 1, "conflict-paths", ("notes.md",)),
    ("both sides bump one pin -> the union is printed", c_pinunion,
     dict(branch_args=[TURN_BRANCH]), 1, "pin-union",
     ("base 5 -> main 7", "EXPECTED_X = 8")),
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
    # The named-target hole: a sha carries no `/`, so the old read prefixed `origin/`
    # onto it and asked the remote for a branch called `d08bba7` — which is why the
    # replay-a-past-merge proof this harness's own docstring advertises could only be
    # run by importing grade(). Controls pass a real commit objectname, the way a seat
    # types it on the command line.
    ("--branch <sha> names the target by commit", c_clean,
     dict(branch_args=[TIP_SHA]), 0, "CHAIN MERGE PREVIEW OK", ()),
    ("--branch <sha> main already carries is refused as a no-op", c_clean,
     dict(branch_args=[MAIN_TIP_SHA]), 2, "CANNOT RUN",
     ("already carries", "no-op")),
    ("one inherited collision counted once, not once per side", c_collision_in_base,
     dict(branch_args=[TURN_BRANCH]), 0, "1 unattributable",
     ("DISTINCT over the 4 chat sides", "0 welded")),
]
EXPECTED_CONTROLS = 16


def fixture_sha(repo, want):
    """A control's sha sentinel -> the fixture's real objectname; anything else passes
    through untouched, so the argv shape matches what a seat types."""
    if want == TIP_SHA:
        return git(repo, "rev-parse", TURN_BRANCH)[1].strip()
    if want == MAIN_TIP_SHA:
        return git(repo, "rev-parse", "HEAD")[1].strip()
    return want


def _capture(build, kwargs):
    from io import StringIO
    try:
        repo = build()
    except CannotRun as exc:
        return 2, "CANNOT RUN — %s" % exc
    buf = StringIO()
    main = kwargs.get("main", "main")
    branch_args = kwargs.get("branch_args")
    if branch_args:
        branch_args = [fixture_sha(repo, a) for a in branch_args]
    try:
        n, problems, notes = grade(repo, main=main,
                                   branch_args=branch_args,
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
