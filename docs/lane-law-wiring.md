# Lane law-wiring audit (DOE TEAM-UPDATE #5, Owner 2026-10-27 04:14Z #hq)

Question asked: do the two `AGENTS.md` laws — the **global** one
(`khaalidrafi/vault` canonical, CI copy `agent-team/AGENTS-GLOBAL.md`) and the
**local** repo-root `AGENTS.md` — actually reach every CI lane harness?

Method: never assume a convention. Each claim below is either (a) a literal read
out of the tool's own installed bundle or its shipped docs, or (b) a probe run in
this harness container. Probes are **zero-spend**: the CLI is started with its
credential env var *unset*, so the provider request is refused while the
start-up memory discovery still runs and writes its debug log.

## The matrix

| lane harness (invocation from `.github/scripts/turn_segment.sh`) | local law | global law | mechanism it honors | evidence |
| --- | --- | --- | --- | --- |
| `qoder -p "$BRIEF"` (turn seat, lane `qwen3.8-flash@qoder`; also `-p deepseek-v4.1-flash` review arm) | YES | **YES — wired this turn** | project `AGENTS.md` upward to the git root, plus `@`-imports inside it; user-level `$HOME/.qoder/AGENTS.md` | probe log `MemoryDiscovery … Successfully read and processed imports: /workspace/AGENTS.md (Length: 84738)` before, `(Length: 93373)` after, plus `deduplication: keeping /workspace/agent-team/AGENTS-GLOBAL.md`; bundle literals `discoverMemoryPaths()`, `getGlobalQoderMdFilePath()`, `external @import(s) blocked in AGENTS.md` (only OUT-of-project imports are gated) |
| `goose run -t "$BRIEF"` (lanes zai/glm-4.7-flash, groq qwen3.8-27b, poolside/laguna) | YES (measured 22895→~28k tokens/request — see `scripts/lane_budget_check.py`) | NO | whole project `AGENTS.md`; **no `@import` mechanism** | one `AGENTS.md` literal in `/usr/local/bin/goose`; the only instruction-ish env names in the binary are `GOOSE_SYSTEM_PROMPT_FILE_PATH`, `GOOSE_CONTEXT_LIMIT`, `GOOSE_ADDITIONAL_CONFIG_FILES` (config, not law); `@import` hits are unrelated prose |
| `codebuddy -p "$BRIEF"` / `codebuddy --acp` (visiting senior lane) | YES | **YES — wired this turn** | `CODEBUDDY.md` **or** `AGENTS.md` as project memory (AGENTS.md only when no `CODEBUDDY.md` exists — true here), plus `~/.codebuddy/CODEBUDDY.md`, `./.codebuddy/rules/*.md`, `CODEBUDDY.local.md`, and `@`-imports inside the memory file | shipped docs `dist/web-ui/docs/en%2Fcli%2Fmemory.md` (table of the four memory locations + the fallback rule); bundle `codebuddy.js`: `eI="AGENTS.md"`, `eB="AGENTS.mdc"`, `resolveMemoryFileNames()`, `ImportUtils.extractImports` regex `(?<!\S)@([^\s@\n]+)` with `MAX_IMPORT_DEPTH`=5 |
| `mcode exec --permission full …` (arm CANCELLED by Owner 2026-10-26 04:57Z — out of project scope) | would be YES | unknown | memory-file set `["AGENTS.md","AGENTS.MD","CLAUDE.md","CLAUDE.MD"]` in `chunks/chunk-IQUH3X7I.js`; user-level config dirs probed at `$MINIMAX_DATA_DIR` and `~/.minimax` | bundle read only; the arm never completes a request (sealed credential refused, `TODOS.org:3886` CANCELLED row), so no probe is available |
| raw-curl duty-review lane (`.github/workflows/agent-review.yml:194-206`, `POST https://api.groq.com/openai/v1/chat/completions`, `qwen/qwen3.8-27b`) | NO | NO | **none** — the payload is one inline `system` message built in the workflow; no file mechanism exists | workflow body read: `payload = {"model": …, "messages": [{"role": "system", "content": sysmsg}, …]}`; `sysmsg` carries only the review brief |
| raw-curl liveness probes (`.github/workflows/agent-team.yml:130-150`) | n/a | n/a | single word `alive`, `max_tokens: 16` | **out of domain by design** — a probe answers transport, not law; wiring anything into it would change what it measures |

