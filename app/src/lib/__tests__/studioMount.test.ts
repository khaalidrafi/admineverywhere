/** The Widget studio page, graded on the mounted UI.
 *
 *  The instance CONTRACT lives in instances.test.ts; what only a mount can
 *  prove: the type dropdown is the live widget registry, the data-source
 *  builder feeds the real engine (the preview paints from schema-resolved
 *  paths), Add really persists, the list buttons really mutate the store,
 *  and an unhonourable draft is refused loudly instead of half-added.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import type { Component } from "svelte";
import { get } from "svelte/store";
import WidgetStudio from "../../pages/WidgetStudio.svelte";
import { widgets } from "../../widgets";
import { app } from "../stores";
import {
  instances,
  addInstance,
  __resetInstancesForTests,
  type WidgetInstance,
} from "../widgets/instances";

const BASE = "http://studio.test";
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
let host: HTMLElement;

const f = (name: string, type: string, extra: Partial<any> = {}) =>
  ({ name, type, required: false, readOnly: false, ...extra });

const SCHEMA = (() => {
  const orders = {
    id: "orders",
    name: "Order",
    singular: "order",
    listPath: "/api/orders/",
    detailPath: "/api/orders/{id}/",
    fields: [
      f("id", "number"),
      f("created_at", "datetime", { readOnly: true }),
      f("status", "enum", { choices: ["pending", "paid", "shipped"] }),
      f("total", "number"),
    ],
    byName: {} as Record<string, any>,
    labelField: "id",
  };
  orders.byName = Object.fromEntries(orders.fields.map((x) => [x.name, x]));
  return { models: [orders], byId: { orders } } as any;
})();

function jsonReply(rows: any[], count: number | null = null) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ count: count ?? rows.length, results: rows, next: null }),
    text: async () => JSON.stringify({ count: count ?? rows.length, results: rows, next: null }),
  };
}

function render(component: Component, props: Record<string, unknown> = {}): HTMLElement {
  host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  return host;
}

const text = (el: HTMLElement) => (el.textContent ?? "").replace(/\s+/g, " ").trim();
/** Drive a <select bind:value> the way recordFormMount does: Svelte 5's change
 *  handler reads the selected option via querySelector(":checked"), which
 *  happy-dom does not derive from a programmatic .value set — so the option
 *  is staged for :checked before the event, inside flushSync. */
