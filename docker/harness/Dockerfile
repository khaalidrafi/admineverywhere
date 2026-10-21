# admincraft agent harness — CI turn container with agent bodies
# PREINSTALLED (Owner order 2026-10-20 #hq: agents go into the image,
# not into CI). Secrets are NEVER baked: keys are env-injected per run
# from repo secrets.
#
# REFRESHED by agent-team.el setup (Owner order 2026-10-21 10:12Z): the
# pkg's proven recipe merged in — OpenCode + Goose + CodeBuddy bodies
# (the goose fallback lanes were DEAD before: the old image baked only
# qoder), and the GLOBAL AGENT-LAW CONFIG bakes verified per agent docs
# (OpenCode ~/.config/opencode/AGENTS.md, Goose ~/.config/goose/.goosehints,
# CodeBuddy ~/.codebuddy/CODEBUDDY.md — baked from docker/harness/
# AGENT-LAW.md; a repo-root AGENTS.md is never created in this project).
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

# --- Non-root run user (matches the Actions runner uid 1001) -----------
RUN useradd -m -u 1001 agent

# --- Baked agent configs (Owner: "make agent configs, too, and reuse them").
#     Keys are env-interpolated at run time; nothing secret is baked. -------
COPY docker/harness/opencode.json     /home/agent/.config/opencode/opencode.json
COPY docker/harness/goose-config.yaml /home/agent/.config/goose/config.yaml
# Global agent law = CONFIGURED into memory (Owner 2026-10-21 08:22Z
# "configure the agent to load global AGENTS.md"; 09:16Z "read docs for
# each agent for how they configure global AGENTS.md"). Bake source is
# docker/harness/AGENT-LAW.md — a repo-root AGENTS.md is NEVER created in
# this project (Owner 2026-10-21: "It shouldn't be made!"). Verified per
# each agent's official docs on 2026-10-21:
#   OpenCode  ~/.config/opencode/AGENTS.md — "applied across all opencode
#             sessions" (opencode.ai/docs/rules); repo-root file (where a
#             project has one of its own) also rides instructions[] in
#             opencode.json.
#   Goose     ~/.config/goose/.goosehints is the GLOBAL hints file (goose
#             config dir, ~/.config/goose/); repo-root AGENTS.md/.goosehints
#             are additionally read from CWD per session.
#   CodeBuddy ~/.codebuddy/CODEBUDDY.md is the USER-LEVEL memory file,
#             "takes effect in all projects".
#   Qoder     no global/user rules path documented — the team law reaches
#             it via the dispatch preamble (TEAM-CONTROL.org + TEAM.md
#             manual pointer); no bake, no repo-root file.
COPY docker/harness/AGENT-LAW.md /home/agent/.config/opencode/AGENTS.md
COPY docker/harness/AGENT-LAW.md /home/agent/.config/goose/.goosehints
COPY docker/harness/AGENT-LAW.md /home/agent/.codebuddy/CODEBUDDY.md
RUN chown -R agent:agent /home/agent

ENV HOME=/home/agent \
    GOOSE_PROVIDER=openrouter \
    GOOSE_MODEL=nvidia/nemotron-3.5-lightning:free

STOPSIGNAL SIGTERM
