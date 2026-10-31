# BURN-QUEUE — deepseek-v4.1-flash@codebuddy exhaust lane (Owner order 2026-10-31)

One task per line. The burn workflow (`.github/workflows/burn-codebuddy.yml`)
feeds each line to `codebuddy -p ... --model deepseek-v4.1-flash` and collects
the work product in the run artifacts. The LEAD triages artifacts and turns
accepted outputs into seat dispatches. Append tasks below; do not edit
lead-owned files to change the workflow itself.

Tasks must be self-contained, read-only analysis/drafting work on THIS repo.
1. Full code review of plugin/src/admineverywhere/branding.py: correctness, path-traversal/symlink edge cases, validation bypasses, and a list of test gaps with concrete pytest names.
2. Security review of the admin auth flow: app/src/lib/secrets.ts, token storage, login page handling of the api url; rank findings by severity with file:line evidence.
3. Draft docs/BRAND.md from the ACTUAL code: read plugin/src/admineverywhere/branding.py and app/src/lib/brand.gen.ts, document every ALLOWED_KEYS field, asset rules, the stamping pipeline order, and a worked example for a new brand "Acme".
4. Produce a Tauri v2 Android release checklist mapped to THIS repo: INTERNET permission, network security config, adaptive icons from `tauri icon`, Android 12+ SplashScreen theming, signing, and how each is (or is not) covered by plugin/src/admineverywhere/branding.py today.
5. i18n audit: enumerate every user-visible English string in app/src/**/*.svelte, propose a translation-key structure and the minimal svelte-i18n wiring diff (draft only).
6. Performance review of the svelte admin app: read app/vite.config and the largest imports under app/src, list the top 10 bundle-reduction opportunities with estimated impact.
7. Coverage-gap analysis: diff plugin/tests/test_branding.py behavior coverage against branding.py; list uncovered branches with the exact test each needs.
8. Draft release notes for the next Freshorama admin release from `git log --oneline -25` in this repo: group into Branding / Loaders / Fixes / Infra, plain-English, no jargon.
9. Emacs client docs: read the build_emacs implementation in plugin/src/admineverywhere/, then draft the user-facing README section (install, load, connect, auth) with real commands.
10. MCP server docs: read the build_mcp implementation, then draft the user-facing README section: install, tool list with arguments, auth model, worked curl/claude-desktop config example.
11. Widget accessibility review: app/src/lib/widgets or components for LiveOrders/TodayRevenue/CompletionGauge — ARIA roles, color-contrast against brand colors (#006e33 primary, #22be6f accent, #f6faf6 bg), and a concrete fix list.
12. Write the end-to-end QA plan for "deeply branded admin apps" across web/desktop/android/mcp/emacs: every check (brand appName, no stock splash, green logo, baked apiUrl, intro loader plays) mapped to the automated test that could enforce it.
