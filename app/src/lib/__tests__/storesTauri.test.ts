/** The stores' remaining Tauri + boot seams, proven at the module boundary.
 *  Everything here used to run ZERO tests: `saveAiSettings` / `loadAiSettings`
 *  (the AI key crossing the keyring boundary), `applyBrand`'s native window
 *  title, and `initApp`'s config/brand boot fetches. chatMount.test.ts sets
 *  the `ai` store BY HAND, so the shipped save path — the trim, the keyring
 *  tuple, and what an emptied key field does — was never executed.
 *
 *  Nothing from this module is mocked: only the @tauri-apps/api entry points
 *  and fetch are, and every assertion is a tuple, a URL or a byte. Tauri mode
 *  is a marker on the REAL happy-dom window (never a replacement: document and
 *  localStorage must stay live), so `vi.resetModules()` + `vi.doMock` + a
 *  dynamic import gives each case a fresh stores/secrets pair — the same
 *  harness trick secrets.test.ts uses for its one-time webWarned.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import type { Brand } from "../types";

const invoke = vi.fn();
const setTitle = vi.fn();
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const BRAND: Brand = {
  appName: "Windowcraft",
  tagline: "",
  colors: { primary: "#0f8b6c" },
  radius: "0.5rem",
  font: "Inter",
};

function tauriMode(on: boolean) {
  if (on) (window as any).__TAURI_INTERNALS__ = {};
  else delete (window as any).__TAURI_INTERNALS__;
}

/** Fresh stores + fresh secrets, both wired to the mocked tauri entry points. */
async function freshStores(): Promise<typeof import("../stores")> {
  vi.resetModules();
  return import("../stores");
}

function jsonReply(data: any) {
  const text = JSON.stringify(data);
  return { ok: true, status: 200, json: async () => data, text: async () => text };
}

function localStorageContains(needle: string): boolean {
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)!;
    if (k.includes(needle) || String(localStorage.getItem(k)).includes(needle)) return true;
  }
  return false;
}

beforeEach(() => {
  invoke.mockReset();
  setTitle.mockReset();
  mockFetch.mockReset();
  localStorage.clear();
  vi.resetModules();
  vi.doMock("@tauri-apps/api/core", () => ({ invoke }));
  vi.doMock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ setTitle }) }));
});

