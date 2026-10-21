# Page registration (ROADLOG R-006) — drop a file, get a route and a nav entry

Reference implementation: `app/src/lib/pages/index.ts` (registry) +
`app/src/lib/router.ts` (matcher) + `app/src/pages/Modules.svelte` (a module
added by the mechanism itself). Tests: `app/src/lib/__tests__/pages.test.ts`
(contract, 27) and `shell.test.ts` (rendered DOM, 8).

## Why this exists

Before R-006 a new screen was a **fork**: the route was hard-coded in
`parseHash`, the component was imported in `Shell.svelte`, and the sidebar
button was typed by hand in `Sidebar.svelte`. Three files to touch per module,
each of them shared — the opposite of the widget contract ("drop one `.svelte`
file in `src/widgets/`, no registry to edit"). R-006 mirrors that contract for
pages, so a non-CRUD module (an invoice list, an audit screen, a report) is one
file.

## The contract

One `.svelte` file in `app/src/pages/` with a `<script module>` export:

```svelte
<script module lang="ts">
  export const meta = {
    title: "Activity",        // required — without it the file is ignored
    path: "/activity",        // required, absolute
    nav: "main",              // false | "main" | "settings" — default "main"
    icon: "chat",             // a name from components/Icon.svelte
    order: 30,                // sidebar order, default 100
    standalone: false,        // true = rendered outside the shell (auth gate)
  };
</script>
```

The glob (`import.meta.glob("../../pages/*.svelte", { eager: true })`) finds it,
the registry validates it, `setPages()` hands the router its route table, the
shell renders the component, and the sidebar lists the entry. Nothing else is
edited — that is the promise, and `pages.test.ts` + `shell.test.ts` enforce it
("Modules" is discovered by the glob, never listed by a test).

### Path patterns

| pattern | answers | notes |
| --- | --- | --- |
| `/` | `#/` only | root is exact; never a prefix |
| `/branding` | `#/branding` | static |
| `/m/:modelId` | `#/m/order` | capture → prop `modelId` |
| `/m/:modelId/:recordId?` | `#/m/order`, `#/m/order/7` | optional tail, last segment only |

Captured segments are spread as **props** — the shell renders the discovered
component with `<Page {...$route.params} />` (`{@const Page = current.component}`;
`<svelte:component>` is deprecated in runes mode), so a pattern's parameter names
are the component's prop names. `ModelPage` therefore takes `modelId` + `recordId`
— R-006 renamed its `id` prop to `modelId` so the declaration and the signature
say the same thing.

Matching prefers **fewest captures**, which is why a static `/legacy` still
wins over a sibling `/:id`. A hash no pattern answers resolves to
`kind: "none"` and the shell says so — the router never invents a page from a
prefix, the same law as `actionPath()` (paths come from the schema) and
`resolveAxis()` (an axis is declared, not guessed).

## Refusals: a broken declaration registers nothing

A page whose declaration cannot be honoured is **refused** — no route, no nav
entry — and `refusedPages` names the reason. The Modules page renders that list
in-app, so a broken drop-in is visible instead of silent:

| reason | example |
| --- | --- |
| `meta.path is required and must be a string, got undefined` | `meta = { title: "X" }` |
| `path "about" does not start with "/"` | relative paths |
| `path "/a//b" has an empty segment` | doubled slashes |
| `path "/a/:" has a parameter with no name` | `:/` |
| `path "/a/:id?/b" puts an optional parameter before the end` | optional must be last |
| `path "/a/:id/:id" repeats the parameter "id"` | duplicate captures |
| `page A declares meta but has no default export` | module, not component |
| `nav "main" needs a param-free path, but "/b/:id" captures id` | a nav entry needs a concrete href — declare `nav: false` |
| `path "/m/:otherId" overlaps "/m/:modelId", already claimed by "One"` | one hash, two owners |

Overlap is about **coverage, not names**: `/m/:a` and `/m/:b` answer the same
hashes, so the later declaration loses. `/m/:id` and `/m/new` are *not* a
collision (static beats param, decided by specificity). A trailing optional
tail does collide with the shorter pattern it swallows (`/m/:id` + `/m/:id/:rec?`).

A file with **no `meta`** is ignored rather than refused — the widget rule: a
half-written page must be harmless. `pages.test.ts` asserts `refusedPages` is
empty at HEAD, so a declaration that breaks the shipped app fails the suite.

## The auth gate is a page too

`Login.svelte` declares `standalone: true`. `App.svelte` no longer imports it;
it renders `standalonePages[0]` while there is no token, and the shell refuses
to render a standalone page inside itself. A client that ships its own sign-in
screen drops in a file and flips `nav: false, standalone: true`.

## Copy checklist (adding a module)

1. Create `app/src/pages/Thing.svelte`; put `meta` in `<script module>` (runes
   are not available there — the export must be static).
2. Give it a unique path shape and a real `Icon.svelte` name; pick `order`.
3. Needs a URL parameter? Declare `nav: false` and read the param as a prop.
4. No registry, router, shell or sidebar edit. `npm test` proves it: the new id
   must appear in `pages` without any test naming it.
5. If it is refused, the Modules page says why; fix the declaration, not the
   registry.

## Component tests became possible (the enabler)

`shell.test.ts` is the repo's first real `.svelte` render test. Two facts it
pins down:

- Vitest resolves svelte's **SSR** build by default (`index-server.js`, where
  `mount()` throws `lifecycle_function_unavailable`). The fix is one condition
  in `vite.config.ts`: `resolve: { conditions: ["browser"] }`, plus
  `test.server.deps.inline: [/svelte/]` so every svelte import stays in one
  transformed graph. That — not a Svelte 5 limitation — was the "mount()
  harness blocks component proof" finding filed twice on 2026-10-20.
- happy-dom assigns `location.hash` but never fires `hashchange`, and Svelte 5
  paints on a microtask. Tests must `window.dispatchEvent(new Event("hashchange"))`
  inside `flushSync(...)`. Teardown is `unmount(instance)` (5.13+), and an
  unclean teardown leaves a stale `<main>` that the next `querySelector` reads —
  which looks exactly like a routing bug and is not one.

The Modules page — the screen that SHOWS the registry — is itself mounted in
`app/src/lib/__tests__/gapMount.test.ts` with the registry module stubbed (the
real glob can only ever hand it the shipped pages, so a refusal would need a
deliberately broken file in `src/pages/`). Pinned through its DOM: one row per
declared page in registry order, `nav:false` as a dash with the standalone
badge, a parameterised page offering NO Open button, Open routing through
`pageHref()` rather than a hand-built hash, and every refused declaration
rendering `id: reason` verbatim while registering no row. The header's page and
model counters are asserted with different numbers on purpose — with `2 · 2` the
component could swap the two variables and stay green.

## Open edges (deliberately not in R-006)

- No nested/parallel page groups (`/m/:id/history/:tab`), no async chunk
  loading (the glob is eager, as with widgets), no route guards — RBAC (R-007)
  owns visibility filtering, and it should filter `navPages()` rather than edit
  this file.
- The page `title` is declared but not yet applied to `document.title` per
  route; `applyBrand()` owns the title today.
- `collectPages()` refuses overlapping declarations; it does not warn about an
  unreachable nav entry hidden behind an identical `order` value.
