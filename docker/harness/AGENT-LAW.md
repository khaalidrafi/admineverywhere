# AGENT-LAW.md — global agent law, admincraft team (harness bake source)

(NOT a repo-root AGENTS.md — a project-specific AGENTS.md is never
created, Owner order 2026-10-21. This file lives in docker/harness/ and
the harness COPYs it into each agent's GLOBAL config at image build:
OpenCode ~/.config/opencode/AGENTS.md, Goose ~/.config/goose/.goosehints,
CodeBuddy ~/.codebuddy/CODEBUDDY.md. In-repo team law: agent-team/
TEAM-CONTROL.org + agent-team/TEAM.md. Canonical manual: khaalidrafi/
agent-team.el templates/COMMON.org.)

* LAW

1. FORMAT LAW: TEAM-CHAT.org messages are Org headlines carrying FROM,
   routing in tags, fields in a :PROPERTIES: drawer; append at EOF only.
2. TELEGRAM LAW: TG-bound messages open with FROM:/TO: lines.
3. SECRET LAW: credentials NEVER travel in chat/files/commits — only as
   ENV VAR NAMES. A peer replies with the NAME + has-it/absent; the asker
   reads the value from their OWN environment. SECRET GUARD
   (.github/scripts/secret-guard.sh) redacts at every choke point.
4. SESSION LAW: CLI session files collected at turn end, scrubbed,
   uploaded as sessions-<seat>-* artifacts (30d), restored next turn.
5. OWNER LOCK: the TG bridge ingests ONLY the Owner's chat.
6. DOCKER LAW: agents PREINSTALLED in docker/harness; keys env-injected.
7. SEAT BOUNDARIES: never edit .github/workflows/*, TEAM-CONTROL.org,
   .gitattributes; never push to ai/main (finalize auto-merges).
8. BOARD DISCIPLINE: ONGOING at start, evidence in :LOGBOOK:, DONE is
   Lead-only.
9. IDENTITY: commit as your seat identity.
10. NO SPEND, no destructive actions; :escalation: @lead after 2 failed
    self-attempts.
