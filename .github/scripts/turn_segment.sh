#!/usr/bin/env bash
# TURN SEGMENT SCRIPT — extracted from agent-team.yml seg step
# (GitHub Actions rejects inline run blocks > 21000 expression
# chars; Owner order chain 2026-10-22). Lead-owned file.
# Inputs: env SEG_SEAT (seat id from the control parse step).
# Behavior identical to the former inline block (bash -e).
set -e

SEAT="${SEG_SEAT:-}"
# Read the objective FROM THE FILE, never by template substitution:
# an objective containing quotes/dollars/backticks must never be
# rendered into the script by the workflow template (mesh/01 turn
# 1-5: quoted objective text broke bash parsing -> exit 127 before
# any agent ran).
OBJECTIVE=$(grep -oP '^\#\+OBJECTIVE:\s*\K.*' agent-team/TEAM-CONTROL.org | head -1 || true)
BOARD=agent-team/TODOS.org
SUMMARY="$GITHUB_STEP_SUMMARY"
TOP=$(grep -E '^\*+ (TODO|ONGOING|PENDING|WAIT)' "$BOARD" | head -8 | sed 's/^\*\** //' || true)
BRANCH="ai/turn-$(date -u +%Y%m%d-%H%M)"
git checkout -b "$BRANCH"
echo "TURN_BRANCH=$BRANCH" >> "$GITHUB_ENV"
# TIME LAW (Owner 2026-10-26 10:42Z #hq): the clock-in is AUTOMATED at
# the exact prompt-send moment. The clock lives INSIDE the segment now:
# the agent-org batch lane's AGENT_ORG_CLOCK_CMD runs the clock_in.py
# twin (pinned, no-dup law) at the EXACT send moment, and the
# direct-lane fallback clocks at dispatch time inside the container
# (the batch_send failure path). The host no longer clocks the WORK
# item — one clock per item, never two (the twin is idempotent either
# way); a failed fetch skips the clock, never the segment. The REVIEW
# clock stays host-side at review dispatch (its own clock, R-2-78).
WORK_ITEM=$(grep -E '^\*+ (TODO|ONGOING|PENDING|WAIT|PROGRESS)' "$BOARD" | head -1 | sed 's/^[*]* //' || true)
if [ -z "${WORK_ITEM:-}" ]; then
  echo "clock-in: no open board item — skipped" >> "$SUMMARY"
fi
# REVIEW CLOCK (Owner 2026-10-26 10:55Z): the review leg is a SEPARATE
# clock on its own nested review TODO — clocked here, not on the work
# item. Marker = the pending branch (cited in the review child's
# evidence lines); best-effort like the work clock: a failed fetch or a
# missing review child skips the clock, never the review.
if [ -n "${PENDING_BRANCH:-}" ]; then
  curl -fsSL -H "Authorization: Bearer ${CLOCK_TOKEN:-}" \
    "https://raw.githubusercontent.com/khaalidrafi/agent-team.el/396848263242bb3686f35c12615e5f7da9957e49/agent-team/tools/clock_in.py" \
    -o .clock_in.py \
  && python3 .clock_in.py "$BOARD" "$PENDING_BRANCH" review >> "$SUMMARY" 2>&1 \
  && git add "$BOARD" \
  && git commit -q -m "board: TIME LAW review clock-in at dispatch (Owner 2026-10-26 10:55Z)" \
  || echo "review clock-in: skipped (fetch/match failed) — review continues" >> "$SUMMARY"
  rm -f .clock_in.py
fi
# ----------------------------------------------------------------
# SEGREGATION LAW v2 — DUTY ROLES (Owner 18:14Z "Separate author,
# reviewer and merger roles" + 18:55Z refinement: "author, reviewer,
# merger duties should be performed by capable member roles with
# capabilities") — three distinct CAPABLE ROLES per delivery:
# AUTHOR = the implementation seats in rotation (platform -> relief
#   -> software); QA is OUT of the author rotation.
# REVIEWER = the QA ENGINEER (groq/qwen3.8-27b@goose — Owner
#   rotation order 2026-10-25 ~18:08Z "rotate your hire list";
#   audit-proven reviewer ROLE, FR-R001-FE), ALWAYS, not "whoever is
#   next"; when QA itself authored the pending branch the VISITING
#   SENIOR ENGINEER (glm-5.3@codebuddy) reviews instead. The turn
#   seat NEVER reviews.
# MERGER = the LEAD holds merge authority; the finalize gate is its
#   execution arm — merges ONLY on the duty reviewer's APPROVED
#   verdict, behind the green landing gate, and refuses a reviewer
#   who is the author or not the duty reviewer.
# What the previous finalize left pending:
PENDING_LINE=$(grep -oP '^\#\+PENDING-REVIEW:\s*\K.*' agent-team/TEAM-CONTROL.org | head -1 | xargs || true)
PENDING_BRANCH=$(printf '%s' "$PENDING_LINE" | sed -n 's/^branch=\([^ |]*\).*/\1/p')
PENDING_AUTHOR=$(printf '%s' "$PENDING_LINE" | sed -n 's/.*author=\([^ |]*\).*/\1/p')
PENDING_SHA=$(printf '%s' "$PENDING_LINE" | sed -n 's/.*sha=\([0-9a-f]\{7,40\}\).*/\1/p')
if [ -n "$PENDING_BRANCH" ] && git ls-remote --exit-code --heads origin "$PENDING_BRANCH" >/dev/null 2>&1; then
  git fetch origin "$PENDING_BRANCH" >/dev/null 2>&1 || true
  # ALREADY-MERGED SKIP (Lead, night-2 cycle 9-f, 21:5xZ — run 40024810045
  # evidence: the duty reviewer burned ~15-20 min of the 30-min step budget
  # reviewing pending 2008 AFTER the Lead had already merged it; the author
  # segment then starved and the step timed out = empty-segment + stall).
  # If the pending branch is fully merged into origin/ai/main there is
  # NOTHING to review — clear the duty and hand the whole budget to the
  # author segment. The merger's slot re-read resolves the stale slot via
  # the empty-segment law (AHEAD=0 -> resolved, author branch parks).
  PAHEAD=$(git rev-list --count "origin/ai/main..origin/$PENDING_BRANCH" 2>/dev/null || echo 1)
  if [ "${PAHEAD:-1}" -eq 0 ]; then
    echo "REVIEW DUTY SKIPPED: ${PENDING_BRANCH} is already fully merged into origin/ai/main — nothing to review, author segment gets the full budget"
    PENDING_BRANCH=""; PENDING_AUTHOR=""; PENDING_SHA=""
  else
    echo "REVIEW DUTY: ${PENDING_BRANCH} (author: ${PENDING_AUTHOR:-unknown}) — duty reviewer is called below"
  fi
else
  PENDING_BRANCH=""; PENDING_AUTHOR=""; PENDING_SHA=""
fi
# DUTY-REVIEWER selection (determined BEFORE the brief is built).
# ROTATION (Owner order 2026-10-25 ~18:08Z "rotate your hire list"):
# duty reviewer member -> groq/qwen3.8-27b@goose (QA-3 hire, MEMBERS
# wave 2). Evidence: 17 consecutive review-missing probes #5-#22 with
# ZERO artifacts — deterministic qoder-side brain substitution
# (episodes #8-#13, transcripts 453/455); the qoder deepseek lane is
# DEMOTED to in-lane fallback below. Recipe proven in this repo's
# author relief arm (probe 200, GROQ_API_KEY in repo secrets).
QA_MEMBER="groq/qwen3.8-27b@goose"
VISITING_MEMBER="glm-5.3@codebuddy"
REVIEWER_ROLE=""; REVIEWER_MEMBER=""; REVIEWER_SEAT=""
if [ -n "$PENDING_BRANCH" ]; then
  # AUTHOR-ID FORMAT FIX (night-watch 2026-10-22 ~20:15Z, measured in
  # REVIEW-LOG runs 19:46Z + 20:10Z): PENDING_AUTHOR carries the SEAT KEY
  # (e.g. quality-assurance-engineer), not the member id — comparing it
  # to $QA_MEMBER never matched, so QA reviewed its own branch and the
  # brief forced reviewer-equals-author REJECTED twice. Match BOTH forms.
  if [ "${PENDING_AUTHOR:-}" = "quality-assurance-engineer" ] || [ "${PENDING_AUTHOR:-}" = "$QA_MEMBER" ]; then
    REVIEWER_ROLE="Visiting Senior Engineer"; REVIEWER_MEMBER="$VISITING_MEMBER"; REVIEWER_SEAT="visiting-engineer"
  else
    REVIEWER_ROLE="QA Engineer"; REVIEWER_MEMBER="$QA_MEMBER"; REVIEWER_SEAT="quality-assurance-engineer"
  fi