## What the Owner's three evidence claims measured

- "`AGENTS-GLOBAL.md` feeds no tool" — **true before this turn**, and the reason
  is arithmetic, not a missing file: the copy is committed and byte-correct
  (`sha256 335c85ee1d084cb6…` = the vault canonical prefix the order names), but
  nothing referenced it. It is now referenced by the one file every
  import-honoring lane already loads.
- "no `CODEBUDDY.md`" — **true and correctly NOT a defect**: the tool's own rule
  is "if `CODEBUDDY.md` exists it wins, otherwise `AGENTS.md`". Committing a
  `CODEBUDDY.md` here would *replace* the repo law's provenance, not add to it.
  The standing law "do not invent a repo-root law file" is respected — the local
  law already exists and is the one imported.
- "qoder mechanism unverified" — **verified now**, twice, from the CLI's own
  debug log (the before/after pair in the table).
- "raw-curl lanes lawless" — **confirmed still lawless**, and it is not a seat
  fix: `.github/workflows/*` is Lead-owned (SEAT BOUNDARIES), so the repair is
  listed below for the Lead rather than committed by this seat.

## Remaining wiring, by owner

Lead-owned (`.github/scripts/turn_segment.sh`, `.github/workflows/agent-review.yml`):

1. **goose arms** — no file mechanism, so prepend a law block to `$BRIEF`. Use
   the **condensed** digest, not the full global file: the groq free tier is
   pinned at 7000 ITPM (`scripts/lane_budget_check.py`), and the goose lane
   already spends ~28k tokens carrying `AGENTS.md`, so the full stack can never
   fit there. `AGENTS.md` already ships that digest as its final section
   ("Global agent law — DISTRIBUTED", 10 numbered lines).
2. **raw-curl duty-review lane** — prepend the same 10-line digest to `sysmsg`,
   which is also the only lane where the token math is headroom-positive
   (`max_tokens: 900` out, ~8k in against the 7000 ITPM cap: `lane_budget_check`
   reports this lane RED today for a different reason — its provider-rejection
   leg — and that RED is pre-existing, not caused by this audit).
3. **A refusal for lawless lanes** — the order asks that "a lawless lane can
   never be trusted first". `scripts/lane_budget_check.py` is the harness that
   already ranks lanes by trust; a law-coverage leg belongs there. Coverage fact
   for whoever writes that leg: today the harness exits 1 at its
   provider-rejection leg and prints ONLY that finding — no budget table at all —
   so it cannot currently answer "does the qoder lane fit?" either. Fix the red
   first, or the new leg inherits a harness that shows nothing.
4. Optional hardening for the import-honoring lanes: write
   `$HOME/.qoder/AGENTS.md` from `agent-team/AGENTS-GLOBAL.md` in the runner
   setup, so a lane that runs outside a trusted folder (where qoder refuses
   project memory — `isTrustedFolder()` gates `discoverMemoryPaths`) still gets
   the global law.

Seat-owned (this file + `AGENTS.md`): the import line, the measurement, and the
matrix above.

## Re-running this audit

```bash
# qoder: which law files does it load, with zero provider request
timeout 90 env -u QODER_PERSONAL_ACCESS_TOKEN HOME=/usr/local/lib/qoder-home \
  qoder -d -p "ping" --no-session-persistence >/dev/null 2>&1
L=$(ls -t -d /usr/local/lib/qoder-home/.qoder/logs/runs/* | head -1)
grep -aE 'MemoryDiscovery' "$L/qodercli.log" | grep -aE 'keeping|imports'

# the byte identity of the CI global copy (must match the vault prefix)
sha256sum agent-team/AGENTS-GLOBAL.md | cut -c1-16

# goose: the whole law mechanism is one literal
tr -cd '\11\12\15\40-\176' < /usr/local/bin/goose \
  | grep -aoE '.{0,40}AGENTS\.md.{0,40}' | sort -u

# codebuddy: the fallback rule, in the tool's own words
sed -n '1,40p' /usr/local/lib/node_modules/@tencent-ai/codebuddy-code/dist/web-ui/docs/en%2Fcli%2Fmemory.md

# lane token/byte cost against provider budgets
python3 scripts/lane_budget_check.py
```
