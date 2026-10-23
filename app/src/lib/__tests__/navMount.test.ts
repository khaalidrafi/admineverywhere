/** Sidebar + nav derivation (FR R-006) — the nav you SEE is the nav the GLOB declared.
 *
 *  The R-006 promise is negative as much as positive: "the router owns NO route
 *  table, the shell imports NO page, the sidebar types NO entry". The positive
 *  half is graded elsewhere (pages.test.ts over the real glob, shell.test.ts over
 *  a rendered shell, gapMount.test.ts over the Modules screen). The negative half
 *  was not graded at all: `shell.test.ts` asserts the nav CONTAINS Dashboard,
 *  Modules and Branding, so a hand-typed fourth button — the exact fork R-006
 *  exists to kill — passed. Measured before writing (grep for `#/<declared path>`
 *  across app/src outside __tests__): ONE page-specific route literal survived in
 *  product code, `Sidebar.svelte` signing out into a hard-coded `#/login`, which
 *  strands the user on a hash no page declares the moment a client ships its own
 *  sign-in module — the flow docs/page-registration.md promises.
 *
 *  So every assertion here is exact-set or wire-level: rendered nav == declared
 *  nav (both directions, in registry order), each nav click routes through
 *  `pageHref()` to the href that page DECLARED, Sign out lands on the href of the
 *  page the registry marks standalone, and a source scan refuses any product file
 *  that spells a declared page's hash by hand. The scan pins its own population,
 *  because a comparison cannot see its own coverage (DEVGUIDE ELEVENTH law): a
 *  collapsed glob would answer "zero violations" over an empty domain.
 */
import { afterEach, describe, expect, it } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import type { Component } from "svelte";
import Sidebar from "../../components/Sidebar.svelte";
import { app, claims, logout } from "../stores";
import { navPages, pageHref, standalonePages, pages } from "../pages/index";

const mounted: Array<Record<string, any>> = [];

function render(component: Component, props: Record<string, unknown> = {}): HTMLElement {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  return host;
}

function goto(hash: string) {
  location.hash = hash;
  flushSync(() => window.dispatchEvent(new Event("hashchange")));
}

const label = (el: Element) => (el.textContent ?? "").replace(/\s+/g, " ").trim();

/** The declared nav buttons only: the `<nav>` group holds the main entries and,
 *  once a schema lands, the schema-derived Models group. No schema in these tests,
 *  so every button in here is a declaration. */
function mainButtons(aside: HTMLElement): HTMLButtonElement[] {
  const nav = aside.querySelector("nav");
  expect(nav, "the sidebar rendered no <nav> group").not.toBeNull();
  return [...nav!.querySelectorAll("button")] as HTMLButtonElement[];
}

/** The bottom settings block (rendered only when something declares it). */
function settingsButtons(aside: HTMLElement): HTMLButtonElement[] {
  const groups = [...aside.querySelectorAll("div")].filter((d) =>
    [...d.children].some((c) => label(c) === "Settings"),
  );
  expect(groups.length, "the Settings heading rendered without its block").toBe(1);
  return [...groups[0].querySelectorAll("button")] as HTMLButtonElement[];
}

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  logout();
  claims.set(null);
  goto("#/");
});

