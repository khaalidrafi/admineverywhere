# frontend-dist (Nix flake input)

This directory is the default value of the `frontend-dist` flake input and
intentionally contains only this README — the repo never ships prebuilt web
assets.

`nix build .#django-ai-dashboard` fails with instructions until you pass a
real Vite bundle:

    cd app && npm ci && npm run build
    nix build --override-input frontend-dist "$(nix store add-path app/dist)" .#django-ai-dashboard

The demo-CI `nix` job (`.github/workflows/build-demo.yml.disabled` while CI
is parked — rename back to `.yml` when re-enabling) does exactly this after
building the web bundle.