fi
# Reviewer brief (host-built, passed into the container; the
# review is a SEPARATE lane call from the author's segment —
# different duty, different brief, read-only).
REVIEW_BRIEF=""
if [ -n "$PENDING_BRANCH" ]; then
  REVIEW_BRIEF="REVIEW DUTY (SEGREGATION LAW v2, Owner 18:14Z + 18:55Z refinement: duties belong to capable member roles — author, reviewer and merger are SEPARATE roles; no seat merges its own work).
You are the DUTY REVIEWER: ${REVIEWER_ROLE}, member ${REVIEWER_MEMBER}. Pending branch: ${PENDING_BRANCH} (authored by ${PENDING_AUTHOR:-unknown}, head ${PENDING_SHA:-unknown}).
If the author is the SAME member as you, your verdict is REJECTED (reason: reviewer-equals-author).
Do this READ-ONLY, in order:
1. git fetch origin ${PENDING_BRANCH} ; git log --oneline origin/ai/main..origin/${PENDING_BRANCH}
2. git diff origin/ai/main...origin/${PENDING_BRANCH} — read EVERY hunk.
3. FAST gate subset ONLY (Lead 2026-10-24 04:45Z, runs 40054713038/40058532383 evidence: reviewers died at max-turns running the FULL gate in-container — vitest alone is 469 tests; 'python' does not exist here, use python3): python3 -m pytest plugin/tests -p no:cacheprovider -q ; python3 demo-backend/manage.py check ; python3 demo-backend/manage.py makemigrations --check — report each rc. Do NOT run vitest/npx/tsc: FE execution is graded by the CI test job on the merge and re-run by the Lead's finalize gate — your duty is the DIFF + LAW review. If a check cannot start, report rc CANNOT and move on — NEVER loop on environment repair (the rig is preinstalled and preflighted).
4. Law check: no secrets in the diff (SECRET LAW); no Lead-owned files edited (.github/workflows/*, agent-team/TEAM-CONTROL.org, .github/scripts/*, .gitattributes) — that list is EXHAUSTIVE: agent-team/TEAM-CHAT.org, agent-team/TODOS.org and docs/CHAIN-TEST.md are lawful seat delivery surfaces (append-only evidence files — grade entry legality, never reject a diff for touching them); the board flip carries :DELIVERED: evidence with branch + sha; TEAM-CHAT entries legal format.
5. Do NOT modify or commit anything — your verdict text is your whole deliverable.
6. REVIEW CLOCK LAW (Owner 2026-10-26 10:55Z): your review time is
   clocked SEPARATELY on a nested TODO — 'review: <parent title>' one
   level under the work item, its own :EFFORT: (in :PROPERTIES:),
   citing branch ${PENDING_BRANCH} in its body (the automation
   matched that citation to clock you in at dispatch). When everything
   is clear YOU set DONE — on the review TODO first, then on the parent
   (the author never grades their own work); CANCELLED/DEFERRED stay
   Lead-only.
7. The LAST line of your answer MUST be exactly one of:
VERDICT: APPROVED
VERDICT: REJECTED — <one line of reasons>"
fi

BRIEF="You are the on-turn member of the admincraft Agent Team, seat ${SEAT}.
TEAM OBJECTIVE (from agent-team/TEAM-CONTROL.org): ${OBJECTIVE}
Law: templates/COMMON.org (canonical manual, khaalidrafi/agent-team.el).
Board: agent-team/TODOS.org. Roster: agent-team/MEMBERS.org.
Manual: agent-team/TEAM-CONTROL.org + agent-team/TEAM.md. Repo context: README.md, HANDOFF.org, ROADLOG.org, TEAM-CHARTER.org.
PEER MESH — ONE CHAT BUFFER (Owner orders 2026-10-20: members talk
to each other — work, share reports, take each other's help, get
dispatches; 16:55: team chat is ONE Org file, direct pings, no
mailbox; 17:55 FORMAT LAW: standard Org format — the headline
carries the FROM, fields ride Org tags + a :PROPERTIES: drawer):
agent-team/TEAM-CHAT.org. Append one message AT EOF in this
EXACT format:
* MSG ${SEAT} -> @<to|all> :<kind>:      :msg:${SEAT}:<to-sans-at>:<kind>:
:PROPERTIES:
:FROM: ${SEAT}
:TO: <to|all>
:KIND: <dispatch|report|request|escalation|review|note>
:WHEN: [YYYY-MM-DD Eee HH:MM UTC]
:END:
<indented body lines>
The headline MUST carry the FROM (Owner: \"Org headings should
contain the FROM content\"); tags + properties drawer = Org
syntax; WHEN is an Org inactive timestamp. Never edit existing
entries — append only. Any Telegram-bound message MUST open with
\"FROM: <seat>\" and \"TO: @owner\" lines (Owner law 17:55).
Handles: @platform-engineer @lead @owner @all.
mailbox/ is a frozen archive — NEVER write there.
TOP BOARD ITEMS (oldest-first):
${TOP}
TIME LAW CLOCK-IN (Owner 2026-10-26 10:42Z): automation clocked an item
in for you at dispatch — ${WORK_ITEM:-none}. NEVER edit :LOGBOOK: clock
entries yourself; the automation owns them (manual clocking exists only
for web/cloud lanes, not this CI).
WORK ORDER — TEST-CHAIN MODE (Owner order 2026-10-22 09:22Z: the
team is validating its own machinery; the feature work order at
the bottom is PARKED until the Lead restores it — do NOT start
feature items). Do EXACTLY ONE item per turn, in this order:
1. TEST-T1 (turn 1): append a check-in to agent-team/TEAM-CHAT.org
   (${SEAT} -> @lead :report: — one line on which brain/lane ran
   for you, RESULT: DONE) AND add one line to docs/CHAIN-TEST.md
   logging: run id, seat, lane, date. NOTHING else.
2. TEST-T2 (turn 2, only if TEST-T1 landed): append a chat entry
   naming ONE concrete improvement you noticed in the
   harness/dispatch flow, and log it in docs/CHAIN-TEST.md.
   NOTHING else.
3. TEST-T3 (turn 3, only if TEST-T2 landed): verify the board and
   chat state (file:line evidence), post a short :report: to
   @lead, and close docs/CHAIN-TEST.md with a 3-line summary.
   NOTHING else.
PARKED FEATURE ORDER (Lead restores after the test — ignore in
TEST-CHAIN MODE):
(RENAMED per Owner 2026-10-23 17:37Z 'Remove the cool naming':
verify-cool-chat-2 -> verify-chat-2, COOL-CHAT-SEND-BACK-2 ->
CHAT-SEND-BACK-2, COOL-PREVIEW -> CHAT-PREVIEW — all three DONE;
historical records keep the old IDs)
NIGHT-2 FEATURE ORDER (Owner 2026-10-23 17:37Z 'Complete rest of
the TODOs' — continuous run; PAUSE-AFTER-TODO OFF tonight):
1. PENDING R-002 docs — the pending branch ai/turn-20261022-2227
   carries 2 stale DEVGUIDE citations (QA rejected it 5x for
   exactly those); fix the citations on the branch, re-deliver.
2. PENDING FR-R001-FE — lifecycle renderer; fix the audit's
   guessed-URL defect, live-verify, re-deliver.
3. TODO FR R-004 kanban view (FE)
4. TODO FR R-005 canonical CSV export (FE:BE)
5. TODO FR R-006 page registration (FE)
6. TODO FR R-008 widget data sources + new charts (FE)
7. TODO FR R-007 RBAC phased (FE:BE)
WORK ONE SEGMENT (time-boxed, max 3 self-attempts per MEMBER LAWS):
1. READ THE TEAM CHAT FIRST (agent-team/TEAM-CHAT.org): scan the
   tail for @${SEAT} pings you have not answered — do the work,
   answer it, or reply BLOCKED with evidence, by appending your
   reply to the chat. Never edit or delete an existing entry;
   never touch other seats' entries.
2. Pick your work toward the TEAM OBJECTIVE: the oldest open board
   item that serves it and matches your role, or any task a peer
   pinged to you in the chat; if none matches, do the smallest
   verifiable improvement that does (docs, tests, CI repair).
3. Do the work IN THIS BRANCH. Small, verifiable, committed.
4. VERIFY before finishing (the landing gate runs the same and
   finalize UNDOES the merge of a red tree — red work never lands).
5. POST TO THE TEAM CHAT (agent-team/TEAM-CHAT.org, append at
   EOF, one headline per message, direct @pings): dispatch
   downstream work to peers, report upstream results with
   evidence (file:line, commit sha), and send :request: /
   :escalation: @lead after 2 failed self-attempts. Taking a
   peer's help IS encouraged — ping them directly.
6. Append a :LOGBOOK: note to the board item you touched: what
   changed + evidence (file:line, commit sha). Never mark DONE
   (that is the Lead's gate).
7. Commit everything on this branch with message 'turn(${SEAT}): ...'.
8. REPORT: append your report to agent-team/TEAM-CHAT.org as
   '${SEAT} -> @lead :report:' (RESULT: DONE | PARTIAL | BLOCKED,
   evidence included). Real runs ALSO post it to YOUR role's Lark
   custom-bot webhook in env ROLE_LARK_WEBHOOK
   (JSON {\"msg_type\":\"text\",\"content\":{\"text\":\"REPORT — <task-id>: <title>\\nFROM: <role> — <model@agent>\\nRESULT: DONE | PARTIAL | BLOCKED\\nEVIDENCE: <file:line / commit sha>\\nNEXT: <what remains>\"}})
   only if it is non-empty; if empty, skip silently and note it
   in the board LOGBOOK. Never put credentials in any message.
9. Never claim the OBJECTIVE complete yourself: a completion claim
   goes to the chat as '${SEAT} -> @lead :report:'; the Lead
   verifies against the objective and only the Lead sets
   OBJECTIVE-STATE: COMPLETE.
10. Do NOT push to ai/main; SEGREGATION LAW (Owner 2026-10-22
    18:14Z: author, reviewer and merger are SEPARATE roles) —
    your branch is NEVER merged by your own run. The NEXT seat
    reviews it (verdict recorded in agent-team/REVIEW-LOG.org)
    and the CI merger merges it ONLY on that reviewer's APPROVED
    verdict. Your chat posts propagate with the branch merge.
11. LEAD-OWNED FILES — never edit, only read and cite:
    .github/workflows/*, agent-team/TEAM-CONTROL.org,
    .gitattributes, .github/scripts/*. Verify plumbing facts with
    file:line evidence in your mail/report instead. (Editing them
    breaks the chain's git permissions and the rotation pointer.)
Boundaries: no spend; no destructive actions; stay in scope of
the item you picked.
SECRET LAW (Owner order 2026-10-21 18:27Z #hq): credentials
NEVER travel in chat, files, commits, or messages — they live
in ENV VARS (repo secrets -> process env, e.g.
QODER_PERSONAL_ACCESS_TOKEN). If you need a credential a peer
holds, ask for its ENV VAR NAME; the peer replies with the NAME
and a has-it confirmation, NEVER the value; you read it from
your OWN environment. Never echo a secret value anywhere. The
SECRET GUARD (.github/scripts/secret-guard.sh) redacts leaked
values from every commit, chat entry, and session artifact
before they reach git history.
SESSION LAW (same Owner order — session files matter): your CLI
session files are collected at the end of the turn, SCRUBBED of
secrets, and uploaded as artifact 'sessions-<seat>-<run>'
(30-day retention). The next turn of YOUR seat restores them
before you run — resume your context (qoder / goose / opencode /
codebuddy session files) instead of starting cold."

# Seat -> body command. Brains come from the baked configs; keys
# come from repo secrets via env. The harness image has the
# bodies preinstalled (Owner order: containers, not CI installs).
# The script lives IN the workspace so the container reads it via
# the mount; the verdict is written back as .turn-result.txt —
# NO shell pipelines anywhere (CI runs bash -o pipefail: a grep
# with no match would silently kill the step — demo/01 turn 5).
cat > "$PWD/.turn-inside.sh" <<'INNER'
#!/usr/bin/env bash
set +e
# SESSION RESTORE (Owner order 18:27Z: session files are
# important — resume with context): the host mounted the seat's
# previous SCRUBBED session tree at /sessions-restore; drop it
# into $HOME before anything runs.
if [ -d /sessions-restore ]; then
  mkdir -p "$HOME"
  if [ -d /sessions-restore/home/agent ]; then
    cp -a /sessions-restore/home/agent/. "$HOME/" 2>/dev/null || true
  else
    cp -a /sessions-restore/. "$HOME/" 2>/dev/null || true
  fi
  # The collect tar is rooted at /, so a store whose member is an ABSOLUTE
  # path keeps that path inside the archive and must be copied back to it.
  # The qoder lanes run with HOME=/usr/local/lib/qoder-home, so their store
  # is collected as usr/local/lib/qoder-home/.qoder (last member of the tar
  # list) and was never restored: the copy above lands the archive root
  # under $HOME, which is not where that CLI reads it. SESSION LAW, graded
  # by scripts/chain_session_check.py leg RESTORE.
  if [ -d /sessions-restore/usr/local/lib/qoder-home/.qoder ]; then
    mkdir -p /usr/local/lib/qoder-home/.qoder
    cp -a /sessions-restore/usr/local/lib/qoder-home/.qoder/. \
      /usr/local/lib/qoder-home/.qoder/ 2>/dev/null || true
  fi
fi
# The plugin is the code under test: link it fast (deps baked).
# Lead fix 21:2xZ cycle 9-e (seat harness-gap report, third seat running):
# bare `python` does not exist in the turn container (only python3) and the
# swallowed error made every seat rediscover the missing rig. Also preflight
# app/node_modules — three seats in a row self-healed an empty husk with a
# manual npm install before the FE gate legs could run.
python3 -m pip install -e /workspace/plugin --no-deps -q 2>/dev/null || true
if [ -d /workspace/app ] && [ ! -d /workspace/app/node_modules/.bin ]; then
  (cd /workspace/app && npm install --no-audit --no-fund -q 2>/dev/null) || true
fi
# -------------------------------------------------------------
# AGENT-ORG BATCH LANE (Owner R-2-77 endgame 2026-10-26 #hq: team CI
# sends run through agent-org).  When the image has emacs-nox + agent-org
# baked, the send goes THROUGH agent-org-batch.el: the SAME prompt-send
# hook an interactive Emacs send fires, and AGENT_ORG_CLOCK_CMD clocks
# the dispatched item at the EXACT send moment (TIME LAW; the
# clock_in.py twin is idempotent).  Exit 42 = fall back to the direct
# CLI lanes below — the batch path only ADDS a working send, never
# removes one; the fallback clock inside batch_send covers them.
printf '%s' "$BRIEF" > /tmp/.turn-brief.txt
{
  printf '%s\n' '#!/usr/bin/env bash'
  printf '%s\n' 'curl -fsSL -H "Authorization: Bearer ${CLOCK_TOKEN:-}" \\'
  printf '%s\n' '  "https://raw.githubusercontent.com/khaalidrafi/agent-team.el/a623e727f23926ad623b0009f50aec8b46c8d3e3/agent-team/tools/clock_in.py" \\'
  printf '%s\n' '  -o /tmp/.clock_in.py 2>/dev/null || exit 0'
  printf '%s\n' 'python3 /tmp/.clock_in.py /workspace/agent-team/TODOS.org "${WORK_ITEM:-}" >/dev/null 2>&1 || true'
  printf '%s\n' 'rm -f /tmp/.clock_in.py'
} > /tmp/.ci-clock.sh
chmod 0755 /tmp/.ci-clock.sh
batch_send() { # $1 provider-id  $2 ACP command  $3 model pin  $4 clock cmd ("" = none)  $5 prompt file  $6 out file
  if [ -x /usr/bin/emacs ] && [ -f /opt/agent-org/agent-org-batch.el ]; then
    if [ -n "${3:-}" ]; then export AGENT_ORG_MODEL="$3"; else unset AGENT_ORG_MODEL || true; fi
    if [ -n "${4:-}" ]; then export AGENT_ORG_CLOCK_CMD="$4"; else unset AGENT_ORG_CLOCK_CMD || true; fi
    AGENT_ORG_PROVIDER="$1" \
    AGENT_ORG_PROVIDER_COMMAND="$2" \
    AGENT_ORG_PROMPT="$5" \
    AGENT_ORG_OUT="$6" \
    AGENT_ORG_TIMEOUT=900 \
    AGENT_ORG_LOAD_PATH="/opt/agent-org" \
    emacs --batch -l /opt/agent-org/agent-org-batch.el \
      --eval '(agent-org-batch-send)' && return 0
    echo "agent-org batch lane failed (rc=$?) — direct CLI lane fallback"
  fi
  [ -n "${4:-}" ] && [ -x "${4:-}" ] && "${4}" || true   # dispatch-time clock for the direct lane
  return 42
}
# ONE batch attempt for this segment's PRIMARY lane; on 42 the proven
# per-seat chains below run unchanged (the honest-lane law: the verdict
# line names the lane that ACTUALLY ran).
seg_via_batch() {
  case "$SEAT" in
    platform-engineer)
      batch_send qoder "env HOME=/usr/local/lib/qoder-home qoder --acp" "" "/tmp/.ci-clock.sh" /tmp/.turn-brief.txt /tmp/.turn-batch-response.txt ;;
    quality-assurance-engineer)
      batch_send qoder "env HOME=/usr/local/lib/qoder-home qoder --acp" "deepseek-v4.1-flash" "/tmp/.ci-clock.sh" /tmp/.turn-brief.txt /tmp/.turn-batch-response.txt ;;
    relief-engineer)
      export GOOSE_PROVIDER=openai GOOSE_MODEL=glm-4.7-flash OPENAI_API_KEY="$ZAI_API_KEY" \
             OPENAI_HOST="https://api.z.ai" OPENAI_BASE_PATH="/api/paas/v4/chat/completions"
      batch_send goose "goose acp" "glm-4.7-flash" "/tmp/.ci-clock.sh" /tmp/.turn-brief.txt /tmp/.turn-batch-response.txt ;;
    software-engineer)
      export CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1
      batch_send codebuddy "codebuddy --acp" "deepseek-v4.1-flash" "/tmp/.ci-clock.sh" /tmp/.turn-brief.txt /tmp/.turn-batch-response.txt
      local rc=$?
      # the dead-socket guard rides the batch path too (run 39834624187:
      # an exit-0 over a dead socket is a FAILED lane)
      [ "$rc" = 0 ] \
        && grep -qE 'ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN|网络请求超时|502 Bad Gateway' /tmp/.turn-batch-response.txt 2>/dev/null \
        && return 42
      return "$rc" ;;
    visiting-engineer)
      export CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1
      batch_send codebuddy "codebuddy --acp" "glm-5.3" "/tmp/.ci-clock.sh" /tmp/.turn-brief.txt /tmp/.turn-batch-response.txt ;;
    *) return 42 ;;
  esac
}
BATCH_OK=0
if seg_via_batch; then
  BATCH_OK=1
  echo "TURN_RESULT=agent-org batch send OK (primary lane via agent-org — clock at the exact send moment)"
fi
# REVIEW PHASE (SEGREGATION LAW v2, Owner 18:14Z + 18:55Z): the
# DUTY REVIEWER is a capable member ROLE, not the turn seat — the
# host already selected REVIEWER_SEAT/REVIEWER_MEMBER and passed
# them in via docker -e. A SEPARATE lane call from the author
# segment below. Read-only: the verdict token lands in
# /workspace/.turn-review.txt and the HOST extracts it; the merger
# (finalize, on LEAD authority) acts only on APPROVED from the
# duty reviewer, who is never the author.
# ADVISORY PREFLIGHT (the TEST-T2 ask, ai/turn-20261025-2230, Lead-wired 2026-10-26):
# the queue graded BEFORE a lane is paid. rc is IGNORED — the queue is red by
# construction while most queued branches carry stale-base notes, so a hard gate
# would freeze the campaign; the finding buys the merger a DISPOSITION (a slot the
# preflight calls conflict-bound or stale should be re-cut or advanced, not
# reviewed) at ~2.3s against the timeout 900 the reviewer arm itself gets.
# || true: the duty-review lane below runs regardless.
python3 scripts/review_preflight_check.py > /workspace/.review-preflight.txt 2>&1 || true
echo "REVIEW-PREFLIGHT: advisory queue grade captured ($(wc -l < /workspace/.review-preflight.txt 2>/dev/null || echo 0) lines, rc ignored) — disposition input, not a gate"
: > /workspace/.turn-review.txt 2>/dev/null || true
# REVIEW BATCH (agent-org send law): the duty reviewer's send goes
# through agent-org too. The REVIEW clock stays host-side at review
# dispatch (its own clock, R-2-78) — the batch send carries no clock
# command, so nothing double-fires.
REVIEW_BATCH_OK=0
if [ -n "$PENDING_BRANCH" ] && [ -n "$REVIEW_BRIEF" ]; then
  printf '%s' "$REVIEW_BRIEF" > /tmp/.turn-review-brief.txt
  case "$REVIEWER_SEAT" in
    quality-assurance-engineer)
      if batch_send qoder "env HOME=/usr/local/lib/qoder-home qoder --acp" "deepseek-v4.1-flash" "" \
             /tmp/.turn-review-brief.txt /workspace/.turn-review.txt; then
        echo "REVIEW: qoder run OK via agent-org batch (review lane: deepseek-v4.1-flash@qoder — lane-budget demotion 2026-10-25)"
        REVIEW_BATCH_OK=1
      fi ;;
    visiting-engineer)
      export CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1
      if batch_send codebuddy "codebuddy --acp" "glm-5.3" "" \
             /tmp/.turn-review-brief.txt /workspace/.turn-review.txt; then
        echo "REVIEW: codebuddy run OK via agent-org batch (visiting senior lane)"
        REVIEW_BATCH_OK=1
      fi ;;
  esac
fi
if [ "$REVIEW_BATCH_OK" = 0 ]; then
if [ -n "$PENDING_BRANCH" ]; then
  # DUTY-REVIEWER lanes (Owner 18:55Z: the review duty belongs to a
  # capable member ROLE, not to whoever happens to hold the turn):
  #   default  -> QA ENGINEER lane: PRIMARY deepseek-v4.1-flash@qoder
  #               (APPLIED 2026-10-26 from the 2156 handover: groq's free
  #               tier cannot carry this repo's AGENTS.md — 22895 tokens
  #               vs 7000 ITPM, MEASURED; scripts/lane_budget_check.py
  #               grades the lane each arm trusts first), FALLBACK
  #               qwen/qwen3.8-27b@goose via groq (Owner rotation
  #               2026-10-25, QA-3 hire) until its budget is measured on
  #               a paid tier
  #   QA authored -> VISITING SENIOR lane (glm-5.3@codebuddy)
  # The turn seat NEVER reviews its own or anyone's work here.
  case "$REVIEWER_SEAT" in
    quality-assurance-engineer)
      # LANE BUDGET (scripts/lane_budget_check.py, measured 2026-10-25 in the
      # lane that died): goose carries the repo's own AGENTS.md in EVERY
      # request — 68878 B = 22895 tokens (req_01m5the92kehhahwngsv266z53), and
      # 22892 in the live workspace lane (req_01m5thd10ream8chgszete560c) —
      # against groq's free-tier input budget of 7000. A goose-on-groq reviewer
      # therefore CANNOT answer its first call in this repo, never; putting it
      # first turned the duty review into review-missing. qoder answers (the
      # turn seat runs on it), so qoder takes the primary slot and groq@goose
      # becomes the fallback until its budget is measured on a paid tier.
      if timeout 900 env HOME=/usr/local/lib/qoder-home \
           qoder -p "$REVIEW_BRIEF" --output-format json --model deepseek-v4.1-flash \
           --permission-mode bypassPermissions --max-turns 60 \
           > /workspace/.turn-review.txt 2>&1; then
        echo "REVIEW: qoder run OK (review lane: deepseek-v4.1-flash@qoder — lane-budget demotion 2026-10-25)"
      else
        echo "REVIEW: qoder lane failed — falling back to groq/qwen3.8-27b@goose"
        env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \
           OPENAI_API_KEY="$GROQ_API_KEY" \
           OPENAI_HOST="https://api.groq.com" \
           OPENAI_BASE_PATH="/openai/v1/chat/completions" \
           timeout 900 goose run -t "$REVIEW_BRIEF" \
           > /workspace/.turn-review.txt 2>&1 || true
      fi
      # A provider rejection is NOT a missing verdict. The extractor greps this
      # file for a VERDICT token; when the session died on the provider's own
      # limit there is no verdict to find, and the branch is parked for a beat
      # that was never spent. Read the markers the provider prints and say so.
      if grep -qE 'Context length exceeded|Rate limit exceeded|too large for model' /workspace/.turn-review.txt 2>/dev/null; then
        echo "REVIEW: provider rejected the review lane — the verdict file is a dead session, not a review"
      fi ;;
    visiting-engineer)
      timeout 900 env CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1 \
        codebuddy -p "$REVIEW_BRIEF" -y --permission-mode bypassPermissions \
        --max-turns 60 --model glm-5.3 \
        > /workspace/.turn-review.txt 2>&1 || true ;;
    *)
      echo "REVIEW: no duty reviewer selected (pending empty or unknown author ${PENDING_AUTHOR:-?})" ;;
  esac
  echo "REVIEW: duty reviewer ${REVIEWER_SEAT:-none} (${REVIEWER_MEMBER:-none}) reviewed ${PENDING_BRANCH}"
else
  echo "REVIEW: no pending branch this run"
fi
fi
if [ "$BATCH_OK" = 0 ]; then
case "$SEAT" in
  platform-engineer)
    # qwen3.8-flash@qoder — the body PROVEN on this team's CI.
    # HOME pinned to the install dir (launcher resolves the real
    # CLI under ITS HOME — runs 39467719908/39477554903 evidence).
    # bypassPermissions: accept_edits denied ALL Bash (git
    # commit/pytest/pip) — seat escalation, run 39488529938.
    # Fallbacks: zai/glm-4.7-flash@goose (acting), then the
    # minimax-m3.1-flash:free relief lane (promo hire 05:33Z).
    if env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=qoder run OK (lane: qwen3.8-flash@qoder)"
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=glm-4.7-flash \
         OPENAI_API_KEY="$ZAI_API_KEY" \
         OPENAI_HOST="https://api.z.ai" \
         OPENAI_BASE_PATH="/api/paas/v4/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (acting lane: zai/glm-4.7-flash@goose)"
    # Lead URL fix 2026-10-22 (run 39752778724 evidence): goose
    # appends /v1/chat/completions to OPENAI_HOST, so the old
    # HOST=https://openrouter.ai/api/v1 produced
    # .../api/v1/v1/chat/completions -> 404 on EVERY turn.
    # Mirrors the proven zai-lane pattern (HOST + BASE_PATH).
    # Relief swap 2026-10-23 (DE TEAM-UPDATE #2 ASK + probe 404 + live
    # catalog check 19:10Z: minimax-m3.1-flash:free DELISTED from
    # OpenRouter — the M3.1 free period ended Oct 22). Replacement:
    # poolside/laguna-s-2.1:free — alive in the catalog, probed every
    # run (429 daily-cap evidence 18:16Z = exists, quota-limited).
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=poolside/laguna-s-2.1:free \
         OPENAI_API_KEY="$OPENROUTER_API_KEY" \
         OPENAI_HOST="https://openrouter.ai" \
         OPENAI_BASE_PATH="/api/v1/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: laguna-s-2.1:free@goose — relief swap 2026-10-23)"
    # Lead lane add 2026-10-22: qwen3.8-27b@groq — GROQ_API_KEY is
    # in repo secrets (probed every run); gives the chain a 4th,
    # independent brain when qoder quota + zai rate-limit die.
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \
         OPENAI_API_KEY="$GROQ_API_KEY" \
         OPENAI_HOST="https://api.groq.com" \
         OPENAI_BASE_PATH="/openai/v1/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: qwen3.8-27b@groq — relief hire 2026-10-22)"
    # mcode arm (Lead 10-eh, board item mcode-lane-activation): the MiniMax
    # coding-agent CLI baked in the harness (ai/turn-20261025-0652@9ea106e)
    # on the Owner-sealed credential (MCODE_AUTH_JSON, 2026-10-25T20:39Z —
    # the Owner's own activation act; DISTINCT from the minimax-m3.1-flash
    # MODEL the 2026-10-24 BURN-LAW bans). LAST-RESORT fallback, never
    # trusted-first: its budget is unmeasured in-lane until the probe job
    # or a real completion answers (probe-first law). Skip-guard measured
    # in the bake: no valid credential -> exec refuses "Sign in to MiniMax"
    # with ZERO requests -> dead-lane record below, never a faked turn.
    elif MC_LOG=/tmp/mcode-lane.log && mkdir -p /tmp/mcode-home/.minimax \
         && printf '%s' "$MCODE_AUTH_JSON" > /tmp/mcode-home/.minimax/auth.json \
         && [ -s /tmp/mcode-home/.minimax/auth.json ] \
         && env HOME=/tmp/mcode-home mcode exec --permission full --output-format json \
              -o /tmp/mcode-out.json --cwd /workspace "$BRIEF" >"$MC_LOG" 2>&1 \
         && ! grep -qE 'Sign in to MiniMax|ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN' "$MC_LOG"; then
      tail -n 3 "$MC_LOG"
      echo "TURN_RESULT=mcode run OK (lane: minimax-agent@mcode — arm wired 2026-10-26)"
    else
      echo "mcode lane not answered (credential empty or provider refusal): $(tail -c 160 ${MC_LOG:-/tmp/mcode-lane.log} 2>/dev/null | tr '\n' ' ')"
      echo "TURN_RESULT=BLOCKED (qoder+zai+laguna+groq+mcode lanes all failed — check the harness)"
    fi
    ;;
  relief-engineer)
    # glm-4.7-flash@goose — second CI seat (rotation arm, Lead fix
    # 2026-10-22 from the T2 finding). ZAI_API_KEY landed in repo
    # secrets 2026-10-22. Same fallback law: independent brains
    # lead, proven lanes cover.
    if env GOOSE_PROVIDER=openai GOOSE_MODEL=glm-4.7-flash \
         OPENAI_API_KEY="$ZAI_API_KEY" \
         OPENAI_HOST="https://api.z.ai" \
         OPENAI_BASE_PATH="/api/paas/v4/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: zai/glm-4.7-flash@goose)"
    # Relief swap 2026-10-23 (DE TEAM-UPDATE #2): minimax :free delisted
    # at source — poolside/laguna-s-2.1:free takes the slot.
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=poolside/laguna-s-2.1:free \
         OPENAI_API_KEY="$OPENROUTER_API_KEY" \
         OPENAI_HOST="https://openrouter.ai" \
         OPENAI_BASE_PATH="/api/v1/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: laguna-s-2.1:free@goose — relief swap 2026-10-23)"
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \
         OPENAI_API_KEY="$GROQ_API_KEY" \
         OPENAI_HOST="https://api.groq.com" \
         OPENAI_BASE_PATH="/openai/v1/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: qwen3.8-27b@groq)"
    elif env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=qoder run OK (lane: qwen3.8-flash@qoder)"
    # mcode arm — same contract as the platform-engineer arm above (Lead
    # 10-eh, mcode-lane-activation): Owner-sealed credential restored to a
    # pinned writable HOME, last-resort fallback, measured skip-guard,
    # dead-lane honesty. Label also fixes the stale minimax name (the
    # 2026-10-23 relief swap made this chain's lanes zai/laguna/groq/qoder).
    elif MC_LOG=/tmp/mcode-lane.log && mkdir -p /tmp/mcode-home/.minimax \
         && printf '%s' "$MCODE_AUTH_JSON" > /tmp/mcode-home/.minimax/auth.json \
         && [ -s /tmp/mcode-home/.minimax/auth.json ] \
         && env HOME=/tmp/mcode-home mcode exec --permission full --output-format json \
              -o /tmp/mcode-out.json --cwd /workspace "$BRIEF" >"$MC_LOG" 2>&1 \
         && ! grep -qE 'Sign in to MiniMax|ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN' "$MC_LOG"; then
      tail -n 3 "$MC_LOG"
      echo "TURN_RESULT=mcode run OK (lane: minimax-agent@mcode — arm wired 2026-10-26)"
    else
      echo "mcode lane not answered (credential empty or provider refusal): $(tail -c 160 ${MC_LOG:-/tmp/mcode-lane.log} 2>/dev/null | tr '\n' ' ')"
      echo "TURN_RESULT=BLOCKED (zai+laguna+groq+qoder+mcode lanes all failed — check the harness)"
    fi
    ;;
  software-engineer)
    # deepseek-v4.1-flash@codebuddy — free-offer hire
    # (Owner order 2026-10-22 #admincraft). Headless tool use
    # must be pre-authorized: -y ALONE still asks on
    # HIGH/CRITICAL tools and headless asks auto-DENY — prose
    # only, exit 0, zero writes (the 2026-10-22 body bug: 3
    # runs, 2 brains, same symptom). Fix per the CLI's own
    # --help + DE analysis (TEAM-CHAT 3b00d4f):
    # --permission-mode bypassPermissions + CODEBUDDY_IS_SANDBOX=1
    # full pass (sanctioned: the job IS an isolated container).
    # HONEST LANE VERDICT (run 39834624187 evidence): the CLI can
    # exit 0 over a DEAD SOCKET — "502 网络请求超时 ... connect
    # ETIMEDOUT 0.0.0.1:443 (target: https://www.codebuddy.ai)" —
    # and the old code recorded "run OK" over zero work. A lane
    # that printed a network failure marker is a FAILED lane: the
    # fallback chain fires and the result line says so.
    CB_LOG=/tmp/cb-lane.log
    CB_RC=0
    env CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1 \
         codebuddy -p "$BRIEF" -y --permission-mode bypassPermissions \
         --max-turns 100 --model deepseek-v4.1-flash >"$CB_LOG" 2>&1 || CB_RC=$?
    CB_BAD=0
    grep -qE 'ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN|网络请求超时|502 Bad Gateway' "$CB_LOG" 2>/dev/null && CB_BAD=1
    if [ "$CB_RC" = 0 ] && [ "$CB_BAD" = 0 ]; then
      tail -n 3 "$CB_LOG"
      echo "TURN_RESULT=codebuddy run OK (lane: deepseek-v4.1-flash@codebuddy)"
    else
      echo "codebuddy lane FAILED rc=$CB_RC network_marker=$CB_BAD: $(head -c 300 "$CB_LOG" | tr '\n' ' ')"
      echo "TURN_RESULT=codebuddy lane failed — trying fallback lanes"
    if env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json --model deepseek-v4.1-flash \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=qoder run OK (lane: deepseek-v4.1-flash@qoder)"
    # BOOST rotation (Owner 2026-10-25 18:21Z "BOOST. SPEED UP.") +
    # probe evidence 18:24Z run 40220339780: codebuddy DEAD (connect
    # failed, RC=124), groq/qwen3.8-27b the ONLY 200-ALIVE free lane
    # -> groq takes the FIRST API-fallback slot ahead of the 429 lanes.
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \
         OPENAI_API_KEY="$GROQ_API_KEY" \
         OPENAI_HOST="https://api.groq.com" \
         OPENAI_BASE_PATH="/openai/v1/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: groq/qwen3.8-27b@goose — boost rotation 2026-10-25)"
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=glm-4.7-flash \
         OPENAI_API_KEY="$ZAI_API_KEY" \
         OPENAI_HOST="https://api.z.ai" \
         OPENAI_BASE_PATH="/api/paas/v4/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: zai/glm-4.7-flash@goose)"
    # Relief swap 2026-10-23 (DE TEAM-UPDATE #2): minimax :free delisted
    # at source — poolside/laguna-s-2.1:free takes the slot.
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=poolside/laguna-s-2.1:free \
         OPENAI_API_KEY="$OPENROUTER_API_KEY" \
         OPENAI_HOST="https://openrouter.ai" \
         OPENAI_BASE_PATH="/api/v1/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: openrouter/laguna-s-2.1:free@goose)"
    # mcode arm — same contract as the platform-engineer arm above (Lead
    # 10-eh, mcode-lane-activation): Owner-sealed credential, last-resort
    # fallback, measured skip-guard, dead-lane honesty.
    elif MC_LOG=/tmp/mcode-lane.log && mkdir -p /tmp/mcode-home/.minimax \
         && printf '%s' "$MCODE_AUTH_JSON" > /tmp/mcode-home/.minimax/auth.json \
         && [ -s /tmp/mcode-home/.minimax/auth.json ] \
         && env HOME=/tmp/mcode-home mcode exec --permission full --output-format json \
              -o /tmp/mcode-out.json --cwd /workspace "$BRIEF" >"$MC_LOG" 2>&1 \
         && ! grep -qE 'Sign in to MiniMax|ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN' "$MC_LOG"; then
      tail -n 3 "$MC_LOG"
      echo "TURN_RESULT=mcode run OK (lane: minimax-agent@mcode — arm wired 2026-10-26)"
    else
      echo "mcode lane not answered (credential empty or provider refusal): $(tail -c 160 ${MC_LOG:-/tmp/mcode-lane.log} 2>/dev/null | tr '\n' ' ')"
      echo "TURN_RESULT=BLOCKED (codebuddy+qoder-ds+zai+laguna+mcode lanes all failed — check the harness)"
    fi
    fi
    ;;
  quality-assurance-engineer)
    # deepseek-v4.1-flash@qoder — free-offer hire (Owner
    # order 2026-10-22 #admincraft). The qoder model flag is
    # UNVERIFIED — if the CLI rejects it the chain self-heals to
    # the next lane; never blocks the segment.
    CB_LOG=/tmp/cb-lane.log
    if env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json --model deepseek-v4.1-flash \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=qoder run OK (lane: deepseek-v4.1-flash@qoder)"
    elif env CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1 \
         codebuddy -p "$BRIEF" -y --permission-mode bypassPermissions \
         --max-turns 100 --model deepseek-v4.1-flash >"$CB_LOG" 2>&1 \
         && ! grep -qE 'ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN|网络请求超时|502 Bad Gateway' "$CB_LOG"; then
      tail -n 3 "$CB_LOG"
      echo "TURN_RESULT=codebuddy run OK (lane: deepseek-v4.1-flash@codebuddy)"
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \
         OPENAI_API_KEY="$GROQ_API_KEY" \
         OPENAI_HOST="https://api.groq.com" \
         OPENAI_BASE_PATH="/openai/v1/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: groq/qwen3.8-27b@goose)"
    elif env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=qoder run OK (lane: qwen3.8-flash@qoder — default brain)"
    # mcode arm — same contract as the platform-engineer arm above (Lead
    # 10-eh, mcode-lane-activation): Owner-sealed credential, last-resort
    # fallback, measured skip-guard, dead-lane honesty.
    elif MC_LOG=/tmp/mcode-lane.log && mkdir -p /tmp/mcode-home/.minimax \
         && printf '%s' "$MCODE_AUTH_JSON" > /tmp/mcode-home/.minimax/auth.json \
         && [ -s /tmp/mcode-home/.minimax/auth.json ] \
         && env HOME=/tmp/mcode-home mcode exec --permission full --output-format json \
              -o /tmp/mcode-out.json --cwd /workspace "$BRIEF" >"$MC_LOG" 2>&1 \
         && ! grep -qE 'Sign in to MiniMax|ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN' "$MC_LOG"; then
      tail -n 3 "$MC_LOG"
      echo "TURN_RESULT=mcode run OK (lane: minimax-agent@mcode — arm wired 2026-10-26)"
    else
      echo "mcode lane not answered (credential empty or provider refusal): $(tail -c 160 ${MC_LOG:-/tmp/mcode-lane.log} 2>/dev/null | tr '\n' ' ')"
      echo "TURN_RESULT=BLOCKED (qoder-ds+codebuddy+groq+qoder+mcode lanes all failed — check the harness)"
    fi
    ;;
  visiting-engineer)
    # glm-5.3@codebuddy — PAID VISITING MEMBER (Owner
    # order 2026-10-22 ~16:08Z: burn the 250 expiring CodeBuddy
    # credits at 50/day until 2026-10-27). --model glm-5.3
    # verified against the codebuddy CLI's own --help (supported
    # ids include deepseek-v4.1-flash, glm-5.3, glm-5.3-flash,
    # kimi-k3, gpt-6-astra, gpt-5.6-*). One visiting turn per
    # day, NOT in the standing rotation — the Lead points #+TURN
    # here for the daily burn; the advance rejoins the rotation
    # at software-engineer. If the paid lane fails, the segment
    # still runs on the proven free lanes but the result SAYS
    # the burn did not happen — a visit is never faked.
    # Honest-verdict guard: a network-marker exit-0 is a DEAD lane
    # (www.codebuddy.ai ETIMEDOUT evidence, run 39834624187).
    CB_LOG=/tmp/cb-lane.log
    CB_RC=0
    env CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1 \
         codebuddy -p "$BRIEF" -y --permission-mode bypassPermissions \
         --max-turns 100 --model glm-5.3 >"$CB_LOG" 2>&1 || CB_RC=$?
    CB_BAD=0
    grep -qE 'ETIMEDOUT|ECONNREFUSED|ENOTFOUND|EAI_AGAIN|网络请求超时|502 Bad Gateway' "$CB_LOG" 2>/dev/null && CB_BAD=1
    if [ "$CB_RC" = 0 ] && [ "$CB_BAD" = 0 ]; then
      tail -n 3 "$CB_LOG"
      echo "TURN_RESULT=codebuddy PAID run OK (lane: glm-5.3@codebuddy — visiting burn)"
    elif env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=PAID LANE FAILED — fell back to qoder (lane: qwen3.8-flash@qoder); visiting burn did NOT happen"
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=glm-4.7-flash \
         OPENAI_API_KEY="$ZAI_API_KEY" \
         OPENAI_HOST="https://api.z.ai" \
         OPENAI_BASE_PATH="/api/paas/v4/chat/completions" \
         goose run -t "$BRIEF"; then
      echo "TURN_RESULT=PAID LANE FAILED — fell back to zai (lane: zai/glm-4.7-flash@goose); visiting burn did NOT happen"
    else
      echo "TURN_RESULT=BLOCKED (visiting paid lane + free fallbacks all failed — check the harness)"
    fi
    ;;
  *)
    echo "TURN_RESULT=BLOCKED (unknown seat ${SEAT} — rotation case gap)"
    ;;
esac
fi
# SESSION COLLECT (Owner order 18:27Z): persist THIS turn's CLI
# session files — the container is --rm, they die here unless
# captured. Scrubbing happens on the host before upload.
SESS="/workspace/.turn-sessions.tgz"
rm -f "$SESS"
tar czf "$SESS" -C / \
  "${HOME#/}/.qoder" \
  "${HOME#/}/.config/goose/sessions" \
  "${HOME#/}/.local/share/goose/sessions" \
  "${HOME#/}/.local/share/opencode" \
  "${HOME#/}/.codebuddy/projects" \
  "${HOME#/}/.codebuddy/sessions" \
  "usr/local/lib/qoder-home/.qoder" \
  2>/dev/null || true
[ -s "$SESS" ] || echo "sessions: nothing collected this turn" >&2
INNER

# SEAT/BRIEF are shell assignments, NOT exported env vars —
# `docker run -e NAME` (bare) reads the CLI process env and passed
# EMPTY strings into the container (smoke test 14:18: SEAT=[]), so
# the inner case matched nothing and exited silently. Pass values
# explicitly instead.
mkdir -p "$PWD/.sessions-restore"
# EARLY VERDICT TRANSPORT (Lead 10-cl; evidence run 40181228238): the
# review is the FIRST phase inside the container and the verdict outputs
# were only written at script END — when the author segment overran the
# 45-min step budget, the host script was killed at this docker-run line
# and a DELIVERED verdict (transcript artifact review-transcript-451:
# full REJECTED, 46 turns) fell back to review-missing; the register
# re-polled a verdict the chain already had. Emit the pending identity
# + review duty up front, and emit the verdict the moment it settles in
# .turn-review.txt (same token across 2 consecutive polls — the review
# writes the file once and never rewrites, so a mid-transcript quoted
# format line would move on and fail the stability check) so a step
# kill can no longer lose a delivered verdict. The end-of-script parse
# below re-emits identical values (same grep, same keys — last write
# wins; settled-case semantics unchanged).
echo "pending_branch=${PENDING_BRANCH}" >> "$GITHUB_OUTPUT"
echo "pending_author=${PENDING_AUTHOR}" >> "$GITHUB_OUTPUT"
echo "pending_sha=${PENDING_SHA}" >> "$GITHUB_OUTPUT"
echo "review_seat=${REVIEWER_SEAT:-}" >> "$GITHUB_OUTPUT"
echo "review_member=${REVIEWER_MEMBER:-}" >> "$GITHUB_OUTPUT"
docker run --rm --user 1001:1001 \
  -v "$PWD":/workspace -w /workspace \
  -v "$PWD/.sessions-restore":/sessions-restore:ro \
  -e SEAT="${SEAT}" -e BRIEF="${BRIEF}" \
  -e WORK_ITEM="${WORK_ITEM:-}" -e CLOCK_TOKEN="${CLOCK_TOKEN:-}" \
  -e REVIEW_BRIEF="${REVIEW_BRIEF}" \
  -e PENDING_BRANCH="${PENDING_BRANCH}" -e PENDING_AUTHOR="${PENDING_AUTHOR}" \
  -e REVIEWER_SEAT="${REVIEWER_SEAT}" -e REVIEWER_MEMBER="${REVIEWER_MEMBER}" \
  -e QODER_PERSONAL_ACCESS_TOKEN -e ZAI_API_KEY -e OPENROUTER_API_KEY \
  -e GROQ_API_KEY -e CODEBUDDY_AUTH_TOKEN -e MCODE_AUTH_JSON \
  agent-harness:local bash /workspace/.turn-inside.sh \
  > /tmp/.turn-out.txt 2>&1 &
DOCKER_PID=$!
PREV_TOKEN=""
for _ in $(seq 1 190); do
  kill -0 "$DOCKER_PID" 2>/dev/null || break
  TOK=$(grep -hoE 'VERDICT:[[:space:]]*(APPROVED|REJECTED)' "$PWD/.turn-review.txt" 2>/dev/null | tail -1 | sed 's/.*VERDICT:[[:space:]]*//' | awk '{print $1}')
  if [ -n "$TOK" ] && [ "$TOK" = "$PREV_TOKEN" ]; then
    echo "review_verdict=${TOK}" >> "$GITHUB_OUTPUT"
    grep -hE 'VERDICT:' "$PWD/.turn-review.txt" 2>/dev/null | tail -1 | tr -d '\r\n"%' | cut -c1-200 | sed 's/^/review_evid=/' >> "$GITHUB_OUTPUT" || true
    echo "early verdict transport: ${TOK} emitted while the container is still running"
    break
  fi
  PREV_TOKEN="$TOK"
  sleep 15
done
if wait "$DOCKER_PID"; then
  echo "container verdict captured"
else
  echo "docker run failed — see output below for the cause"
  tail -30 /tmp/.turn-out.txt || true
  echo "TURN_RESULT=BLOCKED (docker run failed — see log)" > "$PWD/.turn-result.txt"
fi
sed -n '/TURN_RESULT=/p' /tmp/.turn-out.txt > /tmp/.turn-result.tmp || true
if [ -s /tmp/.turn-result.tmp ]; then
  cp /tmp/.turn-result.tmp "$PWD/.turn-result.txt"
fi
[ -s "$PWD/.turn-result.txt" ] || echo "TURN_RESULT=BLOCKED (container wrote no verdict — see log)" > "$PWD/.turn-result.txt"
cat "$PWD/.turn-result.txt" >> "$GITHUB_ENV"
echo "---- container output (up to 80 lines) ----"
sed -n '1,80p' /tmp/.turn-out.txt || true

TURN_RESULT=$(sed 's/^TURN_RESULT=//' "$PWD/.turn-result.txt" | tail -1)
# SEGREGATION LAW bookkeeping outputs: what this run reviewed and
# what it decided (the merger in finalize acts on these).
REVIEW_VERDICT=$(grep -hoE 'VERDICT:[[:space:]]*(APPROVED|REJECTED)' "$PWD/.turn-review.txt" 2>/dev/null | tail -1 | sed 's/.*VERDICT:[[:space:]]*//' | awk '{print $1}')
REVIEW_EVID=$(grep -hE 'VERDICT:' "$PWD/.turn-review.txt" 2>/dev/null | tail -1 | tr -d '\r\n"%' | cut -c1-200)
# HONEST REVIEW-LANE GUARD (Lead cycle 10-l; evidence: run 40073828746
# turn job 120814481260 — the duty review RAN (74 turns, 1042s) but the
# reviewer brain was substituted provider-side ("Model ... is not
# available right now; using ... instead"), the report ended in prose
# with no VERDICT: token, and the harness recorded a healthy run +
# review-missing. The author lanes grep a CB_BAD network marker (the
# blocks at the two docker-run sites); the review lane had no
# equivalent. Substitution marker + no verdict token = lane-dead:
# surfaced honestly so finalize labels the record and the stall law
# can see the failure instead of polling review-missing noise.
REVIEW_LANE_DEAD=0
if [ -z "$REVIEW_VERDICT" ] && [ -n "$PENDING_BRANCH" ] \
   && grep -q 'is not available right now; using' "$PWD/.turn-review.txt" 2>/dev/null; then
  REVIEW_LANE_DEAD=1
  echo "REVIEW LANE DEAD-MARKER: reviewer model substituted and no VERDICT token — recording lane-dead, not review-missing (job 120814481260 evidence)."
fi
# REVIEW-BRAIN PROVENANCE (Lead cycles 10-az / 10-bc / 10-bf / 10-bh / 10-bj —
# FIVE consecutive verdicts judged by a substituted brain while `lane_dead=0`
# made the record read as the duty reviewer's own work). The guard above only
# consults the substitution marker when NO verdict parsed, so a substituted
# reviewer that still prints `VERDICT:` is trusted with no trace of it in
# REVIEW-LOG, and every triage since has had to open the transcript artifact by
# hand to learn which brain judged. The stamp below is unconditional: it records
# provenance WITHOUT changing any outcome (a produced verdict stays a verdict —
# the Lead's ruling), so the audit trail names the brain that actually judged.
REVIEW_SUBSTITUTED=0
REVIEW_SUB_BRAIN=""
if [ -n "$PENDING_BRANCH" ] \
   && grep -q 'is not available right now; using' "$PWD/.turn-review.txt" 2>/dev/null; then
  REVIEW_SUBSTITUTED=1
  REVIEW_SUB_BRAIN=$(sed -n 's/.*is not available right now; using \([^ ]*\) instead.*/\1/p' \
                     "$PWD/.turn-review.txt" 2>/dev/null | head -1 | tr -cd 'A-Za-z0-9._:@-' | cut -c1-60)
fi
echo "review verdict for ${PENDING_BRANCH:-none}: ${REVIEW_VERDICT:-none} lane_dead=${REVIEW_LANE_DEAD} substituted=${REVIEW_SUBSTITUTED}${REVIEW_SUB_BRAIN:+ (brain: ${REVIEW_SUB_BRAIN})}"
echo "pending_branch=${PENDING_BRANCH}" >> "$GITHUB_OUTPUT"
echo "pending_author=${PENDING_AUTHOR}" >> "$GITHUB_OUTPUT"
echo "pending_sha=${PENDING_SHA}" >> "$GITHUB_OUTPUT"
echo "review_verdict=${REVIEW_VERDICT}" >> "$GITHUB_OUTPUT"
echo "review_evid=${REVIEW_EVID}" >> "$GITHUB_OUTPUT"
echo "review_seat=${REVIEWER_SEAT}" >> "$GITHUB_OUTPUT"
echo "review_member=${REVIEWER_MEMBER}" >> "$GITHUB_OUTPUT"
echo "review_lane_dead=${REVIEW_LANE_DEAD}" >> "$GITHUB_OUTPUT"
echo "review_substituted=${REVIEW_SUBSTITUTED}" >> "$GITHUB_OUTPUT"
echo "review_sub_brain=${REVIEW_SUB_BRAIN}" >> "$GITHUB_OUTPUT"
# HOST-SIDE COMMIT (run 39488529938: the seat EDITED + VERIFIED but
# its sandbox denied git/pytest — the edits died in the container,
# branch pushed empty, work lost). The host commits the workspace
# diff so a segment's work ALWAYS reaches the branch.
if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A
  git commit -m "turn(${SEAT}): segment work — host-committed" \
    -m "result: ${TURN_RESULT}" || echo "::notice::workspace commit failed"
else
  echo "workspace clean — no host commit needed"
fi
echo "result=${TURN_RESULT}" >> "$GITHUB_OUTPUT"
echo "## Turn — ${SEAT} @ ${GITHUB_SHA::7}" >> "$SUMMARY"
echo "" >> "$SUMMARY"
echo "objective: ${OBJECTIVE}" >> "$SUMMARY"
echo "branch: ${BRANCH}" >> "$SUMMARY"
echo "result: ${TURN_RESULT}" >> "$SUMMARY"
echo "TURN_SEAT=$SEAT" >> "$GITHUB_ENV"
rm -f "$PWD/.turn-inside.sh" "$PWD/.turn-result.txt" /tmp/.turn-out.txt /tmp/.turn-result.tmp
