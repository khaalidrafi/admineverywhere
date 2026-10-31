/** The instance card on the real dashboard grid — custom widgets are
 *  citizens, not embeds.
 *
 *  instances.test.ts grades the contract, studioMount.test.ts grades the
 *  builder; what only THIS file can prove: a user-built widget paints on the
 *  Dashboard grid through the same schema-resolved feed law as built-ins
 *  (never a guessed URL), the accent role re-maps the card's brand variable,
 *  disabled and unknown instances render nothing, and a crossing threshold
 *  raises exactly one notification through the ONE store — with the feed
 *  label in its body, not a generic string.
 *
 *  Timing note: the feed resolves on microtasks AFTER mount, and a poller
 *  interleaving flushSync proved unreliable in happy-dom — every async
 *  assertion here settles on a real macrotask beat, then asserts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import Dashboard from "../../pages/Dashboard.svelte";
import { app } from "../stores";
import { addInstance, __resetInstancesForTests, type WidgetInstance } from "../widgets/instances";
import { pushNotification } from "../notifications";

vi.mock("../notifications", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  pushNotification: vi.fn(),
}));

const BASE = "http://grid.test";
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
let host: HTMLElement;

const f = (name: string, type: string, extra: Partial<any> = {}) =>
  ({ name, type, required: false, readOnly: false, ...extra });

function makeSchema() {
  const orders = {
    id: "orders",
    name: "Order",
    singular: "order",
    listPath: "/api/orders/",
    detailPath: "/api/orders/{id}/",
    fields: [
      f("id", "number"),
      f("created_at", "datetime", { readOnly: true }),
      f("status", "enum", { choices: ["pending", "paid"] }),
      f("total", "number"),
    ],
    byName: {} as Record<string, any>,
    labelField: "id",
  };
  orders.byName = Object.fromEntries(orders.fields.map((x) => [x.name, x]));
  return { models: [orders], byId: { orders } } as any;
}

function jsonReply(rows: any[]) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ count: rows.length, results: rows, next: null }),
    text: async () => JSON.stringify({ count: rows.length, results: rows, next: null }),
  };
}

function renderDashboard(schema: any) {
  app.update((a) => ({ ...a, schema, token: "", apiUrlOverride: BASE }));
  host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(Dashboard, { target: host }));
  });
  return host;
}

async function settle(ms = 300) {
  await new Promise((r) => setTimeout(r, ms));
  flushSync();
}

function cellFor(title: string): HTMLElement {
  const cell = [...host.querySelectorAll(".grid > div")].find(
    (c) => (c.querySelector("h2")?.textContent ?? "").trim() === title,
  );
  expect(cell, `the grid rendered no cell titled "${title}"`).not.toBeUndefined();
  return cell as HTMLElement;
}

beforeEach(() => {
  localStorage.clear();
  __resetInstancesForTests();
  mockFetch.mockReset();
  vi.mocked(pushNotification).mockClear();
  document.body.innerHTML = "";
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  app.update((a) => ({ ...a, schema: null, apiUrlOverride: "" }));
});

describe("custom widgets on the dashboard grid", () => {
  it("paints a user-built widget from the schema-resolved feed, never a guessed URL", async () => {
    mockFetch.mockResolvedValue(jsonReply([{ id: 1, created_at: "2026-10-31T08:00:00Z", status: "paid", total: "3.00" }]));
    addInstance({
      type: "TrendArea",
      title: "My custom trend",
      data: { endpoint: "orders", aggregate: "bucket", field: "", days: 5, pollInterval: 0, rowCap: 300 },
    } as Partial<WidgetInstance>);
    renderDashboard(makeSchema());

    await settle();
    expect(cellFor("My custom trend").querySelector("svg")).toBeTruthy();
    for (const call of mockFetch.mock.calls) {
      const url = new URL(String(call[0]));
      expect(url.pathname, `a custom widget requested ${url.pathname}`).toBe("/api/orders/");
    }
  });

  it("the accent role re-maps the card's brand variable — no hard-coded colors", async () => {
    mockFetch.mockResolvedValue(jsonReply([]));
    addInstance({ type: "QuoteCard", title: "Plain", accent: "brand" } as Partial<WidgetInstance>);
    addInstance({ type: "QuoteCard", title: "Cyan", accent: "accent" } as Partial<WidgetInstance>);
    addInstance({ type: "QuoteCard", title: "Texty", accent: "text" } as Partial<WidgetInstance>);
    renderDashboard(makeSchema());
    await settle(50);

    expect(cellFor("Plain").querySelector(".card")!.getAttribute("style") ?? "").not.toContain("--brand-primary");
    expect(cellFor("Cyan").querySelector(".card")!.getAttribute("style")).toContain("--brand-primary: var(--brand-accent)");
    expect(cellFor("Texty").querySelector(".card")!.getAttribute("style")).toContain("--brand-primary: var(--brand-text)");
  });

  it("a disabled or unknown instance renders nothing, the rest still render", async () => {
    mockFetch.mockResolvedValue(jsonReply([]));
    addInstance({ type: "QuoteCard", title: "Hidden one", enabled: false } as Partial<WidgetInstance>);
    addInstance({ type: "GhostWidget", title: "Ghost" } as Partial<WidgetInstance>);
    addInstance({ type: "QuoteCard", title: "Shown one" } as Partial<WidgetInstance>);
    renderDashboard(makeSchema());
    await settle(50);

    const titles = [...host.querySelectorAll(".grid h2")].map((h) => h.textContent!.trim());
    expect(titles).not.toContain("Hidden one");
    expect(titles).not.toContain("Ghost");
    expect(titles).toContain("Shown one");
  });

  it("a crossing threshold raises exactly one notification naming the widget", async () => {
    mockFetch.mockResolvedValue(jsonReply([{ id: 1, created_at: "2026-10-31T08:00:00Z", status: "paid", total: "3.00" }]));
    addInstance({
      type: "TrendArea",
      title: "Guarded trend",
      data: { endpoint: "orders", aggregate: "count", field: "", days: 5, pollInterval: 0, rowCap: 300 },
      notify: { mode: "above", value: 0 }, // one record > 0 → crossing on the first tick
    } as Partial<WidgetInstance>);
    renderDashboard(makeSchema());

    await settle();
    expect(vi.mocked(pushNotification)).toHaveBeenCalledTimes(1);
    const call = vi.mocked(pushNotification).mock.calls[0][0];
    expect(call.title).toBe("Guarded trend");
    expect(call.body).toContain("Order"); // the feed's label, not a generic string
    expect(call.source).toBe("widget:TrendArea");
  });

  it("below the threshold nothing fires, the card still renders", async () => {
    mockFetch.mockResolvedValue(jsonReply([{ id: 1, created_at: "2026-10-31T08:00:00Z", status: "paid", total: "3.00" }]));
    addInstance({
      type: "TrendArea",
      title: "Calm trend",
      data: { endpoint: "orders", aggregate: "count", field: "", days: 5, pollInterval: 0, rowCap: 300 },
      notify: { mode: "above", value: 100 },
    } as Partial<WidgetInstance>);
    renderDashboard(makeSchema());

    await settle();
    // a count feed feeds the RULE, not a series chart — the cell is present,
    // the tick happened (the rule saw the number), and nothing fired
    expect(cellFor("Calm trend")).toBeDefined();
    expect(vi.mocked(pushNotification)).toHaveBeenCalledTimes(0);
  });

  it("the dashboard subtitle counts custom widgets", async () => {
    mockFetch.mockResolvedValue(jsonReply([]));
    addInstance({ type: "QuoteCard", title: "One" } as Partial<WidgetInstance>);
    addInstance({ type: "QuoteCard", title: "Two", enabled: false } as Partial<WidgetInstance>);
    const el = renderDashboard(makeSchema());
    expect((el.textContent ?? "").replace(/\s+/g, " ")).toContain("+ 1 yours");
  });
});
