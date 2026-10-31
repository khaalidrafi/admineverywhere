/** The login screen, mounted for real — the golden path of the whole demo
 *  flow (login admin/admin123 → dashboard → Ctrl+K) had ZERO wire proof:
 *  every consumer test mocked `../stores`, so `login()`, `loadSchema()` and
 *  the FR-R007 claims fetch ran their way, but nobody ever judged what the
 *  PAGE actually sends. Here neither stores nor api nor secrets is stubbed:
 *  only fetch is, and every assertion is about bytes and URLs — the POST
 *  goes to the config's authPath (never a guessed /api-token-auth/), with a
 *  JSON body and NO Authorization header; the token that comes back is what
 *  the schema GET carries; the claims read travels the path the DOCUMENT
 *  names; the password never rides in a URL; and the three error branches
 *  (400 invalid credentials, network unreachable + banner flag, any other
 *  status) land as inline text the user can read. Harness = browser resolve
 *  condition + flushSync + stubbed fetch, as in lifecycleMount.test.ts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import Login from "../../pages/Login.svelte";
import Toaster from "../../components/Toaster.svelte";
// the REAL page registry (not a stub) so the post-login root hash resolves
import "../pages";
import { app, claims, toasts } from "../stores";
import { route } from "../router";
import fixture from "./fixtures/openapi.json";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const AUTH_URL = "http://api.test/api/auth/token/";
const SCHEMA_URL = "http://api.test/api/schema/";
/** /api/me/ is in the captured fixture, so mePath is DOCUMENTED — the
 *  claims read must go exactly here, never a hand-written guess. */
const ME_URL = "http://api.test/api/me/";

const mounted: Array<Record<string, any>> = [];
let appSnapshot: any;

beforeEach(() => {
  appSnapshot = get(app);
  localStorage.clear();
  // the user really came here on the login hash, so a navigate("#/") after
  // a successful sign-in is a CHANGE of the hash, not a same-hash re-trigger
  location.hash = "#/login";
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!.instance);
  document.body.innerHTML = "";
  mockFetch.mockReset();
  toasts.set([]);
  claims.set(null);
  app.set(appSnapshot);
  localStorage.clear();
  location.hash = "#/";
  vi.restoreAllMocks();
});

function reply(status: number, data: any) {
  const text = typeof data === "string" ? data : JSON.stringify(data);
  return {
    ok: status < 400,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : null),
  };
}

/** Route by URL so the test can assert WHICH endpoint the page believed in. */
function serve(overrides: Record<string, { status: number; body: any }> = {}) {
  mockFetch.mockImplementation(async (url: string) => {
    const u = String(url);
    for (const [needle, r] of Object.entries(overrides)) {
      if (u.includes(needle)) return reply(r.status, r.body);
    }
    if (u === AUTH_URL) return reply(200, { token: "tok-123" });
    if (u === SCHEMA_URL) return reply(200, fixture);
    if (u === ME_URL) return reply(200, { username: "admin", is_superuser: true, roles: ["staff"] });
    return reply(404, { detail: `unexpected call ${u}` });
  });
}

function render() {
  const host = document.createElement("div");
  const toastHost = document.createElement("div");
  document.body.append(host, toastHost);
  flushSync(() => {
    mounted.push({ instance: mount(Login, { target: host, props: {} }) });
    mounted.push({ instance: mount(Toaster, { target: toastHost }) });
  });
  return { host, toastHost };
}

const field = (host: HTMLElement, id: string) => host.querySelector<HTMLInputElement>(`#${id}`)!;

