/** Widget instances — what the Widget studio persists and the Dashboard renders.
 *
 *  The built-in widgets are CODE: one .svelte file each, auto-discovered by
 *  the registry. An INSTANCE is user data: a chosen widget type plus a title,
 *  a size, a brand-palette accent, an optional FR-R008 data override and an
 *  optional threshold rule. Instances ride the SAME contracts as built-ins —
 *  the data block is validated by the feed engine's own validateWidgetData
 *  (never a second, looser grammar) and rendering goes through the same
 *  schema-resolved feed, so a custom widget can never do anything a declared
 *  one couldn't.
 *
 *  Persistence: plain JSON in localStorage ("dad.widgetInstances.v1",
 *  capped), with export/import as JSON text — a dashboard is data, copyable
 *  between devices and brands.
 *
 *  Threshold rules are evaluated per feed tick in shouldFire(): numeric
 *  aggregates fire once on crossing (cold -> hot), "change" fires once per
 *  actual change after a baseline tick, and the per-instance memory is
 *  resettable for tests. A rule never fires twice for the same state.
 */
import { writable } from "svelte/store";
import { validateWidgetData, type WidgetDataSpec, type FeedResult } from "./feed";

export type AccentRole = "brand" | "accent" | "text";
export type NotifyMode = "above" | "below" | "change";

export interface NotifyRule {
  mode: NotifyMode;
  /** threshold for above/below */
  value?: number;
}

export interface WidgetInstance {
  id: string;
  /** the registry type this renders — a widget file id ("TrendArea") */
  type: string;
  title: string;
  size: "sm" | "lg";
  /** which brand color role-plays as the card's primary */
  accent: AccentRole;
  /** FR-R008 data override — SAME shape the built-ins declare as meta.data */
  data?: WidgetDataSpec;
  notify?: NotifyRule;
  enabled: boolean;
}

export const INSTANCE_CAP = 24;
const KEY = "dad.widgetInstances.v1";

/** Validate one raw instance (a studio draft, an imported JSON entry, a
 *  merged patch). Never throws; a bad instance comes back as a nameable
 *  problem, same law as validateWidgetData. */
export function validateInstance(raw: unknown): { instance: WidgetInstance } | { problem: string } {
  if (raw == null || typeof raw !== "object" || Array.isArray(raw)) {
    return { problem: "an instance must be an object" };
  }
  const r = raw as Record<string, unknown>;
  const type = typeof r.type === "string" ? r.type : "";
  if (!type) return { problem: "instance.type must name a widget type" };
  if (r.accent !== undefined && !(["brand", "accent", "text"] as const).includes(r.accent as AccentRole)) {
    return { problem: `unknown accent "${String(r.accent)}" (brand, accent or text)` };
  }
  if (r.notify !== undefined && r.notify !== null) {
    const n = r.notify as Record<string, unknown>;
    const mode = String(n.mode);
    if (!["above", "below", "change"].includes(mode)) {
      return { problem: `unknown notify mode "${mode}" (above, below or change)` };
    }
    if (mode !== "change" && (typeof n.value !== "number" || !Number.isFinite(n.value))) {
      return { problem: `notify mode "${mode}" needs a finite numeric threshold` };
    }
  }
  let data: WidgetDataSpec | undefined;
  if (r.data !== undefined && r.data !== null) {
    const v = validateWidgetData(r.data);
    if ("problem" in v) return { problem: v.problem.reason };
    data = v.spec;
  }
  const notify: NotifyRule | undefined =
    r.notify && typeof r.notify === "object"
      ? {
          mode: (r.notify as Record<string, unknown>).mode as NotifyMode,
          ...((r.notify as Record<string, unknown>).value !== undefined
            ? { value: (r.notify as Record<string, unknown>).value as number }
            : {}),
        }
      : undefined;
  return {
    instance: {
      id: typeof r.id === "string" && r.id ? r.id : "",
      type,
      title: typeof r.title === "string" && r.title.trim() ? r.title.trim() : type,
      size: r.size === "lg" ? "lg" : "sm",
      accent: (r.accent as AccentRole) ?? "brand",
      ...(data ? { data } : {}),
      ...(notify ? { notify } : {}),
      enabled: r.enabled !== false,
    },
  };
}

function load(): WidgetInstance[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(raw)) return [];
    const seen = new Set<string>();
    const out: WidgetInstance[] = [];
    for (const entry of raw) {
      const v = validateInstance(entry);
      if ("problem" in v) continue; // a half-broken instance never bricks the dashboard
      if (!v.instance.id || seen.has(v.instance.id)) v.instance.id = freshId();
      seen.add(v.instance.id);
      out.push(v.instance);
    }
    return out;
  } catch {
    return [];
  }
}

export const instances = writable<WidgetInstance[]>(load());

