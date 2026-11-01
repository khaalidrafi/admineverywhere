/** ORIGIN LAW — the saved API override may only ever be an origin.
 *
 *  Ported upstream from the Freshorama client hardening (2026-11-02,
 *  ai/authz-1): a stale override like `http://host/dead/subpath` pointed
 *  every fetch through a path no backend ever served (the /cool-admin-era
 *  404 class — the app looked "down" while the API was fine). The law:
 *  path/query/hash are dropped WHOLE (never trimmed), non-http(s) schemes
 *  are dropped, and a dropped override falls back to the URL the bundle
 *  shipped with. Boot self-heals: the stale localStorage copy is removed,
 *  so the poison cannot outlive the process.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { app, effectiveConfig, initApp, sanitizeApiOverride } from "../stores";

const BASE_CFG = {
  apiUrl: "http://bundled.test",
  authPath: "/api/auth/token/",
  schemaPath: "/api/schema/",
};

describe("sanitizeApiOverride — the ORIGIN LAW", () => {
  it("keeps a bare origin", () => {
    expect(sanitizeApiOverride("http://api.test")).toBe("http://api.test");
  });

  it("keeps an origin with an explicit port", () => {
    expect(sanitizeApiOverride("http://api.test:8000")).toBe("http://api.test:8000");
  });

  it("keeps https and canonicalizes away the empty path", () => {
    expect(sanitizeApiOverride("https://api.test/")).toBe("https://api.test");
  });

  it("trims surrounding whitespace", () => {
    expect(sanitizeApiOverride("  http://api.test  ")).toBe("http://api.test");
  });

  it("drops a path-bearing override wholesale — the dead-surface class", () => {
    expect(sanitizeApiOverride("http://api.test/dead/subpath")).toBe("");
  });

  it("drops query and hash carriers", () => {
    expect(sanitizeApiOverride("http://api.test/?next=1")).toBe("");
    expect(sanitizeApiOverride("http://api.test/#frag")).toBe("");
  });

  it("drops non-http(s) schemes", () => {
    expect(sanitizeApiOverride("ftp://api.test")).toBe("");
    expect(sanitizeApiOverride("file:///etc/passwd")).toBe("");
  });

  it("drops garbage and empty strings", () => {
    expect(sanitizeApiOverride("not a url")).toBe("");
    expect(sanitizeApiOverride("http://")).toBe("");
    expect(sanitizeApiOverride("")).toBe("");
  });
});

describe("effectiveConfig — a dropped override falls back to the bundle", () => {
  beforeEach(() => {
    app.update((a) => ({ ...a, config: BASE_CFG, apiUrlOverride: "" }));
  });

  afterEach(() => {
    app.update((a) => ({ ...a, config: null, apiUrlOverride: "" }));
  });

  it("a valid override wins over the bundle", () => {
    app.update((a) => ({ ...a, apiUrlOverride: "http://override.test" }));
    expect(effectiveConfig().apiUrl).toBe("http://override.test");
  });

  it("a path-bearing override never reaches a fetch — bundled wins", () => {
    app.update((a) => ({ ...a, apiUrlOverride: "http://override.test/dead" }));
    expect(effectiveConfig().apiUrl).toBe("http://bundled.test");
  });

  it("no override uses the bundled apiUrl", () => {
    expect(effectiveConfig().apiUrl).toBe("http://bundled.test");
  });
});

describe("boot self-heal — the stale override cannot outlive the process", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem("dad.apiUrl");
    app.update((a) => ({ ...a, config: null, apiUrlOverride: "" }));
  });

  it("a stale path-bearing override is cleared from store and localStorage", async () => {
    localStorage.setItem("dad.apiUrl", "http://host.test/dead/path");
    app.update((a) => ({ ...a, config: BASE_CFG, apiUrlOverride: "http://host.test/dead/path" }));
    await initApp();
    expect(localStorage.getItem("dad.apiUrl")).toBeNull();
    expect(get(app).apiUrlOverride).toBe("");
  });

  it("a valid override survives boot untouched", async () => {
    localStorage.setItem("dad.apiUrl", "http://override.test");
    app.update((a) => ({ ...a, config: BASE_CFG, apiUrlOverride: "http://override.test" }));
    await initApp();
    expect(localStorage.getItem("dad.apiUrl")).toBe("http://override.test");
    expect(get(app).apiUrlOverride).toBe("http://override.test");
  });
});
