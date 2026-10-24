/** App auth-gate mount proof (FR R-006) — the standalone page is DISCOVERED.
 *
 *  docs/page-registration.md pins a rendered promise: "App.svelte no longer
 *  imports [Login]; it renders `standalonePages[0]` while there is no token",
 *  so that a client shipping its own sign-in screen drops in a file and flips
 *  `nav: false, standalone: true` — no edit to App. The only existing render of
 *  that path (shell.test.ts "the whole App boots into the registered standalone
 *  page") mounts the real App over the real glob, so the discovered page IS the
 *  shipped Login and the test cannot tell a dynamic `standalonePages[0]` read
 *  apart from a hard `import Login`. Measured: replacing App's auth branch with
 *  a static Login import left the whole shipped suite green (451/35) — the
 *  promise was graded by a code comment, not by the DOM.
 *
 *  This file grades it through the render: the registry is stubbed, so App's
 *  auth gate is driven by whatever `standalonePages` holds. Two cases:
 *    1. a standalone entry pointing at a NON-Login probe component — App must
 *       render THAT component and none of Login's markup (kills the hard-import
 *       mutation, which would render Login regardless);
 *    2. an empty registry — App must show the friendly "No page declares
 *       `standalone: true`" message, the `{#if authPage}` else-branch the real
 *       glob can never reach (it always carries Login).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import App from "../../App.svelte";
import ProbeLogin from "./fixtures/ProbeLogin.svelte";
import { app } from "../stores";

/** The registry slot App reads for the auth gate, mutable per test.
 *  vi.mock is hoisted above imports, so the stub reads a hoisted holder. */
const registry = vi.hoisted(() => ({ standalone: [] as unknown[] }));

vi.mock("../pages", () => ({
  get standalonePages() {
    return registry.standalone;
  },
  // Shell/Sidebar read these too; never rendered on the no-token path, but the
  // bindings must exist or the App module graph fails to import.
  pageById: () => undefined,
  navPages: () => [],
  pageHref: (page: { path: string }) => "#" + page.path,
  get pages() {
    return [];
  },
  // union-tree bindings (2241's auth-gate slot rides the merged App/Sidebar):
  // the real registry derives authPage = standalonePages[0] and authHref from
  // it; the mock mirrors that shape so the module graph imports clean.
  get authPage() {
    return registry.standalone[0];
  },
  authHref: () => "#/login",
  get refusedPages() {
    return [];
  },
}));

const mounted: Array<Record<string, any>> = [];
let snapshot: any;

beforeEach(() => {
  const a = get_snapshot();
  snapshot = a;
  registry.standalone = [];
});

function get_snapshot() {
  // read once without subscribing
  let value: any;
  const un = app.subscribe((v) => (value = v));
  un();
  return { ...value };
}

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  app.set(snapshot);
  location.hash = "";
  vi.unstubAllGlobals();
});

/** Boot App with no token so the auth branch paints, then flush. */
async function bootNoToken() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("", { status: 404 })),
  );
  localStorage.removeItem("dad.token");
  app.update((a) => ({ ...a, token: "", booted: true }));
  location.hash = "#/";
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(App, { target: host }));
  });
  await new Promise((r) => setTimeout(r, 0));
  flushSync(() => {});
  return host;
}

const text = (host: Element) => (host.textContent ?? "").replace(/\s+/g, " ").trim();

describe("App auth gate renders the page the registry declares", () => {
  it("renders the discovered standalone component, not a hard-imported Login", async () => {
    registry.standalone = [
      { id: "ProbeLogin", title: "Probe", path: "/login", component: ProbeLogin, standalone: true },
    ];
    const host = await bootNoToken();

    // the probe's own markers prove App read standalonePages[0].component...
    expect(text(host)).toContain("Probe Sign-In Gate");
    expect(text(host)).toContain("standalone-from-registry");
    // ...and that it did NOT fall back to the shipped Login form
    expect(host.querySelector("#probe-signin")).not.toBeNull();
    expect(text(host)).not.toContain("Username");
    expect(document.querySelector("aside")).toBeNull(); // still no shell pre-token
  });

  it("shows the friendly setup message when no page declares standalone", async () => {
    registry.standalone = [];
    const host = await bootNoToken();

    // App.svelte's `{#if authPage}` else-branch — the real glob can never reach
    // it (Login is always discovered), so only a stubbed registry exercises it.
    expect(text(host)).toContain("No page declares");
    expect(text(host)).toContain("standalone: true");
    expect(text(host)).toContain("sign-in module is required");
    expect(host.querySelector("#probe-signin")).toBeNull();
    expect(text(host)).not.toContain("Username");
  });
});
