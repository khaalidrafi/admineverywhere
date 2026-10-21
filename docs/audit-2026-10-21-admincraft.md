# Independent Secret-Leak Audit v2 — khaalidrafi/admincraft (verification of SECURITY-AUDIT.org)

- Task ID: 16-a (independent seat; LOCAL-ONLY, read-only audit — no writes inside the repo)
- Date: 2026-10-21 · Auditor: independent security-auditor seat (not the Lead that wrote v1)
- Target: /home/z/my-project/admincraft @ ai/lead-ops (ac90502) = origin/ai/main
- Redaction law: every value shown as first-4-chars + `…` + `(len=N)`. No full value appears in this report.

---

## 1. Verdict on prior SECURITY-AUDIT.org (published 3a9ea44, 2026-10-21T04:20Z)

**Substantive verdict: CONFIRMED.** No live secrets anywhere in the working tree or the
entire history of all branches/tags. Every pattern hit is a test fixture or documentation
echo. `app/src/lib/__tests__/api.test.ts` password/token literals are verifiably MOCK
fixtures: line 14 sits inside a `mockFetch.mockResolvedValueOnce(...)` 400-response body
whose only purpose is to exercise the ApiError redaction path, and line 23 asserts the
expected REDACTED output (`****… (len=8)`). `plugin/tests/test_branding_api.py:139` is an
explicit placeholder (`not-… (len=16)`) in an auth-rejection test. No rotation required.

**Three bookkeeping corrections (do not change the verdict):**

| # | Prior claim | Measured reality |
|---|---|---|
| 1 | "253 commits, every commit reachable from all refs" | 253 = `ai/lead-ops` tip only. ALL refs (5 branches + 3 annotated tags) = **256 commits**. 3 commits are remote-only and were NOT in a lead-ops-only view: c857c44 (origin/ai/turn-20261021-0011), 1026b12 (origin/ai/fr-r004), 49e67fa (origin/ai/cool-chat-verify2). |
| 2 | "672 unique blobs" | Not exactly reproducible at any checkpoint: 659 blobs at audit commit 3a9ea44, 661 at current tip, **678 across all refs now** (includes the 3 remote-only commits). Off by ≤ 19; no finding hides in the delta (all 678 scanned). |
| 3 | "fixture first introduced c857c445" | **Wrong attribution.** c857c44 (a turn-segment commit) never touched api.test.ts. The fixture blob was introduced by **ec7de09** (2026-10-17, mainline "test: add missing test files") and independently by **484f9e4** (2026-10-20, same blob on a parallel branch); latest version via 4508f6a (2026-10-20). |

Prior-audit reconciliation: its "6 findings" ≈ the 6 historical fixture blobs (3 ×
api.test.ts + 3 × test_branding_api.py) and "2 worktree hits" = the 2 api.test.ts lines;
my count additionally includes SECURITY-AUDIT.org quoting itself and gives 4 worktree hit
lines / 10 historical hit lines across 7 blobs — same substance.

## 2. Scan scope

| Dimension | Count |
|---|---|
| Commits (all refs: ai/lead-ops, ai/main, origin/ai/main, origin/ai/cool-chat-verify2, origin/ai/fr-r004, origin/ai/turn-20261021-0011, tags v0.1.0–v0.1.2) | 256 |
| Unique blobs scanned (blob-level, every ref) | 678 |
| Working tree | clean — 0 untracked, 0 modified; `frontend-dist/` tracked and scanned |
| Commit + annotated-tag messages scanned | all (0 hits) |
| Unreachable/dangling objects (`git fsck`) | 0 (no amended-away remnants) |
| Worktree hit lines | 4 |
| History hit lines (blob-level) | 10 across 7 blobs (3 files) |
| High-entropy heuristic pass (28+ char values on key-like names, JWT `eyJ…eyJ…`, `x-access-token:`, Qoder `pt-`, zapier) | 0 hits |
| **By class** | **CONFIRMED 0 · LIKELY 0 · FALSE-POSITIVE 4 distinct (plus 1 documented accepted-risk)** |

Method: (a) blob-level enumeration of all 678 unique blobs across `--all`, each streamed
through the full pattern set (binary-safe); (b) cross-check via `git log --all -p -U0`
(2.1 MB stream) — both passes agree; (c) worktree `rg` pass (tracked + untracked);
(d) filename census of every path ever added (261 unique paths).

## 3. Findings table (all FALSE-POSITIVE / accepted-risk)