afterEach(() => {
  tauriMode(false);
  vi.doUnmock("@tauri-apps/api/core");
  vi.doUnmock("@tauri-apps/api/window");
  document.head.innerHTML = "";
  document.title = "";
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("saveAiSettings — the key crosses the keyring boundary", () => {
  it("trims all three fields, persists base/model as bytes and the key ONLY as an invoke tuple", async () => {
    tauriMode(true);
    invoke.mockResolvedValue(undefined);
    const { ai, saveAiSettings } = await freshStores();

    await saveAiSettings("  https://api.groq.com/openai/v1  ", "  sk-sentinel-9x  ", "  llama-3.1  ");

    expect(get(ai)).toEqual({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "sk-sentinel-9x",
      model: "llama-3.1",
    });
    expect(localStorage.getItem("dad.ai.baseUrl")).toBe("https://api.groq.com/openai/v1");
    expect(localStorage.getItem("dad.ai.model")).toBe("llama-3.1");
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke).toHaveBeenCalledWith("save_secret", {
      service: "admincraft",
      key: "ai.apiKey",
      value: "sk-sentinel-9x",
    });
    // SECRET LAW at wire level: under Tauri the key must not exist anywhere in
    // browser storage (the "  " in the needle proves the trim ran on the value
    // that crossed the boundary, not only on the store copy).
    expect(localStorage.getItem("dad.secret.ai.apiKey")).toBeNull();
    expect(localStorageContains("sk-sentinel-9x")).toBe(false);
  });

  it("an emptied key field DELETES the stored secret — it cannot resurrect itself on next boot", async () => {
    tauriMode(true);
    invoke.mockImplementation((cmd: string) => {
      if (cmd === "load_secret") return Promise.resolve(null); // Rust NoEntry = Ok(None)
      return Promise.resolve(undefined);
    });
    const { ai, loadAiSettings, saveAiSettings } = await freshStores();

    await saveAiSettings("https://api.groq.com/v1", "sk-sentinel-9x", "llama-3.1");
    invoke.mockClear();

    // The settings form hydrates from the store (ChatPanel.svelte:33), so a
    // user who clears the field and saves has asked to forget the key.
    await saveAiSettings("https://api.groq.com/v1", "   ", "llama-3.1");

    expect(get(ai).apiKey).toBe("");
    expect(invoke).not.toHaveBeenCalledWith("save_secret", expect.anything());
    expect(invoke).toHaveBeenCalledWith("delete_secret", {
      service: "admincraft",
      key: "ai.apiKey",
    });

    // the proof that matters to the user: reboot does not bring the key back
    await loadAiSettings();
    expect(get(ai).apiKey).toBe("");
  });

  it("web mode falls back to localStorage for the key and warns once", async () => {
    tauriMode(false);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { ai, loadAiSettings, saveAiSettings } = await freshStores();

    await saveAiSettings("http://localhost:11435/v1", "sk-web", "qwen");
    expect(invoke).not.toHaveBeenCalled();
    expect(localStorage.getItem("dad.secret.ai.apiKey")).toBe("sk-web");

    await loadAiSettings();
    expect(get(ai)).toEqual({
      baseUrl: "http://localhost:11435/v1",
      apiKey: "sk-web",
      model: "qwen",
    });
    // save + load each hit the fallback: the accepted-P2 warning is one-time
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("SECURITY WARNING"));

    // clearing in web mode removes the plaintext copy too
    await saveAiSettings("http://localhost:11435/v1", "", "qwen");
    expect(localStorage.getItem("dad.secret.ai.apiKey")).toBeNull();
  });

  it("loadAiSettings reads base/model from storage and the key from the keyring; an unavailable keychain is an empty key, never a throw", async () => {
    tauriMode(true);
    localStorage.setItem("dad.ai.baseUrl", "https://groq.test/v1");
    localStorage.setItem("dad.ai.model", "mixtral");
    invoke.mockResolvedValue("sk-from-keychain");
    const { ai, loadAiSettings } = await freshStores();

    await loadAiSettings();
    expect(get(ai)).toEqual({
      baseUrl: "https://groq.test/v1",
      apiKey: "sk-from-keychain",
      model: "mixtral",
    });
    expect(invoke).toHaveBeenCalledWith("load_secret", { service: "admincraft", key: "ai.apiKey" });

    // a machine with no keychain at all must still boot the chat panel
    invoke.mockRejectedValue(new Error("keychain unavailable"));
    await expect(loadAiSettings()).resolves.toBeUndefined();
    expect(get(ai).apiKey).toBe("");
  });
});

describe("applyBrand — the native window title follows the live brand", () => {
  it("under Tauri: setTitle receives the appName, and tab title + favicon + CSS ride synchronously", async () => {
    tauriMode(true);
    setTitle.mockResolvedValue(undefined);
    const link = document.createElement("link");
    link.rel = "icon";
    link.href = "/old.ico";
    document.head.appendChild(link);
    const { app, applyBrand } = await freshStores();

    applyBrand({ ...BRAND, favicon: "http://api.test/favicon.ico" });

    // the DOM half must NOT wait on the async title call (first paint)
    expect(document.title).toBe("Windowcraft");
    expect(document.querySelector<HTMLLinkElement>("link[rel='icon']")!.href).toBe(
      "http://api.test/favicon.ico",
    );
    expect(document.getElementById("brand-runtime")!.textContent).toContain("--brand-primary");
    expect(get(app).brand.appName).toBe("Windowcraft");
    await vi.waitFor(() => expect(setTitle).toHaveBeenCalledWith("Windowcraft"));
  });

  it("a window module that rejects is swallowed: the brand still lands everywhere else", async () => {
    tauriMode(true);
    setTitle.mockRejectedValue(new Error("core:window:allow-set-title not in capability"));
    const { applyBrand } = await freshStores();

    expect(() => applyBrand(BRAND)).not.toThrow();
    await vi.waitFor(() => expect(setTitle).toHaveBeenCalled());
    expect(document.title).toBe("Windowcraft");
    expect(document.getElementById("brand-runtime")).not.toBeNull();
  });

  it("web mode never touches the window API", async () => {
    tauriMode(false);
    const { applyBrand } = await freshStores();

    applyBrand(BRAND);
    // a macrotask boundary drains the whole dynamic-import chain of the
    // fire-and-forget title call — the Tauri case above proves it lands
    // within microtasks, so reaching here with zero calls is the guard,
    // not a race (an earlier version awaited two microtasks and proved
    // nothing: the same mutant survived).
    await new Promise((r) => setTimeout(r, 50));
    expect(setTitle).not.toHaveBeenCalled();
    expect(invoke).not.toHaveBeenCalled();
    expect(document.title).toBe("Windowcraft");
  });
});

