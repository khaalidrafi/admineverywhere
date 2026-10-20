# admincraft agent harness — CI turn container with agent bodies
# PREINSTALLED (Owner order 2026-10-20 #hq: agents go into the image,
# not into CI). Secrets are NEVER baked: keys are env-injected per run
# from repo secrets.
#
# Bodies chosen BY FIT (Owner law 2026-10-21 17:47Z: for API-served
# brains you pick the agent that fits and install the model brain —
# "any agent can ride APIs, no surprise"):
#   - qoder  — agentic coding CLI, PAT-auth (auto-detects CI, no
#              browser); the ONE lane PROVEN on CI for this team
#              (proof run 39477554903: real qoder JSON result, 72s of
#              agentic work; budget artifact fixed --max-turns 100).
#   - nodejs/npm — the repo's FE half (Svelte 5/Vite/Tauri) is real
#              work; vitest runs at turn time with `npm ci`.
# Python project deps (Django/DRF/drf-spectacular/cors + pytest) are
# baked so the landing gate runs offline-fast inside segments too.

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl ca-certificates jq procps nodejs npm \
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

# --- Non-root run user (matches the Actions runner uid 1001) -----------
RUN useradd -m -u 1001 agent

ENV HOME=/home/agent

STOPSIGNAL SIGTERM
