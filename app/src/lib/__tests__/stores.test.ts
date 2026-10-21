/** The stores own three decisions nothing else proves — the app-wide ERROR
 *  POLICY (handleApiError), the config OVERRIDE merge (effectiveConfig), and
 *  the toast self-dismiss TIMER — yet every existing test only ever MOCKS the
 *  first two (RecordForm.test.ts:9-10) or imports the raw `app` writable. So
 *  the shipped branches run zero tests while the suite stays green: the exact
 *  disconnected-builder class the 16:11Z / 16:36Z notes call out. These mount
 *  NOTHING and mock NOTHING from this module — they drive the real functions
 *  and assert the EFFECT on the live stores / localStorage / timer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { ApiError } from "../api";
import {
  app,
  claims,
  effectiveConfig,
  handleApiError,
  logout,
  toast,
  toasts,
  type AppState,
} from "../stores";

const BRAND = { appName: "Testcraft", tagline: "", colors: {}, radius: "0", font: "Inter" };

function baseline(over: Partial<AppState> = {}): AppState {
  return {
    booted: true,
    config: null,
    brand: BRAND,
    token: "",
    username: "",
    apiUrlOverride: "",
    schema: null,
    schemaLoading: false,
    backendDown: false,
    ...over,
  };
}

beforeEach(() => {
  toasts.set([]);
  claims.set(null);
  app.set(baseline());
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("effectiveConfig: the override wins over the base apiUrl, the rest is kept", () => {
  it("falls back to the documented auth/schema defaults with no config", () => {
    app.set(baseline({ config: null, apiUrlOverride: "" }));
    expect(effectiveConfig()).toEqual({
      apiUrl: "",
      authPath: "/api/auth/token/",
      schemaPath: "/api/schema/",
    });
  });

  it("keeps the config's own apiUrl when no override is set", () => {
    app.set(baseline({ config: { apiUrl: "http://base", authPath: "/a", schemaPath: "/s" } }));
    expect(effectiveConfig().apiUrl).toBe("http://base");
  });

  it("replaces ONLY apiUrl with the override — auth/schema ride from the config", () => {
    app.set(
      baseline({
        config: { apiUrl: "http://base", authPath: "/a", schemaPath: "/s" },
        apiUrlOverride: "http://over",
      }),
    );
    expect(effectiveConfig()).toEqual({ apiUrl: "http://over", authPath: "/a", schemaPath: "/s" });
  });
});

describe("handleApiError: the central error policy, branch by branch", () => {
  it("a network error raises the banner flag and emits NO toast", () => {
    const seen = toasts.subscribe(() => {});
    handleApiError(new ApiError("Cannot reach backend", { network: true }));
    expect(get(app).backendDown).toBe(true);
    expect(get(toasts)).toHaveLength(0);
    seen();
  });

  it("a 401 logs the session out AND toasts the expiry", () => {
    app.set(baseline({ token: "tok", username: "u", schema: { byId: {}, models: [] } as any }));
    claims.set({ username: "u", isStaff: true, isSuperuser: false, roles: ["auditors"] });
    localStorage.setItem("dad.token", "tok");
    localStorage.setItem("dad.username", "u");

    handleApiError(new ApiError("API 401", { status: 401 }));

    // the logout side effect, measured not asserted-by-mock:
    expect(get(app).token).toBe("");
    expect(get(app).username).toBe("");
    expect(get(app).schema).toBeNull();
    expect(get(claims)).toBeNull();
    expect(localStorage.getItem("dad.token")).toBeNull();
    expect(localStorage.getItem("dad.username")).toBeNull();
    // the user-visible expiry toast, and NOT a raw status line:
    expect(get(toasts).map((t) => t.text)).toContain("Session expired — please sign in again");
  });

  it("a 400 with a string detail surfaces message + reason on one line", () => {
    handleApiError(new ApiError("API 400", { status: 400, detail: "name is required" }));
    expect(get(toasts)).toEqual([
      expect.objectContaining({ kind: "error", text: "API 400: name is required" }),
    ]);
  });

  it("a 400 with an object detail toasts the message only — never a leaked object", () => {
    handleApiError(new ApiError("API 400", { status: 400, detail: { errors: ["boom"] } }));
    expect(get(toasts)[0].text).toBe("API 400");
    expect(get(toasts)[0].text).not.toContain("[object Object]");
  });

  it("a non-ApiError still reaches the user via its message", () => {
    handleApiError(new Error("kaboom"));
    expect(get(toasts)[0].text).toBe("kaboom");
  });
});

describe("logout: clears store, claims and the persisted keys", () => {
  it("drops token/username/schema, nulls claims, and removes both localStorage keys", () => {
    app.set(baseline({ token: "tok", username: "u", schema: { byId: {}, models: [] } as any }));
    claims.set({ username: "u", isStaff: false, isSuperuser: false, roles: ["x"] });
    localStorage.setItem("dad.token", "tok");
    localStorage.setItem("dad.username", "u");

    logout();

    expect(get(app).token).toBe("");
    expect(get(app).username).toBe("");
    expect(get(app).schema).toBeNull();
    expect(get(claims)).toBeNull();
    expect(localStorage.getItem("dad.token")).toBeNull();
    expect(localStorage.getItem("dad.username")).toBeNull();
  });
});

describe("toast: it self-dismisses on its OWN 4s timer (not the feed engine's)", () => {
  it("appears now and is gone after 4000ms — and only after it", () => {
    vi.useFakeTimers();
    toast("success", "Saved");
    expect(get(toasts)).toHaveLength(1);

    // Just under the window: still here, so the cap is 4000, not smaller.
    vi.advanceTimersByTime(3999);
    expect(get(toasts)).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(get(toasts)).toHaveLength(0);
  });

  it("dismisses ONLY the expired toast, never a sibling that is still in-window", () => {
    vi.useFakeTimers();
    toast("error", "first");
    vi.advanceTimersByTime(2000);
    toast("info", "second");

    // +2000 → first crosses 4000, second is only 2000 old.
    vi.advanceTimersByTime(2000);
    const texts = get(toasts).map((t) => t.text);
    expect(texts).toEqual(["second"]);
  });
});
