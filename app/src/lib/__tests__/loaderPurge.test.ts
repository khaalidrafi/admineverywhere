/** Loader purge (owner order, deep branding): the ONLY loader left in the
 *  app is the brand intro on the splash. The busy icons on the Login and
 *  RecordForm submit buttons are gone — the disabled state and the button
 *  text carry the busy signal instead. Mounted for real, held mid-request,
 *  so the assertions run against the BUSY render, not just the idle one.
 *  (ChatPanel's typing cursor and .skeleton content placeholders are
 *  deliberately out of scope — content loaders, not app loaders.)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import Login from "../../pages/Login.svelte";
import RecordFormHarness from "./fixtures/RecordFormHarness.svelte";
import { recordFormHarnessProps } from "./fixtures/harnessProps";
import { normalizeOpenAPI } from "../openapi";
import { app, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const LIVE = normalizeOpenAPI(fixture);

const ROW7 = {
  id: 7, name: "Cold Brew Kit", description: "Glass carafe", price: "24.90",
  stock: 4, is_active: true, launch_date: "2026-01-02", category: 1,
};
const CATEGORIES = [{ id: 1, name: "Brewing" }];

const mounted: Array<Record<string, any>> = [];
let appSnapshot: any;

const reply = (status: number, data: any) => ({
  ok: status < 400,
  status,
  json: async () => data,
  text: async () => JSON.stringify(data),
});

beforeEach(() => {
  let value: any;
  const un = app.subscribe((v) => (value = v));
  un();
  appSnapshot = { ...value };
  mockFetch.mockReset();
  localStorage.clear();
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!.instance);
  document.body.innerHTML = "";
  app.set(appSnapshot);
  toasts.set([]);
  vi.restoreAllMocks();
});

describe("loader purge — no animate-spin survives outside the splash", () => {
  it("Login: the busy submit button shows text only — disabled, no spinner, and it recovers", async () => {
    const AUTH_URL = "http://api.test/api/auth/token/";
    let release: (() => void) | undefined;
    mockFetch.mockImplementation((url: string) => {
      const u = String(url);
      if (u === AUTH_URL) {
        return new Promise((r) => {
          release = () => r(reply(200, { token: "tok-123" }));
        });
      }
      // post-login schema + claims reads: a harmless empty document
      return reply(200, { openapi: "3.0.3", paths: {}, components: {} });
    });
    app.update((a) => ({
      ...a,
      booted: true,
      config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));
    const host = document.createElement("div");
    document.body.append(host);
    flushSync(() => {
      mounted.push({ instance: mount(Login, { target: host, props: {} }) });
    });

    const user = host.querySelector<HTMLInputElement>("#username")!;
    const pass = host.querySelector<HTMLInputElement>("#password")!;
    user.value = "admin";
    pass.value = "admin123";
    user.dispatchEvent(new Event("input", { bubbles: true }));
    pass.dispatchEvent(new Event("input", { bubbles: true }));
    flushSync(() => {});
    host.querySelector("form")!.dispatchEvent(new SubmitEvent("submit", { cancelable: true }));
    flushSync(() => {});

    // busy, and PURGED: the disabled state says it all — no spinning icon
    const btn = host.querySelector("button.btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain("Signing in");
    expect(host.querySelector(".animate-spin")).toBeNull();

    release!();
    const form = host.querySelector("form")!;
    await vi.waitFor(() => expect((form.querySelector("button.btn") as HTMLButtonElement).disabled).toBe(false));
    expect(host.querySelector(".animate-spin")).toBeNull();
  });

  it("RecordForm: the busy save button shows text only — disabled, no spinner", async () => {
    let release: (() => void) | undefined;
    mockFetch.mockImplementation((url: string, init?: any) => {
      const u = String(url);
      if (init?.method === "PUT" && u.includes("/api/products/7/")) {
        return new Promise((r) => {
          release = () => r(reply(200, { ...ROW7 }));
        });
      }
      if (u.includes("/api/categories/")) return reply(200, { count: 1, results: CATEGORIES, next: null });
      return reply(200, { count: 0, results: [] });
    });
    app.update((a) => ({
      ...a,
      booted: true,
      token: "tok",
      apiUrlOverride: "http://api.test",
      schema: LIVE,
      config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    }));
    const host = document.createElement("div");
    document.body.append(host);
    flushSync(() => {
      recordFormHarnessProps.set({
        model: LIVE.byId["products"],
        record: ROW7,
        onclose: () => {},
        onsaved: () => {},
      });
      mounted.push({ instance: mount(RecordFormHarness, { target: host }) });
    });

    const btn = () => host.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(btn().disabled).toBe(false);
    expect(host.querySelector(".animate-spin")).toBeNull();

    // submit while the PUT is held open -> the BUSY render is on screen
    host.querySelector("form")!.dispatchEvent(new SubmitEvent("submit", { cancelable: true }));
    flushSync(() => {});
    expect(btn().disabled).toBe(true);
    expect(host.querySelector(".animate-spin")).toBeNull();

    release!();
    await vi.waitFor(() => expect(btn().disabled).toBe(false));
    expect(host.querySelector(".animate-spin")).toBeNull();
  });
});