describe("initApp — boot: bundled files first, server brand wins", () => {
  const reply = (status: number, data: any) => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  });

  function urlsSeen(): string[] {
    return mockFetch.mock.calls.map((c) => String(c[0]));
  }

  it("boots config.json + brand.json, applies the static brand, then overrides with the server brand over the DOCUMENTED path with resolved assets", async () => {
    tauriMode(false);
    setTitle.mockResolvedValue(undefined);
    mockFetch
      .mockResolvedValueOnce(
        reply(200, { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" }),
      )
      .mockResolvedValueOnce(
        reply(200, { appName: "Static", tagline: "t", colors: {}, radius: "0", font: "Inter" }),
      )
      .mockResolvedValueOnce(
        reply(200, {
          brand: { appName: "Servercraft", colors: { primary: "#123456" }, logo: "/admincraft/branding/asset/logo.png" },
          rev: 3,
        }),
      );
    const { app, initApp } = await freshStores();

    await initApp();

    expect(urlsSeen()).toEqual([
      "config.json",
      "brand.json",
      "http://api.test/admincraft/branding/",
    ]);
    const a = get(app);
    expect(a.booted).toBe(true);
    expect(a.config?.apiUrl).toBe("http://api.test");
    // the server identity replaced the bundled one, and its relative asset
    // was resolved against apiUrl rather than left as a bare path
    expect(a.brand.appName).toBe("Servercraft");
    expect(a.brand.logo).toBe("http://api.test/admincraft/branding/asset/logo.png");
    expect(document.title).toBe("Servercraft");
  });

  it("a backend without the plugin keeps the static brand silently — one read, no toast, banner or throw", async () => {
    tauriMode(false);
    mockFetch
      .mockResolvedValueOnce(reply(200, { apiUrl: "http://plain.test" }))
      .mockResolvedValueOnce(reply(404, { detail: "Not Found" })) // no bundled brand.json
      .mockResolvedValueOnce(reply(404, { detail: "Not Found" })); // plain DRF: no branding API
    const { app, initApp, toasts } = await freshStores();

    await initApp();

    const a = get(app);
    expect(a.booted).toBe(true);
    expect(a.brand.appName).toBe("Admincraft"); // the shipped neutral default
    expect(get(toasts)).toEqual([]);
    expect(a.backendDown).toBe(false); // banner belongs to the schema flow, not boot
    // exactly one probe of the documented plugin path — a 404 is never chased
    // with guesses, and the static brand is what renders
    expect(urlsSeen()).toEqual([
      "config.json",
      "brand.json",
      "http://plain.test/admincraft/branding/",
    ]);
  });

  it("with no config.json at all the boot stays local — zero requests beyond the two bundled files", async () => {
    tauriMode(false);
    mockFetch.mockResolvedValueOnce(reply(404, null)).mockResolvedValueOnce(reply(404, null));
    const { app, initApp } = await freshStores();

    await initApp();

    expect(get(app).config).toBeNull();
    expect(urlsSeen()).toEqual(["config.json", "brand.json"]);
  });

  it("a backend that is unreachable at boot still boots: fetch rejects, the static brand stays, nothing throws", async () => {
    tauriMode(false);
    mockFetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const { app, initApp, toasts } = await freshStores();

    await expect(initApp()).resolves.toBeUndefined();

    const a = get(app);
    expect(a.booted).toBe(true);
    expect(a.brand.appName).toBe("Admincraft");
    expect(a.config).toBeNull();
    expect(get(toasts)).toEqual([]);
  });

  it("an apiUrlOverride from the login screen wins over the bundled config for the branding read", async () => {
    tauriMode(false);
    localStorage.setItem("dad.apiUrl", "http://second.test");
    mockFetch
      .mockResolvedValueOnce(reply(200, { apiUrl: "http://first.test" }))
      .mockResolvedValueOnce(reply(404, null))
      .mockResolvedValueOnce(reply(200, { brand: { appName: "Second" } }));
    const { app, initApp } = await freshStores();
    app.update((s) => ({ ...s, apiUrlOverride: "http://second.test" }));

    await initApp();

    expect(urlsSeen()[2]).toBe("http://second.test/admincraft/branding/");
    expect(get(app).brand.appName).toBe("Second");
  });
});