function pick(select: HTMLSelectElement, value: string) {
  const opt = [...select.options].find((o) => o.value === value);
  expect(opt, `no option "${value}" to pick`).toBeTruthy();
  const native = select.querySelector.bind(select);
  (select as any).querySelector = (q: string) => (q === ":checked" ? opt : (native as any)(q));
  try {
    flushSync(() => {
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
  } finally {
    delete (select as any).querySelector;
  }
}

const button = (el: HTMLElement, label: string) =>
  [...el.querySelectorAll("button")].find((b) => b.textContent!.trim().includes(label));

beforeEach(() => {
  localStorage.clear();
  __resetInstancesForTests();
  mockFetch.mockReset();
  mockFetch.mockResolvedValue(jsonReply([{ id: 1, created_at: "2026-10-31T08:00:00Z", status: "paid", total: "3.00" }]));
  app.update((a) => ({ ...a, schema: SCHEMA, token: "", apiUrlOverride: BASE }));
  document.body.innerHTML = "";
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  app.update((a) => ({ ...a, schema: null, apiUrlOverride: "" }));
});

describe("the Widget studio", () => {
  it("offers every registry type — a dropped-in built-in is immediately buildable", () => {
    const el = render(WidgetStudio);
    const select = el.querySelector("#type-select")!;
    expect((select as HTMLSelectElement).options.length).toBe(widgets.length);
    for (const w of widgets) {
      expect(text(el)).toContain(w.title);
    }
  });

  it("fed types wire a data source; the preview paints through the real engine", async () => {
    const el = render(WidgetStudio);
    expect(text(el)).toContain("Data source"); // TrendArea is fed by default

    const modelSelect = [...el.querySelectorAll("select")].find((s) =>
      [...(s as HTMLSelectElement).options].some((o) => o.value === "orders"),
    )!;
    pick(modelSelect, "orders");

    await vi.waitFor(() => {
      flushSync();
      const preview = [...el.querySelectorAll(".card")].find((c) => c.querySelector("svg"));
      expect(preview, "the preview never painted a chart").toBeTruthy();
    });
    for (const call of mockFetch.mock.calls) {
      const url = new URL(String(call[0]));
      expect(url.pathname, `the preview requested ${url.pathname}`).toBe("/api/orders/");
    }
  });

  it("Add persists the instance and says so", () => {
    const el = render(WidgetStudio);
    const title = el.querySelector("input.input") as HTMLInputElement;
    title.value = "My custom trend";
    title.dispatchEvent(new Event("input"));
    flushSync();

    button(el, "Add to dashboard")!.click();
    flushSync();

    const list = get(instances);
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({ type: "TrendArea", title: "My custom trend", enabled: true });
    const stored = JSON.parse(localStorage.getItem("dad.widgetInstances.v1") ?? "[]");
    expect(stored).toHaveLength(1);
    expect(text(el)).toContain("it's on your dashboard");
  });

  it("an unhonourable draft is refused loudly, the store untouched", () => {
    const el = render(WidgetStudio);
    // notify above with a non-numeric threshold: type letters into the value field
    const notify = [...el.querySelectorAll("select")].find((s) =>
      [...(s as HTMLSelectElement).options].some((o) => o.value === "above"),
    ) as HTMLSelectElement;
    pick(notify, "above");
    const threshold = el.querySelector("#notify-value") as HTMLInputElement;
    threshold.value = "abc"; // raw text: garbage is refused, never coerced to 0
    threshold.dispatchEvent(new Event("input"));
    flushSync();

    button(el, "Add to dashboard")!.click();
    flushSync();

    expect(get(instances)).toHaveLength(0);
    expect(text(el)).toContain("threshold");
  });

  it("the list rows mutate the store: remove and reorder", () => {
    const a = (addInstance({ type: "QuoteCard", title: "A" }) as { instance: WidgetInstance }).instance;
    const b = (addInstance({ type: "QuoteCard", title: "B" }) as { instance: WidgetInstance }).instance;
    const el = render(WidgetStudio);

    expect(text(el)).toContain("Your widgets (2)");
    // move B up
    const rowB = [...el.querySelectorAll("li.card")].find((li) => li.textContent!.includes("B"))!;
    const moveUp = [...rowB.querySelectorAll("button")].find((btn) => btn.title === "Move up")!;
    moveUp.click();
    flushSync();
    expect(get(instances).map((i) => i.title)).toEqual(["B", "A"]);

    const rowA2 = [...el.querySelectorAll("li.card")].find((li) => li.textContent!.includes("A"))!;
    [...rowA2.querySelectorAll("button")].find((btn) => btn.title === "Remove")!.click();
    flushSync();
    expect(get(instances).map((i) => i.title)).toEqual(["B"]);
  });

  it("hide/show toggles enabled without deleting", () => {
    addInstance({ type: "QuoteCard", title: "A" });
    const el = render(WidgetStudio);
    const row = el.querySelector("li.card")!;
    [...row.querySelectorAll("button")].find((btn) => btn.title === "Hide from dashboard")!.click();
    flushSync();
    expect(get(instances)[0].enabled).toBe(false);
    [...row.querySelectorAll("button")].find((btn) => btn.title === "Show on dashboard")!.click();
    flushSync();
    expect(get(instances)[0].enabled).toBe(true);
  });

  it("export fills the box; a bad import is refused with the store intact", () => {
    addInstance({ type: "TrendArea", title: "Exported one", data: { aggregate: "count" } });
    const el = render(WidgetStudio);

    button(el, "Export")!.click();
    flushSync();
    const box = el.querySelector("textarea") as HTMLTextAreaElement;
    expect(box.value).toContain("Exported one");

    box.value = "{not json";
    box.dispatchEvent(new Event("input"));
    flushSync();
    button(el, "Import")!.click();
    flushSync();
    expect(text(el)).toContain("not valid JSON");
    expect(get(instances)).toHaveLength(1); // all-or-nothing held
  });

  it("import replaces the dashboard from pasted JSON", () => {
    const el = render(WidgetStudio);
    const box = el.querySelector("textarea") as HTMLTextAreaElement;
    box.value = JSON.stringify([
      { type: "QuoteCard", title: "From elsewhere" },
      { type: "TrendArea", title: "Also mine", data: { aggregate: "count" } },
    ]);
    box.dispatchEvent(new Event("input"));
    flushSync();
    button(el, "Import")!.click();
    flushSync();

    expect(get(instances).map((i) => i.title)).toEqual(["From elsewhere", "Also mine"]);
    expect(text(el)).toContain("Imported 2 widgets");
  });
});
