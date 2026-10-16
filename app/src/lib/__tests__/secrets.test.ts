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
