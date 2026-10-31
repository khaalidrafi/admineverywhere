/** Notification center — the store + OS bridge, graded before any UI mounts.
 *
 *  Why this file exists: the notification list is the single source the bell
 *  badge, the Notifications page and the dashboard threshold alerts all read.
 *  If the store lost events, double-pushed, or fired OS toasts in browser
 *  mode, every consumer would look individually innocent — so the contract is
 *  graded here, at the seam, including the Tauri hand-off (mocked plugin) and
 *  the localStorage rehydration a page reload depends on.
 */
import { beforeEach, describe, expect, it, vi, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  notifications,
  unreadCount,
  pushNotification,
  markAllRead,
  clearNotifications,
  osPermissionStatus,
  CAP,
  __resetForTests,
} from "../notifications";

/** The Tauri plugin mock: flags live in vi.hoisted so the hoisted factory can
 *  read them; `grantedNow` answers isPermissionGranted, `ask` answers the
 *  requestPermission() prompt. */
const h = vi.hoisted(() => ({
  grantedNow: true,
  ask: "granted" as "granted" | "denied",
  sent: [] as Array<Record<string, unknown>>,
}));

vi.mock("@tauri-apps/plugin-notification", () => ({
  isPermissionGranted: async () => h.grantedNow,
  requestPermission: async () => h.ask,
  sendNotification: (n: Record<string, unknown>) => {
    h.sent.push(n);
  },
}));

function tauriMode(on: boolean) {
  if (on) (window as any).__TAURI_INTERNALS__ = {};
  else delete (window as any).__TAURI_INTERNALS__;
}

beforeEach(() => {
  localStorage.clear();
  __resetForTests();
  h.sent.length = 0;
  h.grantedNow = true;
  h.ask = "granted";
});

afterEach(() => tauriMode(false));

describe("the notification store", () => {
  it("starts empty on a clean browser profile", () => {
    expect(get(notifications)).toEqual([]);
    expect(get(unreadCount)).toBe(0);
  });

  it("push adds newest first with id, ts and read=false", () => {
    pushNotification({ title: "First", body: "b1" });
    pushNotification({ title: "Second", body: "b2", source: "widget:TrendArea" });
    const list = get(notifications);
    expect(list.map((n) => n.title)).toEqual(["Second", "First"]);
    expect(list[0].read).toBe(false);
    expect(list[0].source).toBe("widget:TrendArea");
    expect(list[0].id).not.toBe(list[1].id);
    expect(list[0].ts).toBeGreaterThanOrEqual(list[1].ts);
  });

  it(`caps the list at ${CAP} entries, dropping the oldest`, () => {
    for (let i = 0; i < CAP + 5; i++) pushNotification({ title: `n${i}`, body: "x" });
    const list = get(notifications);
    expect(list).toHaveLength(CAP);
    expect(list[0].title).toBe(`n${CAP + 4}`); // newest kept
    expect(list.at(-1)!.title).toBe(`n5`); // oldest five dropped
  });

  it("unreadCount counts unread; markAllRead zeroes it and persists read=true", () => {
    pushNotification({ title: "a", body: "x" });
    pushNotification({ title: "b", body: "x" });
    expect(get(unreadCount)).toBe(2);
    markAllRead();
    expect(get(unreadCount)).toBe(0);
    const stored = JSON.parse(localStorage.getItem("dad.notifications.v1") ?? "[]");
    expect(stored.every((n: any) => n.read === true)).toBe(true);
  });

  it("clear empties the list and persists the empty state", () => {
    pushNotification({ title: "a", body: "x" });
    clearNotifications();
    expect(get(notifications)).toEqual([]);
    expect(localStorage.getItem("dad.notifications.v1")).toBe("[]");
  });

  it("rehydrates a previous session's list from localStorage", async () => {
    localStorage.setItem(
      "dad.notifications.v1",
      JSON.stringify([
        { id: "a", title: "Kept", body: "b", ts: 2, read: false },
        { id: "b", title: "Old", body: "b", ts: 1, read: true },
      ]),
    );
    vi.resetModules();
    const mod = await import("../notifications");
    expect(get(mod.notifications).map((n) => n.id)).toEqual(["a", "b"]);
    expect(get(mod.unreadCount)).toBe(1);
  });

  it("rehydration drops malformed entries instead of crashing", async () => {
    localStorage.setItem(
      "dad.notifications.v1",
      JSON.stringify([{ title: "ok", body: "b", ts: 1 }, null, "junk", { nope: true }, 42]),
    );
    vi.resetModules();
    const mod = await import("../notifications");
    expect(get(mod.notifications).map((n) => n.title)).toEqual(["ok"]);
  });
});

describe("the OS toast bridge", () => {
  it("browser mode never attempts an OS toast", () => {
    pushNotification({ title: "web", body: "x" });
    expect(h.sent).toEqual([]);
  });

  it("tauri mode + granted permission: push sends the toast", async () => {
    tauriMode(true);
    pushNotification({ title: "Hello", body: "from the studio" });
    await vi.waitFor(() => expect(h.sent).toHaveLength(1));
    expect(h.sent[0]).toMatchObject({ title: "Hello", body: "from the studio" });
  });

  it("tauri mode + granted on request: the prompt answers and the toast ships", async () => {
    tauriMode(true);
    h.grantedNow = false; // not yet asked
    h.ask = "granted";
    pushNotification({ title: "Ask", body: "x" });
    await vi.waitFor(() => expect(h.sent).toHaveLength(1));
  });

  it("tauri mode + denied request: no toast, and the in-app event still lands", async () => {
    tauriMode(true);
    h.grantedNow = false;
    h.ask = "denied";
    pushNotification({ title: "Denied", body: "x" });
    await new Promise((r) => setTimeout(r, 0)); // let the bridge settle
    expect(h.sent).toEqual([]);
    expect(get(notifications).map((n) => n.title)).toEqual(["Denied"]);
  });

  it("osPermissionStatus: unsupported in browser, real answer under Tauri", async () => {
    expect(await osPermissionStatus()).toBe("unsupported");
    tauriMode(true);
    expect(await osPermissionStatus()).toBe("granted");
    h.grantedNow = false;
    expect(await osPermissionStatus()).toBe("denied");
  });
});
