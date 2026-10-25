# admincraft agent harness — CI turn container with agent bodies
# PREINSTALLED (Owner order 2026-10-20 #hq: agents go into the image,
# not into CI). Secrets are NEVER baked: keys are env-injected per run
# from repo secrets.
#
# REFRESHED by agent-team.el setup (Owner order 2026-10-21 10:12Z): the
# pkg's proven recipe merged in — OpenCode + Goose + CodeBuddy bodies
# (the goose fallback lanes were DEAD before: the old image baked only
# qoder), and the GLOBAL AGENTS.md CONFIG bakes verified per agent docs
# (OpenCode ~/.config/opencode/AGENTS.md, Goose ~/.config/goose/.goosehints,
# CodeBuddy ~/.codebuddy/CODEBUDDY.md; Qoder reads repo-root AGENTS.md).
# Project deps (Django/DRF/drf-spectacular/cors + pytest) stay baked so
# the landing gate runs offline-fast inside segments too.

FROM python:3.12-slim

RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      git curl ca-certificates bzip2 jq procps nodejs npm \
 && rm -rf /var/lib/apt/lists/*

# --- Python project deps (baked; the plugin itself is EDITABLE-INSTALLED
#     from the mounted workspace at segment start — it is the code under
#     test, not an agent body) -------------------------------------------
RUN pip install --no-cache-dir \
      "Django>=5.0,<6.0" \
      "djangorestframework>=3.15" \
      "drf-spectacular>=0.27" \
      "django-cors-headers>=4.3" \
      pytest

# --- OpenCode body (preinstalled once, reused every turn) -------------------
RUN export HOME=/usr/local/lib/opencode-home \
 && curl -fsSL https://opencode.ai/install | bash \
 && chmod -R a+rX /usr/local/lib/opencode-home \
 && ln -sf /usr/local/lib/opencode-home/.opencode/bin/opencode /usr/local/bin/opencode

# --- Goose body (direct tarball: the download_cli.sh installer opens
#     /dev/tty and dies on headless runners — demo/01 turn 2 evidence) ------
RUN mkdir -p /tmp/goose-dl \
 && curl -fsSL -o /tmp/goose-dl/goose.tar.bz2 \
      https://github.com/block/goose/releases/download/stable/goose-x86_64-unknown-linux-gnu.tar.bz2 \
 && tar -xjf /tmp/goose-dl/goose.tar.bz2 -C /tmp/goose-dl \
 && install -m 0755 /tmp/goose-dl/goose /usr/local/bin/goose \
 && rm -rf /tmp/goose-dl

# --- Qoder body (exact recipe proven in khaalidrafi/agent-team.el:
#     install under /usr/local/lib/qoder-home, a+rwX, symlink the ENTRY
#     dispatcher, and pin HOME=/usr/local/lib/qoder-home at RUNTIME —
#     the launcher resolves the real CLI under ITS HOME, so a plain
#     /home/agent HOME prints "Qoder CLI is not installed"; runs
#     39467719908 + 39477554903 evidence). Version check is FATAL. ----
RUN export HOME=/usr/local/lib/qoder-home \
 && curl -fsSL https://qoder.com/install | bash \
 && chmod -R a+rwX /usr/local/lib/qoder-home \
 && ln -sf /usr/local/lib/qoder-home/.qoder/entry/qoder /usr/local/bin/qoder \
 && timeout 60 env HOME=/usr/local/lib/qoder-home qoder --version

# --- CodeBuddy body (baked and DORMANT until a CodeBuddy account
#     credential exists; headless needs -y in -p mode for tool use) ----
RUN npm install -g @tencent-ai/codebuddy-code \
 && timeout 60 codebuddy --version

# --- Cline body (wave-3 QA-6/QA-7 lane; Owner hire order 2026-10-24
#     17:01Z "Hire built-in models from Opencode and cline"). Headless:
#     `cline "task" --json`; non-OAuth auth proven in sandbox 2026-10-22
#     (`cline auth -p cline -k $KEY -m <model>` -> providers.json).
#     DORMANT until CLINE_API_KEY (or DoE free-account creds) lands as a
#     repo secret — the probe step SKIPs cleanly without it.
#     10-ba BUILD LAW (run 40117823054 evidence): this bake built GREEN at
#     17:26 (run 40116083108 probes) and FAILED at 17:58 (run 40117823054,
#     npm install -g cline exit 1) — a flaky/driftering npm install of a
#     DORMANT body must never brick the image and kill the whole chain
#     (no image -> no turn, no review -> review-missing -> stall). One
#     retry, then the body degrades to ABSENT with a loud marker; the
#     proven bodies (qoder/codebuddy above) stay strict. ---------------
RUN (npm install -g cline \
  || (sleep 20 && npm install -g cline) \
  || echo "CLINE-BODY-ABSENT (npm install failed twice - dormant lane, chain continues)") \
 && (timeout 120 cline --version \
  || echo "CLINE-BODY-UNVERIFIED (installed but --version failed - probe will grade it)")

# --- MCode body (@minimax-ai/code — Owner carve-out 2026-10-24 17:11Z
#     "you can use m3.1 on Mcode for free!!!", lane RE-ARMED in ROSTER.org:69).
#     Lead 10-ay deferred this bake because the CLI refuses the image's system
#     Node and a base-Node upgrade would risk the five PROVEN bodies above.
#     Refusal measured IN this image, not assumed: the postinstall dies with
#     "[MCode] Unsupported Node.js environment. Detected: linux-x64, Node
#     20.19.2 (ABI 115) / Supported: Node 22.19+, 24, 25, 26" (rc 1, package
#     never lands). So the lane gets a PRIVATE Node 24 that no other body
#     sees — the system nodejs and its PATH entry are untouched, and the
#     wrapper below is the only thing that execs the private one.
#     Two facts shape the recipe: (a) the tarball is .tar.gz because this
#     image has NO xz binary (`tar -xJf` -> "tar (child): xz: Cannot exec"),
#     and (b) it is SHA256-pinned because nodejs.org serves no .asc for it
#     (measured 404) and there is no gpg here.
#     After install the non-linux half of the `computer-use` plugin payload
#     is deleted: that 228M directory holds only darwin-arm64/darwin-x64/
#     win32-arm64/win32-x64 — NO linux build, so it can never run here.
#     Verified without it: `mcode --version` -> 0.6.13, `mcode exec` and
#     Node's header dir (67M, build-time only) goes too. better-sqlite3's
#     native binding is fetched by ITS OWN install script (`prebuild-install`,
#     no compiler needed): measured functional under the private Node
#     (`new Database(':memory:')` + INSERT + SELECT) — and measured ABSENT when
#     the install is run with `--ignore-scripts` (build/Release never appears),
#     so this step must NOT gain that flag, however tempting CI hygiene looks.
#     Headless contract for the arm wiring (Lead-owned turn_segment.sh):
#     `mcode exec --permission full --output-format json -o <file> --cwd <ws>
#     "<prompt>"` (the `ask` policy needs a TUI, so CI must pick full/smart).
#     DORMANT until MCODE_AUTH_JSON lands as a repo secret: an unauthenticated
#     `mcode exec` refuses with "Sign in to MiniMax to use Agent features.
#     Run `mcode login`, then retry." and ZERO requests — a clean skip-guard.
#     Restore target for the sealed token: $MINIMAX_DATA_DIR/auth.json
#     (default ~/.minimax; `auth-state.json`/`auth.lock` sit beside it). ---------
RUN set -e \
 && mkdir -p /usr/local/lib/mcode-node \
 && curl -fsSL -o /tmp/node24.tar.gz \
      https://nodejs.org/dist/v24.22.1/node-v24.22.1-linux-x64.tar.gz \
 && echo "eb6728e77c576a35162c122c45ccadf224d89ff00abc8dae46cc2897c6002d7c  /tmp/node24.tar.gz" \
      | sha256sum -c - \
 && tar -xzf /tmp/node24.tar.gz -C /usr/local/lib/mcode-node --strip-components=1 \
 && rm -rf /usr/local/lib/mcode-node/include /tmp/node24.tar.gz \
 && timeout 60 /usr/local/lib/mcode-node/bin/node --version

RUN set -e \
 && export PATH=/usr/local/lib/mcode-node/bin:$PATH \
 && npm install --prefix /usr/local/lib/mcode @minimax-ai/code@0.6.13 \
      --no-audit --no-fund \
 && rm -rf /usr/local/lib/mcode/node_modules/@minimax-ai/code/embedded/computer-use \
 && chmod -R a+rX /usr/local/lib/mcode-node /usr/local/lib/mcode \
 && printf '#!/bin/sh\nexec /usr/local/lib/mcode-node/bin/node /usr/local/lib/mcode/node_modules/@minimax-ai/code/cli.js "$@"\n' \
      > /usr/local/bin/mcode \
 && chmod 0755 /usr/local/bin/mcode \
 && timeout 120 mcode --version

# --- Non-root run user (matches the Actions runner uid 1001) -----------
RUN useradd -m -u 1001 agent

# --- Baked agent configs (Owner: "make agent configs, too, and reuse them").
#     Keys are env-interpolated at run time; nothing secret is baked. -------
COPY docker/harness/opencode.json     /home/agent/.config/opencode/opencode.json
COPY docker/harness/goose-config.yaml /home/agent/.config/goose/config.yaml
# Global AGENTS.md = agent law, CONFIGURED into memory (Owner 2026-10-21
# 08:22Z "configure the agent to load global AGENTS.md"; 09:16Z "read docs
# for each agent for how they configure global AGENTS.md"). Verified against
# each agent's official docs on 2026-10-21:
#   OpenCode  ~/.config/opencode/AGENTS.md — "applied across all opencode
#             sessions" (opencode.ai/docs/rules); repo-root AGENTS.md also
#             rides instructions[] in opencode.json.
#   Goose     ~/.config/goose/.goosehints is the GLOBAL hints file (goose
#             config dir, ~/.config/goose/); repo-root AGENTS.md/.goosehints
#             are additionally read from CWD per session.
#   CodeBuddy ~/.codebuddy/CODEBUDDY.md is the USER-LEVEL memory file,
#             "takes effect in all projects"; repo-root AGENTS.md auto-loads
#             when no CODEBUDDY.md exists (documented backward compat).
#   Qoder     no global/user rules path documented — repo-root AGENTS.md is
#             auto-recognized (docs.qoder.com/user-guide/rules); no bake.
COPY AGENTS.md /home/agent/.config/opencode/AGENTS.md
COPY AGENTS.md /home/agent/.config/goose/.goosehints
COPY AGENTS.md /home/agent/.codebuddy/CODEBUDDY.md
# OWNER GLOBAL LAW (Owner order 2026-10-22 09:22Z: "You and your team
# members MUST follow it, except for my local-specific parts. This should
# be configured in agents/harnesses' configs to load."). Baked VERBATIM as
# the TOP layer of every agent's global config — the repo AGENTS.md below
# it stays the project layer. Local-specific parts (Guix box, emacsclient
# detection) self-neutralize in CI: INSIDE_EMACS is never set here.
COPY agent-team/AGENTS-GLOBAL.md /tmp/AGENTS-GLOBAL.md
RUN for f in /home/agent/.config/opencode/AGENTS.md \
            /home/agent/.config/goose/.goosehints \
            /home/agent/.codebuddy/CODEBUDDY.md; do \
      printf '\n\n=====\n\n# ==== OWNER GLOBAL LAW (agent-team/AGENTS-GLOBAL.md — top layer) ====\n\n' | cat - /tmp/AGENTS-GLOBAL.md "$f" > /tmp/.law-merge \
      && mv /tmp/.law-merge "$f"; \
    done && rm -f /tmp/AGENTS-GLOBAL.md
RUN chown -R agent:agent /home/agent

ENV HOME=/home/agent \
    GOOSE_PROVIDER=openrouter \
    GOOSE_MODEL=nvidia/nemotron-3.5-lightning:free

STOPSIGNAL SIGTERM
