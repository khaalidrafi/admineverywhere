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