| Class | Type | Location (file:line) | Introduced by (commit, date) | Redacted preview | Live in HEAD |
|---|---|---|---|---|---|
| FALSE-POSITIVE | mock password literal in mocked 400 fetch response | app/src/lib/__tests__/api.test.ts:14 | ec7de09 2026-10-17 (dup 484f9e4; latest 4508f6a; blob 98e56efa) | `passw…: "secr… (len=9)"` alongside `"x… (len=3)"` | yes — deliberate, tests redaction |
| FALSE-POSITIVE | expected REDACTED output asserted by test | app/src/lib/__tests__/api.test.ts:23 | ec7de09 2026-10-17 | `"****… (len=8)"` | yes |
| FALSE-POSITIVE | placeholder token in auth-rejection test | plugin/tests/test_branding_api.py:139 (historical :133 @ cc10b21b) | 07b7454 2026-10-17 (blob 307234b3 via 953d725) | `token="not-… (len=16)"` | yes |
| FALSE-POSITIVE | audit doc quoting its own finding | SECURITY-AUDIT.org:16 | 3a9ea44 2026-10-21 (blob 4818ab98) | `secr… (len=9)` | yes |
| ACCEPTED-RISK (not a leak) | committed Android **debug** signing keystore | app/src-tauri/signing/debug.keystore (binary, 2666 B) | c6f4e78 2026-10-17 | PKCS12 alias `androiddebugkey`, store/key password `andr… (len=7)` — the universal public Android debug default | yes — intentional, documented in app/src-tauri/signing/README.md: sideload-only debug builds, signature stability on ephemeral CI runners; explicitly NOT a Play Store upload key |

Zero hits for: GitHub PATs (`github_pat_`, `ghp/gho/ghu/ghs/ghr_`), AI keys (sk-ant-,
sk-or-v1-, sk-proj-, gsk_, generic sk-32+), Telegram bot token shape, AWS AKIA, Google
AIza, Slack xox-, Discord/Lark/Feishu/Slack webhook hosts, private-key headers, Bearer
tokens, JWT shapes, Qoder pt-, x-access-token URLs, and all high-entropy heuristic forms.
Workflows contain only `${{ secrets.* }}` interpolation (names, never values); commit and
tag messages clean; no `.env*`/`.pem`/`.key`/`id_rsa*`/`.netrc`/`.npmrc`/`.pfx` file was
EVER added in the entire history (census of 261 paths).

## 4. Rotation list

**NONE.** No CONFIRMED (and no LIKELY) credential exists in any ref, blob, message, or the
worktree. Nothing to revoke or rotate. The committed debug keystore is the documented
Android debug default (public password, self-signed, sideload-only) — rotation is not
required; the README already carries the rotation procedure if the project ever ships
Play Store releases (then: real upload key in repo secrets, never in git).

## 5. Hygiene recommendations

1. **.gitignore additions** (currently missing all of these):
   `.env`, `.env.*`, `*.pem`, `*.key`, `*.pfx`, `*.jks`, `*.keystore` (with an explicit
   exception `!app/src-tauri/signing/debug.keystore` so the intentional file stays
   tracked), `.netrc`, `.npmrc`, `id_rsa*`, `id_ed25519*`, `.cb-auth-token.json`,
   `.cb-auth-state.json`, `.relay-values.json`, `.gh-pat`, `.askpass*`, `*-session*.org`
   artifact dumps if any agent writes them inside the repo.
2. **secret-guard.sh coverage gaps** (its GENERIC regex covers only pt- / TG token /
   ghp_ / github_pat_ / sk-16+ / x-access-token):
   - add: `sk-ant-`, `sk-or-v1-`, `sk-proj-`, `gsk_…{20,}`, `AIza[0-9A-Za-z_-]{35}`,
     `AKIA[0-9A-Z]{16}`, `xox[baprs]-`, webhook URL hosts (discord.com/api/webhooks,
     hooks.slack.com, open.feishu.cn, hooks.larksuite.com), `Bearer <20+>`,
     `eyJ…eyJ…` JWT shape, `BEGIN …PRIVATE KEY`;
   - word-bound the generic `sk-` alternative to cut mid-word false matches;
   - add a HARD-FAIL mode for confirmed shapes (today it redacts and never fails the run —
     safe-by-default, but a real credential would only be silently redacted, never raised);
   - `SECRET_GUARD_VALUES` misses `DISCORD_WEBHOOK_*`-style var prefixes — extend the
     collect_values regex.
3. **CI backstop:** the guard only sees staged/branch diffs. Add a scheduled full-history
   scanner (e.g. gitleaks/trufflehog against `--all`) as a second layer; this audit's
   blob-level method can serve as the offline equivalent.
4. **Attribution hygiene:** record scan checkpoint refs+counts in future audits (the
   v1 "253/672/c857c445" triple was irreproducible from any single ref — harmless here,
   but it made independent verification slower).
