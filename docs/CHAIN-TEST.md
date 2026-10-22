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