instances.subscribe((list) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage full or private — the in-memory list still works */
  }
});

let seq = 0;
function freshId(): string {
  seq += 1;
  return `w${Date.now().toString(36)}-${seq.toString(36)}`;
}

export function addInstance(draft: unknown): { instance: WidgetInstance } | { problem: string } {
  const v = validateInstance(draft);
  if ("problem" in v) return v;
  const inst: WidgetInstance = { ...v.instance, id: v.instance.id || freshId() };
  let result: { instance: WidgetInstance } | { problem: string };
  instances.update((l) => {
    if (l.length >= INSTANCE_CAP) {
      result = { problem: `the dashboard holds at most ${INSTANCE_CAP} custom widgets` };
      return l;
    }
    result = { instance: inst };
    return [...l, inst];
  });
  return result!;
}

export function updateInstance(id: string, patch: Partial<WidgetInstance>): { instance: WidgetInstance } | { problem: string } {
  let result: { instance: WidgetInstance } | { problem: string } = { problem: `no instance "${id}"` };
  instances.update((l) => {
    const i = l.findIndex((x) => x.id === id);
    if (i < 0) return l;
    const v = validateInstance({ ...l[i], ...patch, id }); // id is identity, never patchable
    if ("problem" in v) {
      result = v;
      return l;
    }
    result = { instance: v.instance };
    return [...l.slice(0, i), v.instance, ...l.slice(i + 1)];
  });
  return result!;
}

export function removeInstance(id: string): void {
  instances.update((l) => l.filter((x) => x.id !== id));
}

/** Reorder by swapping with the neighbour (list order = dashboard order). */
export function moveInstance(id: string, dir: -1 | 1): void {
  instances.update((l) => {
    const i = l.findIndex((x) => x.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= l.length) return l;
    const copy = [...l];
    [copy[i], copy[j]] = [copy[j], copy[i]];
    return copy;
  });
}

export function exportInstances(): string {
  return JSON.stringify([...instancesList()], null, 2);
}

/** Replace the whole list from JSON text. All-or-nothing: one bad entry and
 *  nothing changes (a half-imported dashboard is worse than a refused one). */
export function importInstances(text: string): { added: number } | { problem: string } {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return { problem: "not valid JSON" };
  }
  if (!Array.isArray(raw)) return { problem: "expected a JSON array of instances" };
  const out: WidgetInstance[] = [];
  const seen = new Set<string>();
  for (const entry of raw) {
    const v = validateInstance(entry);
    if ("problem" in v) return { problem: v.problem };
    if (!v.instance.id || seen.has(v.instance.id)) v.instance.id = freshId();
    seen.add(v.instance.id);
    out.push(v.instance);
  }
  if (out.length > INSTANCE_CAP) return { problem: `at most ${INSTANCE_CAP} custom widgets` };
  instances.set(out);
  return { added: out.length };
}

function instancesList(): WidgetInstance[] {
  let out: WidgetInstance[] = [];
  instances.subscribe((l) => (out = l))(); // read-once without wiring a component
  return out;
}

/** The number a rule watches, per feed result kind. */
export function numericValue(result: FeedResult): number | null {
  switch (result.kind) {
    case "count":
    case "number":
      return result.value;
    case "delta":
      return result.current;
    case "series":
      return result.values.length ? result.values[result.values.length - 1] : null;
    case "groups":
      return result.total;
  }
}

const memory = new Map<string, { value: number | null; hot: boolean }>();

/** Evaluate one instance's threshold rule against one feed result. Called
 *  every tick; fires only on the transitions a rule promises (crossing for
 *  above/below, change for "change"), never twice for the same state. */
export function shouldFire(inst: WidgetInstance, result: FeedResult): { fire: boolean; text: string } {
  const rule = inst.notify;
  if (!rule) return { fire: false, text: "" };
  const prev = memory.get(inst.id) ?? null;
  const v = numericValue(result);
  if (rule.mode === "change") {
    const changed = prev !== null && prev.value !== null && v !== null && v !== prev.value;
    memory.set(inst.id, { value: v, hot: false });
    return { fire: changed, text: `${result.label}: ${prev?.value ?? "—"} → ${v ?? "—"}` };
  }
  const hot = v !== null && (rule.mode === "above" ? v > rule.value! : v < rule.value!);
  const wasHot = prev?.hot ?? false;
  memory.set(inst.id, { value: v, hot });
  return { fire: hot && !wasHot, text: `${result.label}: ${v ?? "—"} (${rule.mode} ${rule.value})` };
}

/** Test isolation: forget every rule's last state. */
export function resetInstanceMemory(): void {
  memory.clear();
}

/** Test isolation: empty the store without touching localStorage. */
export function __resetInstancesForTests(): void {
  instances.set([]);
}
