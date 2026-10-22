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
