# CHAIN-TEST.md — TEST-CHAIN run log (Owner order 2026-10-22)

One line per turn: run id | seat | lane | date.

e489738@ai/turn-20261022-0942 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22
3bb34bc@ai/turn-20261022-0958 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | improvement: close the SESSION collect->restore loop — the restore copies only /sessions-restore/home/agent and drops the qoder lane's own store (usr/local/lib/qoder-home/.qoder), while all three goose lanes run --no-session and therefore never write one
3bb34bc@ai/turn-20261022-1000 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | TEST-T1 check-in (no pending pings, minimax-m3.1-flash:free@goose) — carried over from the 10:24Z attempt, uncommitted in this branch's tree, committed with TEST-T3 (the chat is append-only)
64638cf@ai/turn-20261022-1024 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | TEST-T3 — board + chat state verified (chat append-only: 0 deleted lines since 490ffa0; board carries no TEST-CHAIN item, no ONGOING headline), log closed

## Summary (TEST-CHAIN, 3 turns)

1. Turns: T1 check-in landed (a0dd163), T2 one harness improvement landed (c42be40 + 7b54938), T3 state verification + log close landed (this branch) — every turn committed with the landing gate green (pytest 299 passed, manage.py check 0 issues, no migration drift).
2. Machinery measured: the chat stayed append-only and format-clean (0 deleted lines, 0 malformed drawers across the objective's 8 entries), the board was never touched (it carries no TEST-CHAIN item and no ONGOING headline, so the Lead's parked feature order is intact), and the chain's own stall accounting sits at 0 (agent-team/TEAM-CONTROL.org:10).
3. One defect still open for the Lead: T2's SESSION collect->restore loop is unapplied and re-measured LIVE this turn — the restore copies only the first store (.github/workflows/agent-team.yml:521 and :522) while the collect tars two (:583 and :587), and /sessions-restore was empty at this boot.

## Post-chain handoff (turn 4 — appended AFTER the log was closed at T3; append-only)

