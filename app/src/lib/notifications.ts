/** Notification center — the in-app list, the unread badge and the OS toast
 *  hand-off (Tauri desktop + Android via tauri-plugin-notification).
 *
 *  Laws this module obeys:
 *  - ONE list is the single source every surface reads (the bell badge, the
 *    Notifications page, threshold alerts fired by dashboard widgets), so an
 *    event raised anywhere shows everywhere.
 *  - Plain JSON in localStorage ("dad.notifications.v1", same namespace as
 *    the other client state), capped — an unbounded notification center is a
 *    memory leak with a UI.
 *  - OS toasts are BEST-EFFORT: browser mode has no Tauri runtime (in-app
 *    only), a denied permission degrades silently, a missing or broken plugin
 *    never throws into the caller — the in-app center already holds the event.
 */
import { derived, writable } from "svelte/store";
import { isTauri } from "./secrets";

export interface AppNotification {
  id: string;
  title: string;
  body: string;
  ts: number;
  read: boolean;
  /** where it came from, e.g. "widget:TrendArea" — shown as a chip */
  source?: string;
}

/** Newest first, hard-capped. */
export const CAP = 50;
const KEY = "dad.notifications.v1";

function load(): AppNotification[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw
      .filter((n) => n && typeof n === "object" && typeof (n as any).title === "string" && typeof (n as any).body === "string")
      .slice(0, CAP)
      .map((n: any, i: number) => ({
        id: typeof n.id === "string" ? n.id : `n${n.ts ?? i}-${i}`,
        title: String(n.title),
        body: String(n.body),
        ts: typeof n.ts === "number" ? n.ts : 0,
        read: n.read === true,
        ...(typeof n.source === "string" && n.source ? { source: n.source } : {}),
      }));
  } catch {
    return [];
  }
}

export const notifications = writable<AppNotification[]>(load());

notifications.subscribe((list) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage full or private — the in-memory list still works */
  }
});

export const unreadCount = derived(notifications, (l) => l.filter((n) => !n.read).length);

let seq = 0;
function nid(): string {
  seq += 1;
  return `n${Date.now().toString(36)}-${seq.toString(36)}`;
}

/** Best-effort OS toast. Never throws, never runs outside Tauri. */
async function fireOs(title: string, body: string): Promise<void> {
  if (!isTauri()) return;
  try {
    const mod = await import("@tauri-apps/plugin-notification");
    let granted = await mod.isPermissionGranted();
    if (!granted) granted = (await mod.requestPermission()) === "granted";
    if (granted) mod.sendNotification({ title, body });
  } catch {
    /* no plugin / no OS layer — the in-app center already has the event */
  }
}

export function pushNotification(n: { title: string; body: string; source?: string }): void {
  const item: AppNotification = {
    id: nid(),
    title: n.title,
    body: n.body,
    ts: Date.now(),
    read: false,
    ...(n.source ? { source: n.source } : {}),
  };
  notifications.update((l) => [item, ...l].slice(0, CAP));
  void fireOs(n.title, n.body);
}

export function markAllRead(): void {
  notifications.update((l) => l.map((n) => (n.read ? n : { ...n, read: true })));
}

/** Read ONE notification (the row click on the Notifications page). */
export function markRead(id: string): void {
  notifications.update((l) => l.map((n) => (n.id === id && !n.read ? { ...n, read: true } : n)));
}

export function clearNotifications(): void {
  notifications.set([]);
}

/** Ask the OS for notification permission (Tauri only; browser = false).
 *  Returns whether toasts may be sent after the prompt. */
export async function requestOsPermission(): Promise<boolean> {
  if (!isTauri()) return false;
  try {
    const mod = await import("@tauri-apps/plugin-notification");
    return (await mod.requestPermission()) === "granted";
  } catch {
    return false;
  }
}

/** "granted"/"denied" drive the permission row on the Notifications page;
 *  "unsupported" in browser mode (the row hides), "unknown" when the plugin
 *  itself is missing or broken. */
export async function osPermissionStatus(): Promise<"granted" | "denied" | "unknown" | "unsupported"> {
  if (!isTauri()) return "unsupported";
  try {
    const mod = await import("@tauri-apps/plugin-notification");
    return (await mod.isPermissionGranted()) ? "granted" : "denied";
  } catch {
    return "unknown";
  }
}

/** Test isolation only: empties the store without touching localStorage
 *  (tests seed and clear it themselves). */
export function __resetForTests(): void {
  notifications.set([]);
}