describe("loadSchema — the no-claims degradation (FR-R007)", () => {
  /** The positive leg (claims read at the DOCUMENTED mePath) is pinned by
   *  loginMount.test.ts. The OTHER half — a plain DRF document that carries
   *  no read-only /me/ — is the one that keeps a normal backend usable, and
   *  it ran zero tests: the else branch in stores.ts:170. */
  it("a document with no mePath leaves claims null and fires NO roles probe", async () => {
    tauriMode(false);
    const doc = {
      openapi: "3.0.3",
      paths: { "/api/orders/": { get: {}, post: {} }, "/api/audit/": { get: {}, post: {} } },
      components: { schemas: {} },
    };
    mockFetch.mockResolvedValue(jsonReply(doc));
    const { app, claims, loadSchema } = await freshStores();
    app.update((s) => ({
      ...s,
      token: "tok-1",
      config: { apiUrl: "http://plain.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));

    await loadSchema();

    expect(mockFetch.mock.calls.map((c) => String(c[0]))).toEqual([
      "http://plain.test/api/schema/",
    ]);
    const a = get(app);
    expect(a.schema).not.toBeNull();
    expect(a.schema!.mePath).toBeUndefined();
    expect(get(claims)).toBeNull(); // null = no filtering anywhere
    expect(a.schemaLoading).toBe(false);
  });

  it("a documented mePath that answers a non-claims body degrades to no claims, never an error", async () => {
    tauriMode(false);
    const doc = {
      openapi: "3.0.3",
      paths: { "/api/orders/": { get: {}, post: {} }, "/api/me/": { get: {} } },
      components: { schemas: {} },
    };
    mockFetch
      .mockResolvedValueOnce(jsonReply(doc))
      .mockResolvedValueOnce(jsonReply([1, 2, 3]));
    const { app, claims, loadSchema } = await freshStores();
    app.update((s) => ({
      ...s,
      token: "tok-1",
      config: { apiUrl: "http://plain.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));

    await loadSchema();

    // the read went exactly where the DOCUMENT pointed
    expect(mockFetch.mock.calls.map((c) => String(c[0]))).toEqual([
      "http://plain.test/api/schema/",
      "http://plain.test/api/me/",
    ]);
    expect(get(claims)).toBeNull();
  });
});

describe("loadSchema — the in-flight guard and the anonymous read", () => {
  const doc = {
    openapi: "3.0.3",
    paths: { "/api/orders/": { get: {}, post: {} } },
    components: { schemas: {} },
  };

  it("a second load while one is in flight answers immediately and fires NO extra request", async () => {
    tauriMode(false);
    let release: (v: any) => void = () => {};
    mockFetch.mockImplementation(
      () => new Promise((resolve) => { release = resolve; }),
    );
    const { app, loadSchema } = await freshStores();
    app.update((s) => ({
      ...s,
      token: "tok-1",
      config: { apiUrl: "http://plain.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));

    const first = loadSchema();
    // let the first call reach its await and set the flag
    await vi.waitFor(() => expect(get(app).schemaLoading).toBe(true));
    await loadSchema(); // the sidebar + a widget can both ask at once
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(get(app).schemaLoading).toBe(true); // the second call must not clear it

    release(jsonReply(doc));
    await first;
    expect(get(app).schemaLoading).toBe(false);
    expect(get(app).schema).not.toBeNull();
  });

  it("with no token stored the schema read still goes out, carrying NO Authorization header", async () => {
    tauriMode(false);
    mockFetch.mockResolvedValue(jsonReply(doc));
    const { app, loadSchema } = await freshStores();
    app.update((s) => ({
      ...s,
      token: "",
      config: { apiUrl: "http://plain.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));

    await loadSchema();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(String(url)).toBe("http://plain.test/api/schema/");
    expect(JSON.stringify(init)).not.toContain("Authorization");
    expect(get(app).schema?.models.map((m) => m.id)).toEqual(["orders"]);
  });
});