- 965956e@ai/turn-20261022-1040 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | turn 4 (post-T3): the SESSION collect->restore defect re-measured LIVE (3 gaps: restore drops the qoder store, collect tars a path goose 1.55 never writes, three goose lanes pass --no-session) and a ready-to-apply proposal patch shipped at docs/session-loop-fix.patch — NOT applied (.github/workflows/* is Lead-owned); gate GREEN (4/4 legs)
- Turn 5 (post-chain, harness): the objective's landed evidence became a COMMAND —
  `scripts/chain_test_check.py` grades it: the three scripted turns each landed as a
  commit that is an ancestor of the main ref, the chat carries the FROM in EVERY
  headline with a complete :PROPERTIES: drawer, inside the objective's window every
  historical chat version is a BYTE prefix of the current one, over the whole history
  no entry ever disappears, the run log holds one well-formed line per turn whose every
  run id resolves to a real commit and whose date agrees with that turn's chat entry,
  and all 14 parked board items are still headlines. `--selftest` runs 8 controls
  against copies and proves every leg can fail (rc 1 / rc 2 as expected). Deliberately
  NOT named `*_diff.py`: that glob IS the landing gate's twin roster, and this grades
  the CHAIN, not a pair of artifacts.
- Turn 6 (post-chain, harness): the SESSION collect->restore defect became a COMMAND —
  `scripts/chain_session_check.py` grades the Lead-owned workflow READ-ONLY: every store
  the collect tar takes is restored to its OWN path (the tar is rooted at /, so each member
  keeps its absolute archive-relative path), no lane runs the CLI with --no-session, the
  collect list covers the goose session store, and the restore dir is created and mounted.
  The shipped tree grades RED on the real defect (rc 1); `--selftest` applies
  docs/session-loop-fix.patch to a COPY and proves the fix turns it GREEN, plus 7 more
  controls that prove each leg can fail (8 controls, rc 0). The patch stays UNAPPLIED —
  .github/workflows/* is Lead-owned.
f1678cd@ai/turn-20261022-1124 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22
f05cd19@ai/turn-20261022-1124 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | TEST-T2 — improvement: the #+TURN: rotation pointer is a no-op in both directions — the pointer->seat grammar's catch-all silently substitutes platform-engineer for ANY pointer value (.github/workflows/agent-team.yml:198-201) and the pointer-advance case writes the SAME constant for every arm (:702-705), so across the 92 commits that touch agent-team/TEAM-CONTROL.org the pointer line changed ONCE and zero pointer commits exist (`git log --oneline --grep=ci-turn` -> 0) while the same file's #+STALL-COUNT changed 89 times — the roster's dormant CI seat (zai/glm-4.7-flash@goose, agent-team/MEMBERS.org:9-11) is unreachable and a typo'd pointer runs the wrong lane instead of the workflow's own "rotation case gap" BLOCKED path (:573); the fix is Lead-owned and NOT applied here

## runs

The first `runs` block above was closed by the FIRST cycle's T3 (2026-10-22 10:33Z), so the
second cycle's T1/T2 lines (:39 and :41) fell below the first `## ` heading — and
scripts/chain_test_check.py reads run lines only from a section named exactly `runs`, so the
re-runnable check was grading the FIRST cycle's four lines while this cycle's three turns sat
invisible below the fold. This block re-lists the second cycle's three turns; nothing above was
edited or removed, and the run ids are this cycle's real branch bases.
f05cd19@ai/turn-20261022-1124 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | TEST-T1 — check-in: which brain/lane ran for this seat (minimax-m3.1-flash:free@goose) and that no @platform-engineer ping was pending; the run id is this turn's branch base (the 11:24Z line at :39 quoted f1678cd, the v0.1.0 release tag's commit — corrected here)
f05cd19@ai/turn-20261022-1124 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | TEST-T2 — improvement: the #+TURN: rotation pointer is a no-op in both directions — the pointer->seat grammar's catch-all silently substitutes platform-engineer for ANY pointer value (.github/workflows/agent-team.yml:198-201) and the pointer-advance case writes the SAME constant for every arm (:702-705), so across the 92 commits that touch agent-team/TEAM-CONTROL.org the pointer line changed ONCE and zero pointer commits exist (`git log --oneline --grep=ci-turn` -> 0) while the same file's #+STALL-COUNT changed 89 times; the roster's dormant CI seat (agent-team/MEMBERS.org:9-11) is unreachable by the dispatch flow; the fix is Lead-owned and was NOT applied
03b5723@ai/turn-20261022-1136 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | TEST-T3 — board + chat state verified with file:line evidence, and this cycle's log closed; the first cycle's `runs` block was already closed, so this cycle's T1/T2 lines had fallen outside it and were invisible to chain_test_check.py (re-listed above)

## Summary (TEST-CHAIN, 3 turns — second cycle, 2026-10-22 11:24Z-11:40Z)

1. Turns: T1 check-in landed (90949af), T2 one harness improvement landed (d655571), T3 this commit — all three reached ai/main through the chain's merge 03b5723, every turn committed with the landing gate green (pytest 299 passed, manage.py check 0 issues, no migration drift).
2. Machinery measured: the chat stayed append-only and format-clean (0 deleted lines since 490ffa0, 0 malformed drawers over 115 entries), the board was never touched (no TEST-CHAIN item, 0 ONGOING headlines, all 14 parked feature items still headlines at agent-team/TODOS.org:9/:176/:418/:469/:592/:648/:816/:1776/:1987/:2468/:2619/:2672/:3008/:3200), and the chain's stall accounting sits at 0 (agent-team/TEAM-CONTROL.org:10) with #+OBJECTIVE-STATE: OPEN (:7, Lead-owned).
3. Two blind spots found, one closed and one reported: the log's `runs` block was closed by the first cycle's T3, so this cycle's T1/T2 lines were invisible to chain_test_check.py (closed here — the three lines are re-listed in the `## runs` continuation above); and the check's DATE cross-check is dead for every entry (scripts/chain_test_check.py:195 keeps the key prefix in the drawer value, so turn_dates at :336 is always empty) — the one-line fix is `cur.split(":", 2)[2].strip()`, NOT applied, for the Lead to dispatch.

## runs

The second cycle's `## runs` block was closed by that cycle's own T3 summary, so this
cycle's T1 line falls below the fold — scripts/chain_test_check.py reads run lines only
from a section named exactly `runs` (parse_log, scripts/chain_test_check.py:231). This
block re-opens it for the third cycle; nothing above was edited or removed.
d862667@ai/turn-20261022-1145 | platform-engineer | minimax-m3.1-flash:free@goose | 2026-10-22 | TEST-T1 — check-in: which brain/lane ran for this seat (minimax-m3.1-flash:free@goose — GOOSE_MODEL=minimax/minimax-m3.1-flash:free, GOOSE_PROVIDER=openai, measured in the seat container); the qoder and zai/glm-4.7-flash@goose arms ahead of it in .turn-inside.sh exited non-zero first, so the elif chain reached the minimax relief lane; no @platform-engineer ping was pending (the only dispatch ever addressed to this seat is agent-team/TEAM-CHAT.org:42, superseded by the TEST-CHAIN objective switch); the run id is this turn's branch base (GITHUB_RUN_ID is unset inside the seat container — measured)
26c690f@ai/turn-20261022-1838 | platform-engineer | qwen3.8-flash@qoder | 2026-10-22 | TEST-T2 — improvement: the SEGREGATION-LAW pending slot cannot bootstrap from an empty #+PENDING-REVIEW, so NO turn branch can ever land again — the only writer that puts an author branch in the slot requires OUTCOME=approved+GATE=green (.github/workflows/agent-team.yml:809), and approved is unreachable while the slot is empty (:704, :706 guard, empty write-back at :840); live state: slot empty (agent-team/TEAM-CONTROL.org:13), 0 `* REVIEW` records (agent-team/REVIEW-LOG.org), this run's review phase printed "no pending branch this run" leaving .turn-review.txt at 0 bytes, no turn merge on ai/main after 58eb342; /tmp replay of the step shows no-pending -> [] and approved -> the branch, so the leg only works in the state it must first produce; invisible to health checks because a non-empty author branch counts as PROGRESS (:1011) and STALL-COUNT stays 0. Fix is Lead-owned (key the write on "old pending retained", not "approved+green", at :809; and add `rejected` to the retain clause at :817 so REVIEW-LOG law 4 holds) — NOT applied here
e846f89@ai/turn-20261022-2039 | platform-engineer | qwen3.8-flash@qoder | 2026-10-22 | TEST-T3 — board + chat state verified with file:line evidence and this cycle's log closed; `python3 scripts/chain_test_check.py` rc 0 on this tree (128 messages, 0 dropped, 9->10 run lines, 14 parked board items, 0 ONGOING)

## Summary (TEST-CHAIN, 3 turns — third cycle, 2026-10-22 18:38Z-20:40Z)

1. Turns: T1 check-in landed (d862667 branch, docs/CHAIN-TEST.md:66), T2 the pending-slot bootstrap finding landed (26c690f, :67; audit-merged by the Lead as 765dbd91 because the very defect it names blocks the CI path), T3 this commit — all three logged, and `python3 scripts/chain_test_check.py` grades rc 0 on this tree.
2. Machinery measured: the chat is intact and format-clean (128 `* MSG` headlines = 128 `:PROPERTIES:` = 128 `:FROM:` = 128 `:END:`; every historical version inside the objective's window is a byte prefix of the current file, 0 entries ever dropped), the board is untouched (0 ONGOING headlines, no TEST-CHAIN item, the 14 parked feature items still headlines at agent-team/TODOS.org:9/:176/:489/:540/:663/:719/:887/:1847/:2058/:2539/:2690/:2743/:3079/:3332), and the Lead-owned files were only read (agent-team/TEAM-CONTROL.org:7/:9/:10/:13).
3. What the state now says: the T2 finding is no longer invisible — `#+STALL-COUNT: 1` (TEAM-CONTROL.org:10, raised by e846f89 "segment no-pending, result none") while `#+PENDING-REVIEW:` is still empty (:13) and REVIEW-LOG.org holds only the two pre-fix REJECTED records (:32 and :44, 19:46Z + 20:10Z), so nothing has landed through the segregation path since the Lead's manual audit-merge 765dbd91; the fix stays Lead-owned and unapplied.

## Post-chain fix (fourth cycle, seat software-engineer — appended AFTER the closed log; prose only, so `parse_log` reads no run line here)

- The blind spot the second cycle's T3 left for dispatch (Summary item 3: "the check's
  DATE cross-check is dead for every entry") is CLOSED, and it had a SECOND cause the
  report did not see. (1) The drawer value was read with `cur.split(":", 1)[1]`, which
  keeps the key glued to the value, so every `:WHEN:` came back as
  `WHEN: [2026-10-22 Thu 18` — the fix is `split(":", 2)` and a length guard.
  (2) Even with the value correct, `WHEN_RE` was `^\d{4}-\d{2}-\d{2}` while the FORMAT
  LAW writes an Org INACTIVE timestamp `[YYYY-MM-DD Eee HH:MM UTC]`, so the leading
  bracket matched nothing: measured after fix (1) alone, LOG-DATE was 1/3 turns and the
  one survivor was the single MALFORMED entry (agent-team/TEAM-CHAT.org:5528 writes
  `:WHEN: 2026-10-22 Wed 11:24 UTC` — no brackets, and 2026-10-22 is a Thu). `WHEN_RE`
  is now `^\[?(?P<date>\d{4}-\d{2}-\d{2})`; LOG-DATE reads 3/3 and the shipped check is
  rc 0.
- The ELEVENTH-law population rule, applied to this harness's own legs: a turn whose
  chat entries exist but yield NO parseable `:WHEN:` is now CANNOT RUN naming the parse,
  never a silently skipped comparison. Measured by re-introducing the glued-key read on
  a restored copy: old behaviour `CHAIN-TEST CHECK OK` rc 0 (three cycles of it), new
  behaviour rc 2 `the drawer parse is broken`.
- Two controls were themselves rotted and are fixed, both found by running `--selftest`
  rather than trusting its last recorded rc:
  * `unclosed log summary` cleared only the FIRST `## Summary` heading. The log has
    carried TWO of them since the second cycle closed its own run (:10 and :54), and the
    leg asks whether ANY section starts with "Summary", so one surviving heading kept it
    green — the control answered rc 0 and graded nothing. It now rewrites every
    `## Summary` heading.
  * the new `log date disagrees` control first re-dated only one marker-carrying run
    line; the leg tests set INTERSECTION and each turn is logged by three cycles, so the
    remaining 2026-10-22 lines still agreed with the chat and it answered rc 0 (measured).
    It now re-dates every graded run line. It also re-joins with `splitlines()` + "\n":
    `parse_log` hands back lines WITHOUT their terminator, so writing one of those into a
    `splitlines(True)` list drops the newline and silently merges two run lines into one —
    measured as `LOG: 8 run line(s)` where the tree holds 9.
- Control roster pinned, not derived: `EXPECTED_CONTROLS = 10` is asserted against
  `len(CONTROLS)` at the top of `selftest`, so a deleted control is CANNOT RUN instead of
  a shorter `SELFTEST OK`. Measured: the pin set to 9 answers rc 2.
- MEASURED this segment: `python3 scripts/chain_test_check.py` rc 0 (3 turns landed, 128
  chat messages, 9 run lines, LOG-DATE 3/3); `--selftest` rc 0 (10 controls, each landing
  its own rc as specced). `scripts/chain_test_check.py` is NOT in `landing_gate.py`'s
  `EXPECTED_TWINS` roster (it is not a `*_diff.py` harness), so no twin roster moved. The
  published control count was retyped by hand, in the SAME commit, in the two mirror docs
  that publish it as an instruction (`AGENTS.md` ## Commands and `docs/DEVGUIDE.md`
  ## Commands, 8 -> 10) — and NO harness grades it: `release_readiness.py`'s doc-count leg
  knows only `DOC_PIN_NAMES = {"pytest", "vitest"}` (:180), so a control count carries no
  pin beyond the harness's own `EXPECTED_CONTROLS`. FOR THE LEAD: a doc count of the shape
  `N controls` is the same "published as an instruction" class and could join that leg.
- REPORTED, NOT FIXED (append-only law + Lead-owned entry): agent-team/TEAM-CHAT.org:5528
  carries the malformed `:WHEN:` above — the harness tolerates it by the optional bracket,
  and a seat cannot repair another seat's entry.

## runs

Earlier `runs` blocks were each closed by their own cycle's summary, so a later turn's line
falls outside every one of them and `parse_log` (scripts/chain_test_check.py) reads nothing —
this block re-opens it for the ALL-TODOS-drive review queue rather than editing a closed one.
59d8194@ai/turn-20261024-2110 | software-engineer | qodercli body (brain not seat-observable; GOOSE_MODEL empty, #+TURN named codebuddy) | 2026-10-24 | review-preflight harness: the queue graded BEFORE a lane is paid — 12 branches, 16 findings, 7 INHERITED chat-structure reds, 2 merge-preview conflicts, register branch 0633 among them
2ed08e2@ai/turn-20261025-2230 | relief-engineer | qoder body (SEAT=relief-engineer and QODER_CLI=1 measured in-segment; the qoder arm is the FOURTH elif of the relief lane .github/scripts/turn_segment.sh:373-400, after zai/glm-4.7-flash -> poolside/laguna-s-2.1:free -> qwen/qwen3.8-27b@groq, so the three goose arms ahead of it exited non-zero THIS run; ambient GOOSE_MODEL here is the image default openrouter/nvidia nemotron, not an arm recipe) | 2026-10-25 | TEST-T2 — improvement: `scripts/review_preflight_check.py` is never invoked by the chain (grep -c review_preflight -> .github/scripts/turn_segment.sh 0, .github/workflows/agent-team.yml 0, .github/workflows/agent-review.yml 0; harness_roster_check's own LIVE line: 2 of 17 graders are invoked under .github/) — so the register burned four reviewer lanes tonight on ai/turn-20261025-1946 (REVIEW-LOG.org:2668/:2678/:2688 approved+gate-conflict-branch-kept at 20:35/21:01/21:44Z, :2698 review-missing at 22:19Z) although the Lead closed it twice (ce4a67f squash landing, 127ee8b 10-do, c60fcb8 10-dp) and the harness predicts the conflict in 2.3 s; the ask is ONE advisory step before the reviewer arm, `|| true` in the shape agent-team.yml:977 already uses, never a hard gate (20 of 27 queued branches are conflict-bound today, so a hard gate freezes the campaign); the full report is the relief-engineer -> @lead :report: entry appended to agent-team/TEAM-CHAT.org in this same commit