describe("the rendered nav is exactly the declared nav", () => {
  it("main group: one button per navPages('main'), same order, nothing typed by hand", () => {
    const aside = render(Sidebar);
    const declared = navPages("main");

    expect(declared.length, "the registry declares no main nav entry").toBeGreaterThan(0);
    // exact set AND exact order: an extra hand-typed button is as red as a missing one
    expect(mainButtons(aside).map(label)).toEqual(declared.map((p) => p.title));
  });

  it("settings group: exactly the pages that declared nav: 'settings'", () => {
    const aside = render(Sidebar);
    const declared = navPages("settings");

    expect(declared.length, "the registry declares no settings nav entry").toBeGreaterThan(0);
    expect(settingsButtons(aside).map(label)).toEqual(declared.map((p) => p.title));
    // and none of them leaked into the top group
    for (const page of declared) {
      expect(mainButtons(aside).map(label)).not.toContain(page.title);
    }
  });

  it("a declared nav entry renders exactly once across both groups", () => {
    const aside = render(Sidebar);
    const rendered = [...mainButtons(aside), ...settingsButtons(aside)].map(label);
    const all = navPages();

    expect(rendered.length).toBe(all.length); // no duplicate, no omission
    expect(new Set(rendered).size).toBe(rendered.length);
    expect([...rendered].sort()).toEqual(all.map((p) => p.title).sort());
  });

  it("a page that is not a nav page never appears as a nav button", () => {
    const aside = render(Sidebar);
    const navIds = new Set(navPages().map((p) => p.id));
    const rendered = [...mainButtons(aside), ...settingsButtons(aside)].map(label);

    for (const offNav of pages.filter((p) => !navIds.has(p.id))) {
      expect(rendered, `${offNav.id} is nav:false or standalone and must not be linked`).not.toContain(offNav.title);
    }
  });

  it("clicking each nav button routes to the href THAT PAGE declared", () => {
    const aside = render(Sidebar);
    const declared = navPages("main");

    declared.forEach((page, i) => {
      mainButtons(aside)[i].click();
      expect(location.hash, `${page.id} click`).toBe(pageHref(page));
      goto(pageHref(page)); // the browser's reply
      const lit = mainButtons(aside).filter((b) => b.className.includes("bg-primary/15")).map(label);
      expect(lit, `${page.id} lit the wrong entry`).toEqual([page.title]);
    });
  });
});

describe("Sign out follows the registry, not a typed hash", () => {
  function footerButtons(aside: HTMLElement): HTMLButtonElement[] {
    const nav = aside.querySelector("nav")!;
    const declared = new Set([...mainButtons(aside), ...settingsButtons(aside)]);
    return ([...aside.querySelectorAll("button")] as HTMLButtonElement[]).filter(
      (b) => !nav.contains(b) && !declared.has(b),
    );
  }

  it("clears the token and lands on the declared standalone page's href", () => {
    const authPage = standalonePages[0];
    expect(authPage, "no page declares standalone: true").toBeDefined();

    app.update((a) => ({ ...a, token: "tkn", booted: true }));
    goto(pageHref(authPage!));
    const aside = render(Sidebar);
    const signOut = footerButtons(aside).find((b) => label(b) === "Sign out")!;

    signOut.click();
    expect(get(app).token).toBe(""); // the session really ended
    expect(get(claims)).toBeNull(); // and its claims with it
    // the href comes from the DECLARATION — the page the registry marks
    // standalone, not the first NAV entry (Dashboard, order 10), and not a typed
    // literal. The two are distinguishable precisely because the auth page is
    // declared with nav: false.
    expect(location.hash).toBe(pageHref(authPage!));
    expect(location.hash).toBe("#" + authPage!.path);
    expect(location.hash).not.toBe(pageHref(navPages("main")[0]));
  });

  it("a standalone page is never offered as a nav button", () => {
    const aside = render(Sidebar);
    const rendered = [...mainButtons(aside), ...settingsButtons(aside)].map(label);
    for (const standalone of standalonePages) {
      expect(rendered).not.toContain(standalone.title);
    }
  });
});