function fill(host: HTMLElement, vals: { username?: string; password?: string; api?: string }) {
  for (const [id, key] of [["username", "username"], ["password", "password"], ["api", "api"]] as const) {
    const value = vals[key];
    if (value === undefined) continue;
    const el = field(host, id);
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  flushSync(() => {});
}

/** The API URL field is a collapsed disclosure (Login.svelte): hidden at
 *  mount, revealed only by the "Advanced — API URL" toggle. The prefill
 *  $effect runs while collapsed, so the value is ready when revealed. */
function showAdvanced(host: HTMLElement) {
  (host.querySelector('button[aria-expanded]') as HTMLButtonElement).click();
  flushSync(() => {});
}

const submitForm = (host: HTMLElement) => {
  host.querySelector("form")!.dispatchEvent(new SubmitEvent("submit", { cancelable: true }));
};

const urls = () => mockFetch.mock.calls.map((c) => String(c[0]));
const initFor = (url: string) => mockFetch.mock.calls.find((c) => String(c[0]) === url)?.[1] as any;

describe("mounted login page — the bytes on the wire", () => {
  it("posts credentials to the documented authPath and stores only the token", async () => {
    serve();
    app.update((a) => ({
      ...a,
      booted: true,
      config: { apiUrl: "http://configured.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));
    const { host, toastHost } = render();

    // the settings field is collapsed — nothing of it on the first screen
    expect(field(host, "api")).toBeNull();
    showAdvanced(host);
    // the one settings field prefills from config
    await vi.waitFor(() => expect(field(host, "api").value).toBe("http://configured.test"));

    fill(host, { api: "  http://api.test/  ", username: "admin", password: "admin123" });
    submitForm(host);

    await vi.waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThanOrEqual(3));
    expect(urls()).toEqual([AUTH_URL, SCHEMA_URL, ME_URL]);

    const authInit = initFor(AUTH_URL);
    expect(authInit.method).toBe("POST");
    expect(JSON.parse(authInit.body)).toEqual({ username: "admin", password: "admin123" });
    expect(authInit.headers["Content-Type"]).toBe("application/json");
    // a login request has no token to send
    expect(authInit.headers.Authorization).toBeUndefined();
    // credentials never ride in a URL — the password travels ONLY in the
    // POST body of the auth call
    expect(urls().every((u) => !u.includes("admin123"))).toBe(true);

    // the returned token is what every later call carries
    expect(initFor(SCHEMA_URL).headers.Authorization).toBe("Token tok-123");
    expect(initFor(ME_URL).headers.Authorization).toBe("Token tok-123");

    const a = get(app);
    expect(a.token).toBe("tok-123");
    expect(a.username).toBe("admin");
    // whitespace is trimmed; a trailing slash survives because api.ts's
    // baseUrl() strips it per request — the stored override stays verbatim
    expect(a.apiUrlOverride).toBe("http://api.test/");
    expect(localStorage.getItem("dad.token")).toBe("tok-123");
    expect(localStorage.getItem("dad.username")).toBe("admin");
    expect(localStorage.getItem("dad.apiUrl")).toBe("http://api.test/");

    // the schema arrived through the config's schemaPath and went through
    // normalizeOpenAPI — byId/listPath only exist on the normalized shape,
    // so this fails if the raw document were ever stored instead
    expect(get(app).schema!.byId["orders"]!.listPath).toBe("/api/orders/");
    // and the claims land from the DOCUMENTED me path, parsed
    expect(get(claims)).toEqual({ username: "admin", isStaff: false, isSuperuser: true, roles: ["staff"] });

    await vi.waitFor(() => expect(toastHost.textContent).toContain("Welcome, admin!"));
    expect(get(app).backendDown).toBe(false);
    // navigate("#/") ran — the router's own hash moved (the mounted page
    // keeps its markup here because the SHELL, not Login, swaps views),
    // and that hash resolves to a real page, not a dead end. happy-dom
    // assigns location.hash but never fires hashchange, so dispatch it.
    expect(location.hash).toBe("#/");
    flushSync(() => window.dispatchEvent(new HashChangeEvent("hashchange")));
    expect(get(route).path).toBe("/");
    expect(get(route).kind).toBe("page");
  });

  it("an override beats the config URL — that is what the login screen is for", async () => {
    serve();
    app.update((a) => ({
      ...a,
      config: { apiUrl: "http://configured.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
      apiUrlOverride: "http://api.test",
    }));
    const { host } = render();
    showAdvanced(host);
    await vi.waitFor(() => expect(field(host, "api").value).toBe("http://api.test"));
    fill(host, { username: "admin", password: "admin123" });
    submitForm(host);
    await vi.waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThanOrEqual(1));
    expect(urls()[0]).toBe(AUTH_URL);
    expect(urls()[0]).not.toContain("configured.test");
  });

  it("the API URL field is a collapsed disclosure — hidden until asked for", async () => {
    serve();
    app.update((a) => ({
      ...a,
      booted: true,
      config: { apiUrl: "http://configured.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));
    const { host } = render();

    // nothing of the settings field leaks into the first screen — not the
    // input, not its helper text
    expect(field(host, "api")).toBeNull();
    expect(host.textContent).not.toContain("DRF + drf-spectacular");
    expect(host.textContent).not.toContain("demo-backend");
    // the toggle starts collapsed (aria-expanded false), click flips it true
    const toggle = host.querySelector('button[aria-expanded]') as HTMLButtonElement;
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    // yet the prefill $effect ran while hidden: the revealed field is ready
    showAdvanced(host);
    await vi.waitFor(() => expect(field(host, "api").value).toBe("http://configured.test"));
    expect(host.textContent).toContain("DRF + drf-spectacular backend (token auth)");
    expect((host.querySelector('button[aria-expanded]') as HTMLButtonElement).getAttribute("aria-expanded")).toBe("true");

    // and the toggle collapses it back
    showAdvanced(host);
    expect(field(host, "api")).toBeNull();
    expect((host.querySelector('button[aria-expanded]') as HTMLButtonElement).getAttribute("aria-expanded")).toBe("false");
  });

  it("submitting without ever opening the disclosure still uses the config apiUrl", async () => {
    // the prefill $effect runs while the field is hidden, so a user who never
    // touches the Advanced toggle signs in against the configured API
    serve();
    app.update((a) => ({
      ...a,
      booted: true,
      config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));
    const { host } = render();

    // never revealed — the field is absent and the toggle still reads collapsed
    expect(field(host, "api")).toBeNull();
    expect((host.querySelector('button[aria-expanded]') as HTMLButtonElement).getAttribute("aria-expanded")).toBe("false");

    fill(host, { username: "admin", password: "admin123" });
    submitForm(host);
    await vi.waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThanOrEqual(1));
    // the hidden-but-prefilled apiUrl carried the POST to the config's URL
    expect(urls()[0]).toBe(AUTH_URL);
    expect(localStorage.getItem("dad.apiUrl")).toBe("http://api.test");
  });

  it("empty credentials answer inline text with ZERO requests", async () => {
    serve();
    const { host } = render();
    submitForm(host);
    flushSync(() => {});
    expect(host.textContent).toContain("Enter username and password.");
    expect(mockFetch.mock.calls.length).toBe(0);
    expect(get(app).token).toBe("");
  });

  it("a 400 from the token endpoint reads as invalid credentials, no token kept", async () => {
    serve({ "/api/auth/token/": { status: 400, body: { non_field_errors: ["Unable to log in"] } } });
    const { host, toastHost } = render();
    showAdvanced(host);
    fill(host, { api: "http://api.test", username: "admin", password: "wrong" });
    submitForm(host);
    await vi.waitFor(() => expect(host.textContent).toContain("Invalid credentials"));
    expect(get(app).token).toBe("");
    expect(localStorage.getItem("dad.token")).toBeNull();
    expect(get(app).backendDown).toBe(false);
    expect(toastHost.textContent).toBe("");
    // the form is usable again (the .btn is the Sign in button — the
    // disclosure toggle is a plain type=button and is never disabled)
    expect((host.querySelector("button.btn") as HTMLButtonElement).disabled).toBe(false);
    expect(mockFetch.mock.calls.length).toBe(1); // no schema fetch followed
  });

  it("an unreachable backend says so, raises the banner flag and stays on the page", async () => {
    mockFetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const { host } = render();
    showAdvanced(host);
    fill(host, { api: "http://down.test", username: "admin", password: "admin123" });
    submitForm(host);
    await vi.waitFor(() => expect(host.textContent).toContain("Backend unreachable at http://down.test"));
    expect(get(app).backendDown).toBe(true);
    expect(get(app).token).toBe("");
  });

  it("any other failure still reaches the user, secret-free", async () => {
    // a sentinel password: the shipped hint text literally prints
    // "admin / admin123" (Login.svelte:110), so only a value unique to this
    // test can prove the credential never reaches the rendered DOM
    serve({
      "/api/auth/token/": {
        status: 500,
        body: { detail: "boom", password: "sup3r-sentinel" },
      },
    });
    const { host, toastHost } = render();
    showAdvanced(host);
    fill(host, { api: "http://api.test", username: "admin", password: "sup3r-sentinel" });
    submitForm(host);
    await vi.waitFor(() => expect(toastHost.textContent).toContain("API 500"));
    // An object detail is NOT spliced into the toast (only a string detail
    // is, stores.ts:186-187) and redactSecrets has already masked the
    // password inside err.detail — so the credential can reach the user
    // through neither channel.
    expect(toastHost.textContent).not.toContain("sup3r-sentinel");
    expect(host.textContent).not.toContain("sup3r-sentinel");
    expect(urls().some((u) => u.includes("sup3r-sentinel"))).toBe(false);
    expect(get(app).token).toBe("");
  });

  it("shows the brand logo and swallows a double submit while the request is open", async () => {
    // the two branches nothing else reached: Login.svelte:33 (busy guard)
    // and the brand logo at :69 — a rebranded client must show ITS mark on
    // the gate the first user ever sees
    app.update((a) => ({
      ...a,
      booted: true,
      brand: { ...a.brand, logo: "data:image/png;base64,LOGO", tagline: "Ops console" },
      config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));
    let release: (() => void) | undefined;
    mockFetch.mockImplementation((url: string) => {
      const u = String(url);
      if (u === AUTH_URL) {
        return new Promise((r) => {
          release = () => r(reply(200, { token: "tok-123" }));
        });
      }
      if (u === SCHEMA_URL) return reply(200, fixture);
      return reply(200, { username: "admin", roles: [] });
    });
    const { host } = render();
    showAdvanced(host);

    expect(field(host, "api").value).toBe("http://api.test");
    const img = host.querySelector("img");
    expect(img?.getAttribute("src")).toBe("data:image/png;base64,LOGO");
    expect(host.textContent).toContain("Ops console");

    fill(host, { username: "admin", password: "admin123" });
    submitForm(host);
    submitForm(host); // the button is disabled, but Enter/programmatic re-submit must not double-post
    flushSync(() => {});
    expect(mockFetch.mock.calls.filter((c) => String(c[0]) === AUTH_URL).length).toBe(1);
    expect((field(host, "username").closest("form")!.querySelector("button.btn") as HTMLButtonElement).disabled).toBe(true);

    release!();
    await vi.waitFor(() => expect(get(app).token).toBe("tok-123"));
    expect(mockFetch.mock.calls.filter((c) => String(c[0]) === AUTH_URL).length).toBe(1);
    await vi.waitFor(() =>
      expect((host.querySelector("form")!.querySelector("button.btn") as HTMLButtonElement).disabled).toBe(false),
    );
  });
});
