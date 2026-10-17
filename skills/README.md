# skills/ — the admincraft agent skills

Two skills ship with the repo (identical engine scripts in each bundle,
by design — skills are self-contained and get copied around):

| skill | when |
| --- | --- |
| `admincraft-onboard` | wire an existing Django/DRF repo onto admincraft (plugin install, settings/urls, brand, client config, verify) |
| `admincraft-craft` | branding & releases: derive a brand from the project's source or guide the user; runtime (in-app) vs build-time (launcher) layers; icon regeneration; release checklist |

Both skills have two modes — **ask** (default: confirm branding choices
and irreversible edits in one batch) and **auto** (derive everything
from the project's own source, apply, report) — selected from the user's
phrasing.

## Layout

```
skills/admincraft-onboard/     SKILL.md, scripts/{inspect_project,derive_brand}.py,
                               references/wiring.md, evals/evals.json
skills/admincraft-craft/       SKILL.md, scripts/{inspect_project,derive_brand}.py,
                               references/branding.md, evals/evals.json
```

The scripts are pure-stdlib Python 3.10+ and run standalone:

```bash
python skills/admincraft-craft/scripts/inspect_project.py --root <repo>
python skills/admincraft-craft/scripts/derive_brand.py --root <repo> --out <repo>/brand
```

## Installing for your agent

Copy either directory into your agent's skills location (e.g.
`~/.claude/skills/` or your runtime's skills dir). The `scripts/` are
self-contained; keep them next to their SKILL.md.

If you edit the shared scripts, edit them in BOTH skill bundles (they
are intentionally duplicated for portability).
