/** The notification center UI, graded on the mounted page + bell.
 *
 *  Module-level store laws live in notifications.test.ts; what only a mount
 *  can prove: the page renders the store it is handed (no local copy), the
 *  badge on the bell tracks the same store, the buttons really mutate it,
 *  the OS permission row follows the runtime (hidden in browser mode), and
 *  the bell routes through the page REGISTRY — never a hand-typed hash.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import type { Component } from "svelte";
import { get } from "svelte/store";
import Notifications from "../../pages/Notifications.svelte";
import NotificationBell from "../../components/NotificationBell.svelte";
import {
  notifications,
  unreadCount,
  pushNotification,
  __resetForTests,
} from "../notifications";
import { pages, pageHref } from "../pages";

const h = vi.hoisted(() => ({
  grantedNow: false,
  ask: "granted" as "granted" | "denied",
}));

vi.mock("@tauri-apps/plugin-notification", () => ({
  isPermissionGranted: async () => h.grantedNow,
  requestPermission: async () => h.ask,
  sendNotification: (_n: unknown) => {},
}));

const mounted: Array<Record<string, any>> = [];

function render(component: Component, props: Record<string, unknown> = {}): HTMLElement {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  return host;
}

const text = (el: HTMLElement) => (el.textContent ?? "").replace(/\s+/g, " ").trim();

beforeEach(() => {
  localStorage.clear();
  __resetForTests();
  h.grantedNow = false;
  h.ask = "granted";
  delete (window as any).__TAURI_INTERNALS__;
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
});

describe("the Notifications page", () => {
  it("renders the store newest first, unread dots included", () => {
    pushNotification({ title: "Older", body: "b1" });
    pushNotification({ title: "Newer", body: "b2", source: "widget:TrendArea" });
    const host = render(Notifications);

    expect(text(host)).toContain("2 events · 2 unread");
    const titles = [...host.querySelectorAll(".font-semibold")].map((n) => n.textContent!.trim());
    expect(titles).toContain("Newer");
    expect(text(host).indexOf("Newer")).toBeLessThan(text(host).indexOf("Older"));
    expect(host.querySelectorAll("[aria-label='unread']").length).toBe(2);
    expect(text(host)).toContain("widget:TrendArea"); // the source chip
  });

  it("mark all read zeroes the badge on the SAME store the bell reads", () => {
    const host = document.createElement("div");
    document.body.append(host);
    pushNotification({ title: "a", body: "x" });
    pushNotification({ title: "b", body: "x" });
    flushSync(() => {
      mounted.push(mount(NotificationBell, { target: host }));
      mounted.push(mount(Notifications, { target: host }));
    });

    const badge = () => host.querySelector("[aria-label^='Notifications,']");
    expect(badge()?.textContent?.trim()).toBe("2");

    const mark = [...host.querySelectorAll("button")].find((b) => b.textContent!.includes("Mark all read"))!;
    mark.click();
    flushSync();

    expect(get(unreadCount)).toBe(0);
    expect(badge()).toBeNull(); // badge gone from the bell, not just the page
    expect(host.querySelectorAll("[aria-label='unread']").length).toBe(0);
  });

  it("clear empties the list and shows the quiet state", () => {
    pushNotification({ title: "a", body: "x" });
    const host = render(Notifications);
    const clear = [...host.querySelectorAll("button")].find((b) => b.textContent!.trim() === "Clear")!;
    clear.click();
    flushSync();

    expect(get(notifications)).toEqual([]);
    expect(localStorage.getItem("dad.notifications.v1")).toBe("[]");
    expect(text(host)).toContain("Quiet for now");
  });

  it("clicking an unread event marks just that one read", () => {
    pushNotification({ title: "a", body: "x" });
    pushNotification({ title: "b", body: "x" });
    const host = render(Notifications);
    const row = [...host.querySelectorAll("li > button")].find((b) => b.textContent!.includes("b"))!;
    row.click();
    flushSync();

    expect(get(unreadCount)).toBe(1);
    const stored = JSON.parse(localStorage.getItem("dad.notifications.v1") ?? "[]");
    expect(stored.find((n: any) => n.title === "b").read).toBe(true);
    expect(stored.find((n: any) => n.title === "a").read).toBe(false);
  });

  it("the OS permission row hides in browser mode", () => {
    const host = render(Notifications);
    expect(text(host)).not.toContain("not enabled yet");
    expect(text(host)).not.toContain("enabled —");
  });

  it("under Tauri the row shows status and the Enable prompt really asks", async () => {
    (window as any).__TAURI_INTERNALS__ = {};
    const host = render(Notifications);
    await vi.waitFor(() => expect(text(host)).toContain("not enabled yet"));

    const enable = [...host.querySelectorAll("button")].find((b) => b.textContent!.trim() === "Enable")!;
    enable.click();
    await vi.waitFor(() => expect(text(host)).toContain("enabled —"));
  });
});

describe("the bell", () => {
  it("routes through the page registry, never a typed hash", () => {
    const host = render(NotificationBell);
    const bell = host.querySelector("button")!;
    expect(bell, "the bell hid while the Notifications page is declared").not.toBeNull();

    bell.click();
    const declared = pages.find((p) => p.id === "Notifications")!;
    expect(location.hash).toBe(pageHref(declared));
  });

  it("shows the unread count, capped at 9+", () => {
    const host = document.createElement("div");
    document.body.append(host);
    flushSync(() => {
      mounted.push(mount(NotificationBell, { target: host }));
    });
    for (let i = 0; i < 12; i++) pushNotification({ title: `n${i}`, body: "x" });
    flushSync();

    const badge = host.querySelector("[aria-label^='Notifications,']")!;
    expect(badge.textContent!.trim()).toBe("9+");
  });
});
