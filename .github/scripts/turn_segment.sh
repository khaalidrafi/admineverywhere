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
# ----------------------------------------------------------------
# SEGREGATION LAW v2 — DUTY ROLES (Owner 18:14Z "Separate author,
# reviewer and merger roles" + 18:55Z refinement: "author, reviewer,
# merger duties should be performed by capable member roles with
# capabilities") — three distinct CAPABLE ROLES per delivery:
# AUTHOR = the implementation seats in rotation (platform -> relief
#   -> software); QA is OUT of the author rotation.
# REVIEWER = the QA ENGINEER (deepseek-v4.1-flash@qoder — the
#   audit-proven reviewer role, FR-R001-FE), ALWAYS, not "whoever is
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
# DUTY-REVIEWER selection (determined BEFORE the brief is built):
QA_MEMBER="deepseek-v4.1-flash@qoder"
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
3. Landing gate: python -m pytest plugin/tests -p no:cacheprovider -q ; app vitest run ; demo-backend/manage.py check ; demo-backend/manage.py makemigrations --check — report each rc.
4. Law check: no secrets in the diff (SECRET LAW); no Lead-owned files edited (.github/workflows/*, agent-team/TEAM-CONTROL.org, .github/scripts/*, .gitattributes); the board flip carries :DELIVERED: evidence with branch + sha; TEAM-CHAT entries legal format.
5. Do NOT modify or commit anything — your verdict text is your whole deliverable.
6. The LAST line of your answer MUST be exactly one of:
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
# REVIEW PHASE (SEGREGATION LAW v2, Owner 18:14Z + 18:55Z): the
# DUTY REVIEWER is a capable member ROLE, not the turn seat — the
# host already selected REVIEWER_SEAT/REVIEWER_MEMBER and passed
# them in via docker -e. A SEPARATE lane call from the author
# segment below. Read-only: the verdict token lands in
# /workspace/.turn-review.txt and the HOST extracts it; the merger
# (finalize, on LEAD authority) acts only on APPROVED from the
# duty reviewer, who is never the author.
: > /workspace/.turn-review.txt 2>/dev/null || true
if [ -n "$PENDING_BRANCH" ]; then
  # DUTY-REVIEWER lanes (Owner 18:55Z: the review duty belongs to a
  # capable member ROLE, not to whoever happens to hold the turn):
  #   default  -> QA ENGINEER lane (deepseek-v4.1-flash@qoder via the
  #               qoder body — the seat's PROVEN recipe, --model pinned)
  #   QA authored -> VISITING SENIOR lane (glm-5.3@codebuddy)
  # The turn seat NEVER reviews its own or anyone's work here.
  case "$REVIEWER_SEAT" in
    quality-assurance-engineer)
      env HOME=/usr/local/lib/qoder-home \
        qoder -p "$REVIEW_BRIEF" --output-format json --model deepseek-v4.1-flash \
        --permission-mode bypassPermissions --max-turns 60 \
        > /workspace/.turn-review.txt 2>&1 || true ;;
    visiting-engineer)
      env CODEBUDDY_AUTH_TOKEN="$CODEBUDDY_AUTH_TOKEN" CODEBUDDY_IS_SANDBOX=1 \
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
         goose run --no-session -t "$BRIEF"; then
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
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: laguna-s-2.1:free@goose — relief swap 2026-10-23)"
    # Lead lane add 2026-10-22: qwen3.8-27b@groq — GROQ_API_KEY is
    # in repo secrets (probed every run); gives the chain a 4th,
    # independent brain when qoder quota + zai rate-limit die.
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \
         OPENAI_API_KEY="$GROQ_API_KEY" \
         OPENAI_HOST="https://api.groq.com" \
         OPENAI_BASE_PATH="/openai/v1/chat/completions" \
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: qwen3.8-27b@groq — relief hire 2026-10-22)"
    else
      echo "TURN_RESULT=BLOCKED (qoder+zai+minimax+groq lanes all failed — check the harness)"
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
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: zai/glm-4.7-flash@goose)"
    # Relief swap 2026-10-23 (DE TEAM-UPDATE #2): minimax :free delisted
    # at source — poolside/laguna-s-2.1:free takes the slot.
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=poolside/laguna-s-2.1:free \
         OPENAI_API_KEY="$OPENROUTER_API_KEY" \
         OPENAI_HOST="https://openrouter.ai" \
         OPENAI_BASE_PATH="/api/v1/chat/completions" \
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: laguna-s-2.1:free@goose — relief swap 2026-10-23)"
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \
         OPENAI_API_KEY="$GROQ_API_KEY" \
         OPENAI_HOST="https://api.groq.com" \
         OPENAI_BASE_PATH="/openai/v1/chat/completions" \
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: qwen3.8-27b@groq)"
    elif env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=qoder run OK (lane: qwen3.8-flash@qoder)"
    else
      echo "TURN_RESULT=BLOCKED (zai+minimax+groq+qoder lanes all failed — check the harness)"
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
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=glm-4.7-flash \
         OPENAI_API_KEY="$ZAI_API_KEY" \
         OPENAI_HOST="https://api.z.ai" \
         OPENAI_BASE_PATH="/api/paas/v4/chat/completions" \
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: zai/glm-4.7-flash@goose)"
    # Relief swap 2026-10-23 (DE TEAM-UPDATE #2): minimax :free delisted
    # at source — poolside/laguna-s-2.1:free takes the slot.
    elif env GOOSE_PROVIDER=openai GOOSE_MODEL=poolside/laguna-s-2.1:free \
         OPENAI_API_KEY="$OPENROUTER_API_KEY" \
         OPENAI_HOST="https://openrouter.ai" \
         OPENAI_BASE_PATH="/api/v1/chat/completions" \
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: openrouter/laguna-s-2.1:free@goose)"
    else
      echo "TURN_RESULT=BLOCKED (codebuddy+qoder-ds+zai+laguna lanes all failed — check the harness)"
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
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=goose run OK (lane: groq/qwen3.8-27b@goose)"
    elif env HOME=/usr/local/lib/qoder-home \
         qoder -p "$BRIEF" --output-format json \
         --permission-mode bypassPermissions --max-turns 100; then
      echo "TURN_RESULT=qoder run OK (lane: qwen3.8-flash@qoder — default brain)"
    else
      echo "TURN_RESULT=BLOCKED (qoder-ds+codebuddy+groq+qoder lanes all failed — check the harness)"
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
         goose run --no-session -t "$BRIEF"; then
      echo "TURN_RESULT=PAID LANE FAILED — fell back to zai (lane: zai/glm-4.7-flash@goose); visiting burn did NOT happen"
    else
      echo "TURN_RESULT=BLOCKED (visiting paid lane + free fallbacks all failed — check the harness)"
    fi
    ;;
  *)
    echo "TURN_RESULT=BLOCKED (unknown seat ${SEAT} — rotation case gap)"
    ;;
esac
# SESSION COLLECT (Owner order 18:27Z): persist THIS turn's CLI
# session files — the container is --rm, they die here unless
# captured. Scrubbing happens on the host before upload.
SESS="/workspace/.turn-sessions.tgz"
rm -f "$SESS"
tar czf "$SESS" -C / \
  "${HOME#/}/.qoder" \
  "${HOME#/}/.config/goose/sessions" \
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
if docker run --rm --user 1001:1001 \
  -v "$PWD":/workspace -w /workspace \
  -v "$PWD/.sessions-restore":/sessions-restore:ro \
  -e SEAT="${SEAT}" -e BRIEF="${BRIEF}" \
  -e REVIEW_BRIEF="${REVIEW_BRIEF}" \
  -e PENDING_BRANCH="${PENDING_BRANCH}" -e PENDING_AUTHOR="${PENDING_AUTHOR}" \
  -e REVIEWER_SEAT="${REVIEWER_SEAT}" -e REVIEWER_MEMBER="${REVIEWER_MEMBER}" \
  -e QODER_PERSONAL_ACCESS_TOKEN -e ZAI_API_KEY -e OPENROUTER_API_KEY \
  -e GROQ_API_KEY -e CODEBUDDY_AUTH_TOKEN \
  agent-harness:local bash /workspace/.turn-inside.sh \
  > /tmp/.turn-out.txt 2>&1; then
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
echo "review verdict for ${PENDING_BRANCH:-none}: ${REVIEW_VERDICT:-none}"
echo "pending_branch=${PENDING_BRANCH}" >> "$GITHUB_OUTPUT"
echo "pending_author=${PENDING_AUTHOR}" >> "$GITHUB_OUTPUT"
echo "pending_sha=${PENDING_SHA}" >> "$GITHUB_OUTPUT"
echo "review_verdict=${REVIEW_VERDICT}" >> "$GITHUB_OUTPUT"
echo "review_evid=${REVIEW_EVID}" >> "$GITHUB_OUTPUT"
echo "review_seat=${REVIEWER_SEAT}" >> "$GITHUB_OUTPUT"
echo "review_member=${REVIEWER_MEMBER}" >> "$GITHUB_OUTPUT"
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