describe("no product file hand-types a declared page's route", () => {
  /** Every .svelte/.ts under src/, raw text, keyed by file. The glob is eager so
   *  a new file joins the domain automatically — same widening law as the page
   *  registry itself: adding a module must not break this test, only widen it. */
  const sources = import.meta.glob("../../**/*.{svelte,ts}", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  /* Vite keys a glob by whatever prefix the pattern needs ("../../App.svelte",
   * "./gapMount.test.ts"), so the RELATIVE form is not a stable identity. Every
   * key is resolved against this module's own URL before it is filtered or
   * reported — a scan that silently keeps its sibling tests in domain would be
   * grading fixtures instead of product code. */
  const domain = Object.entries(sources)
    .map(([key, text]) => {
      const abs = new URL(key, import.meta.url).pathname;
      return { abs, rel: abs.split("/src/").pop()!, text };
    })
    .filter(({ abs }) => !abs.includes("/__tests__/"));

  /** A hash literal is forbidden in a file other than the one that DECLARES it. */
  function ownerOfFile(file: string): string | undefined {
    const id = file.split("/").pop()!.replace(/\.svelte$/, "");
    return pages.find((p) => p.id === id)?.id;
  }

  it("the raw glob really discovered the product tree (the scan can see its own coverage)", () => {
    // A collapsed domain would answer "no violations" over nothing, so the
    // population is pinned: the shipped tree is far bigger than any floor here,
    // and every declared route is searched.
    expect(domain.length, "the scan's file domain collapsed; a violation could hide").toBeGreaterThanOrEqual(20);
    const paramFree = pages.filter((p) => p.params.length === 0 && p.path !== "/");
    expect(paramFree.length, "no declared page path was searched").toBeGreaterThanOrEqual(4);
    const files = domain.map((d) => d.rel);
    for (const expected of ["components/Sidebar.svelte", "components/Shell.svelte", "App.svelte", "lib/router.ts", "lib/pages/index.ts"]) {
      expect(files, `${expected} left the scan domain`).toContain(expected);
    }
    expect(files.filter((f) => f.includes("__tests__")), "a test file leaked into the product domain").toEqual([]);
  });

  it("no file outside a page's own declaration spells that page's hash route", () => {
    const concrete = pages.filter((p) => p.params.length === 0 && p.path !== "/");
    const offenders: string[] = [];
    let graded = 0; // every (file, declared href) pair actually compared
    for (const { abs, rel, text } of domain) {
      const owner = ownerOfFile(abs);
      for (const page of concrete) {
        graded++;
        if (owner === page.id) continue; // declaring its own path is the contract
        if (text.includes(`#${page.path}`)) offenders.push(`${rel}: #${page.path} (${page.id})`);
      }
    }
    // A scan that silently checked nothing would print the same clean answer as
    // one that found nothing, so its own work is pinned: every product file
    // against every concrete declared href.
    expect(graded, "the scan compared no file/route pair").toBe(domain.length * concrete.length);
    expect(graded).toBeGreaterThan(0);
    expect(offenders, "a declared route was hand-typed instead of taken from the registry").toEqual([]);
  });

  /** The other half of the same fork: before R-006 `Shell.svelte` imported each
   *  page and switched on the route name. App.svelte renders the auth gate from
   *  the registry today, and a mount test cannot tell that from a direct import
   *  of Login.svelte — the DOM would look identical. So the IMPORT graph is
   *  scanned too: only the glob (lib/pages/index.ts) may reach a page file. */
  it("no product file imports a page module directly — only the glob may", () => {
    const importer = /(?:from|import)\s*\(?\s*["'][^"'"]*\/pages\/[^"'"/]+\.svelte["']/;
    const allowed = "lib/pages/index.ts"; // the registry itself spells no page either: it globs
    const offenders: string[] = [];
    let graded = 0;
    for (const { rel, text } of domain) {
      if (rel === allowed || rel.startsWith("pages/")) continue; // the glob + the pages themselves
      graded++;
      const line = text.split("\n").findIndex((l) => importer.test(l));
      if (line >= 0) offenders.push(`${rel}:${line + 1}: ${text.split("\n")[line].trim()}`);
    }
    expect(graded, "the import scan walked no product file").toBeGreaterThan(0);
    expect(offenders, "a component hand-imported a page instead of letting the registry discover it").toEqual([]);
  });
});
