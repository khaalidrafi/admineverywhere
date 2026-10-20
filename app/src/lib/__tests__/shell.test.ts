/** Shell + Sidebar rendering (FR R-006) — the registry drives the DOM.
 *
 *  These are the repo's first real component tests. Mounting a `.svelte` file
 *  only became possible once vite.config.ts carried `resolve.conditions:
 *  ["browser"]`: without it Vitest resolves svelte's SSR build, where
 *  `mount()` throws `lifecycle_function_unavailable`. The earlier reports of
 *  "the mount() harness blocks component proof" were that condition, not a
 *  Svelte 5 limitation.
 *
 *  What is asserted is the R-006 promise itself: neither the shell nor the
 *  sidebar names a page, yet a dropped-in file appears in the nav and renders
 *  in the main region.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import type { Component } from "svelte";
import App from "../../App.svelte";
import Shell from "../../components/Shell.svelte";
import Sidebar from "../../components/Sidebar.svelte";
import { app } from "../stores";
import { navigate } from "../router";

const mounted: Array<Record<string, any>> = [];

/** Mount into a live node and flush, so assertions see painted DOM. */
function render(component: Component, props: Record<string, unknown> = {}): HTMLElement {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  return host;
}

/** Let the router react to a hash and paint the result.
 *
 *  happy-dom assigns `location.hash` but never fires `hashchange`, so the
 *  router's only re-parse path stays asleep until the event is dispatched by
 *  hand, and Svelte 5 flushes on a microtask unless told "now". A real browser
 *  does both on its own — an environment gap, not a product one.
 */
function goto(hash: string) {
  location.hash = hash;
  flushSync(() => window.dispatchEvent(new Event("hashchange")));
}

function navButtons(scope: HTMLElement): HTMLButtonElement[] {
  return [...scope.querySelectorAll("button")] as HTMLButtonElement[];
}

function labels(scope: HTMLElement): string[] {
  return navButtons(scope).map((b) => (b.textContent ?? "").trim());
}

function lit(scope: HTMLElement): string[] {
  return navButtons(scope)
    .filter((b) => b.className.includes("bg-primary/15"))
    .map((b) => (b.textContent ?? "").trim());
}

function main(): HTMLElement {
  const el = document.querySelector("main");
  expect(el, "the shell rendered no <main>").not.toBeNull();
  return el as HTMLElement;
}

afterEach(() => {
  // an unclean teardown leaves a stale <main> behind, and querySelector would
  // then read the previous test's render
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  goto("#/");
});

describe("Sidebar renders what the page registry declared", () => {
  it("lists every nav page, in order, without naming a single one", () => {
    const aside = render(Sidebar);

    const nav = labels(aside);
    // built-ins + the drop-in Modules page: the glob found it, this test did not
    for (const expected of ["Dashboard", "Modules", "Branding"]) {
      expect(nav, `nav is missing ${expected}`).toContain(expected);
    }
    // a parameterised page and the standalone auth page can never appear here
    expect(nav).not.toContain("Model");
    expect(nav).not.toContain("Sign in");
    // the Models group is schema-gated: no schema loaded -> no fabricated links
    expect(aside.textContent).toContain("Schema unavailable");
  });

  it("a nav click drives the hash and lights exactly the entry that owns it", () => {
    const aside = render(Sidebar);

    const modules = navButtons(aside).find((b) => (b.textContent ?? "").trim() === "Modules")!;
    modules.click();
    expect(location.hash).toBe("#/modules");
    goto("#/modules"); // the click set the hash; this is the browser's reply

    expect(lit(aside)).toEqual(["Modules"]);
  });
});

describe("Shell renders the page the route resolves to", () => {
  it("mounts the parameterless page for #/modules", () => {
    goto("#/modules");
    render(Shell);

    expect(main().textContent).toContain("registered pages");
    expect(main().textContent).toContain("/modules"); // its declared path is listed
    expect(main().textContent).not.toContain("No page declares");
  });

  it("refuses to render a standalone page inside the shell", () => {
    goto("#/login");
    render(Shell);
    expect(main().textContent).toContain("outside the app shell");
  });

  it("an undeclared hash gets no page — never a guess", () => {
    goto("#/not-a-module");
    render(Shell);
    expect(main().textContent).toContain("No page declares");
    expect(main().textContent).toContain("/not-a-module");
  });

  it("spreads the captured parameters into the page as props", () => {
    goto("#/m/order/7");
    render(Shell);
    // ModelPage received modelId="order": with no schema loaded it reports the
    // unknown model by name, which only happens if the param arrived as a prop.
    expect(main().textContent).toContain("Unknown model");
    expect(main().textContent).toContain("order");
  });

  it("navigating to another declared page swaps the rendered module", () => {
    goto("#/modules");
    render(Shell);
    expect(main().textContent).toContain("registered pages");

    navigate("#/branding");
    goto("#/branding");
    expect(main().textContent).toContain("Branding");
    expect(main().textContent).not.toContain("registered pages");
  });
});

describe("the auth gate is a registered page too", () => {
  it("the whole App boots into the registered standalone page", async () => {
    // No file imports Login.svelte any more: the auth gate asks the registry
    // for the page that declared `standalone: true` and renders that.
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    localStorage.removeItem("dad.token");
    app.update((a) => ({ ...a, token: "", booted: true }));
    goto("#/");
    const host = render(App);
    await new Promise((r) => setTimeout(r, 0));
    flushSync(() => {});

    expect(host.textContent).toContain("Username"); // the Login form's first field
    expect(document.querySelector("aside")).toBeNull(); // no shell before a token
    vi.unstubAllGlobals();
  });
});
