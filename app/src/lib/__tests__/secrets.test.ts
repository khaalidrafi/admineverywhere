/** secrets.ts tests — web fallback warning, Tauri detection. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { isTauri, isWebStorage, loadSecret, saveSecret, deleteSecret } from "../secrets";

describe("Tauri detection", () => {
  it("detects Tauri via __TAURI_INTERNALS__", () => {
    const original = (globalThis as any).window;
    (globalThis as any).window = { __TAURI_INTERNALS__: {} };
    expect(isTauri()).toBe(true);
    expect(isWebStorage()).toBe(false);
    (globalThis as any).window = original;
  });

  it("returns false in plain browser", () => {
    const original = (globalThis as any).window;
    (globalThis as any).window = {};
    expect(isTauri()).toBe(false);
    expect(isWebStorage()).toBe(true);
    (globalThis as any).window = original;
  });
});

describe("web fallback warning", () => {
  let warnSpy: any;
  
  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    (globalThis as any).window = {}; // no __TAURI_INTERNALS__
  });

  afterEach(() => {
    warnSpy.mockRestore();
    (globalThis as any).window = undefined;
  });

  it("warns once on first localStorage fallback", async () => {
    await saveSecret("test-key", "test-value");
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("SECURITY WARNING: Tauri keyring not available")
    );
  });

  it("does not warn again on subsequent calls", async () => {
    await saveSecret("key1", "val1");
    warnSpy.mockClear();
    await saveSecret("key2", "val2");
    await loadSecret("key1");
    await deleteSecret("key1");
    expect(warnSpy).not.toHaveBeenCalled();
  });
});

describe("localStorage operations", () => {
  beforeEach(() => {
    (globalThis as any).window = { localStorage: new Map() };
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    (globalThis as any).window = undefined;
  });

  it("saves and loads secrets", async () => {
    await saveSecret("api-key", "sk-test-123");
    const loaded = await loadSecret("api-key");
    expect(loaded).toBe("sk-test-123");
  });

  it("returns null for missing keys", async () => {
    const loaded = await loadSecret("nonexistent");
    expect(loaded).toBeNull();
  });

  it("deletes secrets", async () => {
    await saveSecret("temp", "value");
    await deleteSecret("temp");
    const loaded = await loadSecret("temp");
    expect(loaded).toBeNull();
  });
});

/** The Tauri branches (secrets.ts:32-35, 42-48, 55-60) ran ZERO tests until
 *  now: the web fallback covered 3 of 4 paths and the coverage sweep named
 *  the rest. Those lines are the packaged product's whole secret store, and
 *  the invoke() argument names are a BOUNDARY contract with the Rust side —
 *  src-tauri/src/lib.rs:10 keeps `DEFAULT_SERVICE: "admineverywhere"` and the
 *  commands take (service, key, value). A renamed or dropped argument fails
 *  silently on the Rust signature or buries the key under a different
 *  keychain bucket, invisible in web mode. Each test re-imports the module
 *  fresh so `webWarned` and the dynamic @tauri-apps/api/core mock cannot leak
 *  between cases or into the web-fallback describes above.
 */
describe("Tauri keyring branches — the invoke() boundary contract", () => {
  const invoke = vi.fn();

  beforeEach(() => {
    vi.resetModules();
    invoke.mockReset();
    vi.doMock("@tauri-apps/api/core", () => ({ invoke }));
    (globalThis as any).window = { __TAURI_INTERNALS__: {} };
  });

  afterEach(() => {
    vi.doUnmock("@tauri-apps/api/core");
    (globalThis as any).window = undefined;
  });

  const fresh = () => import("../secrets");

  it("save_secret rides service/key/value with the shipped SERVICE name", async () => {
    invoke.mockResolvedValue(undefined);
    const { saveSecret, SERVICE } = await fresh();
    await saveSecret("ai.apiKey", "sk-test");
    expect(SERVICE).toBe("admineverywhere");
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke.mock.calls[0]).toEqual([
      "save_secret",
      { service: "admineverywhere", key: "ai.apiKey", value: "sk-test" },
    ]);
    // the Tauri path never touches localStorage
    expect(localStorage.getItem("dad.secret.ai.apiKey")).toBeNull();
  });

  it("load_secret returns the value and reads nothing when the keychain throws", async () => {
    invoke.mockResolvedValue("sk-from-keychain");
    const { loadSecret } = await fresh();
    expect(await loadSecret("ai.apiKey")).toBe("sk-from-keychain");
    expect(invoke.mock.calls[0]).toEqual([
      "load_secret",
      { service: "admineverywhere", key: "ai.apiKey" },
    ]);

    // Rust answers NoEntry as Ok(None); a keychain that is unavailable at all
    // arrives as a rejected invoke — both must degrade to null, never a throw
    // that would kill loadAiSettings and leave the chat panel unconfigured.
    invoke.mockRejectedValue(new Error("keychain unavailable"));
    expect(await loadSecret("ai.apiKey")).toBeNull();
  });

  it("delete_secret swallows an already-gone entry and still returns", async () => {
    invoke.mockResolvedValue(undefined);
    const { deleteSecret } = await fresh();
    await deleteSecret("ai.apiKey");
    expect(invoke.mock.calls[0]).toEqual([
      "delete_secret",
      { service: "admineverywhere", key: "ai.apiKey" },
    ]);

    invoke.mockRejectedValue(new Error("NoEntry"));
    await expect(deleteSecret("ai.apiKey")).resolves.toBeUndefined();
    expect(invoke).toHaveBeenCalledTimes(2);
  });

  it("the web-fallback warning stays a one-time warning across all three ops", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    (globalThis as any).window = {};
    vi.resetModules();
    vi.doUnmock("@tauri-apps/api/core");
    const { saveSecret, loadSecret, deleteSecret } = await fresh();
    await saveSecret("k", "v");
    await loadSecret("k");
    await deleteSecret("k");
    expect(warnSpy).toHaveBeenCalledTimes(1);
    warnSpy.mockRestore();
  });
});
