/** FR-R008 wire proof for the three fed stat tiles — LiveOrders (count on the
 *  engine's poll), TodayRevenue (latest day-bucket over its window) and
 *  CompletionGauge (leading declared choice as a radial fraction). Same
 *  harness as chartMount.test.ts (browser resolve condition + manual
 *  flushSync): pure-module tests over feed.ts stay green while a tile prints
 *  the wrong number, draws geometry off the wrong quantity or guesses a URL,
 *  so every assertion here is DOM- and request-level, judged through the
 *  component. The DeltaChip poll law (widgetMount.test.ts) is re-proven for
 *  LiveOrders at its own 15 s cadence: first tick at once, nothing early,
 *  the second tick exactly at 15 s, and the timer dead after unmount. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import LiveOrders from "../../widgets/LiveOrders.svelte";
import TodayRevenue from "../../widgets/TodayRevenue.svelte";
import CompletionGauge from "../../widgets/CompletionGauge.svelte";
import { app } from "../stores";
import { dayKeys } from "../widgets/feed";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const C = 2 * Math.PI * 40; // the gauge's own circumference (r=40)

const mounted: Array<Record<string, any>> = [];
let snapshot: any;

beforeEach(() => {
  const a = get(app);
  snapshot = { ...a, schema: null, config: a.config ?? null };
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  mockFetch.mockReset();
  app.set(snapshot);
  vi.useRealTimers();
});

function jsonReply(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

const f = (name: string, type: string, extra: Partial<FieldSpec> = {}): FieldSpec =>
  ({ name, type: type as FieldSpec["type"], required: false, readOnly: false, ...extra });

function model(id: string, name: string, fields: FieldSpec[]): ModelSpec {
  return {
    id,
    name,
    singular: id.replace(/s$/, ""),
    listPath: `/api/${id}/`,
    detailPath: `/api/${id}/{id}/`,
    fields,
    byName: Object.fromEntries(fields.map((x) => [x.name, x])),
    labelField: "id",
  };
}

/** Schema that can feed every tile: a readOnly created_at, a status enum and
 *  a numeric total — none of the three widgets names any of them. */
const ORDERS = model("orders", "Order", [
  f("created_at", "datetime", { readOnly: true }),
  f("status", "enum", { choices: ["pending", "paid", "shipped"] }),
  f("total", "number"),
]);
const SCHEMA: AdminSchema = { models: [ORDERS], byId: { orders: ORDERS } };

/** No date and no enum — refuses the bucket and the group feed. */
const PLAIN = model("notes", "Note", [f("body", "string")]);
const NO_FEED: AdminSchema = { models: [PLAIN], byId: { notes: PLAIN } };

/** Zero models — the only schema that can refuse a count feed ("any model"
 *  is enough to serve one, so nothing short of empty refuses it). */
const EMPTY: AdminSchema = { models: [], byId: {} };

function boot(schema: AdminSchema) {
  app.update((a) => ({ ...a, schema, token: "tkn", apiUrlOverride: "http://api.test" }));
}

async function render(component: any, props = {}) {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  await vi.waitFor(() => {
    flushSync(() => {});
    expect(host.childNodes.length).toBeGreaterThan(0);
  });
  return host;
}

/** Wait for the feed to settle into its final painted state. */
async function paint(host: HTMLElement, want: () => boolean) {
  await vi.waitFor(() => {
    flushSync(() => {});
    expect(want()).toBe(true);
  });
}

const groupRows = (...pairs: Array<[string, number]>) => ({
  count: pairs.reduce((s, [, n]) => s + n, 0),
  results: pairs.flatMap(([status, n]) => Array.from({ length: n }, (_, i) => ({ id: `${status}${i}`, status }))),
  next: null,
});

describe("LiveOrders", () => {
  it("prints the server count as one big live tile, over the discovered listPath with the token", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 42, results: [{ id: 1 }], next: null }));
    const host = await render(LiveOrders);
    await paint(host, () => host.querySelector("[role='status']") !== null);

    const value = host.querySelector("[role='status']")!;
    expect(value.textContent).toBe("42");
    expect(value.getAttribute("aria-label")).toBe("Order: 42 right now");
    expect(host.querySelector(".live-dot")).not.toBeNull(); // the pulsing dot is CSS-only
    expect(host.textContent).toContain("Order · refreshes every 15s");

    // one 1-row page, schema-discovered path + token header, one well-formed URL
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/orders/?page=1&page_size=1");
    expect((init.headers as Record<string, string>).Authorization).toBe("Token tkn");
  });

  it("polls on the engine's 15s cadence — nothing early, nothing after unmount", async () => {
    vi.useFakeTimers();
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 7, results: [{ id: 1 }], next: null }));
    const host = document.createElement("div");
    document.body.append(host);
    try {
      flushSync(() => {
        mounted.push(mount(LiveOrders, { target: host }));
      });
      await vi.advanceTimersByTimeAsync(0);
      flushSync(() => {});
      expect(mockFetch).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(14000);
      expect(mockFetch).toHaveBeenCalledTimes(1); // the widget arms no timer of its own
      await vi.advanceTimersByTimeAsync(1000);
      expect(mockFetch).toHaveBeenCalledTimes(2); // exactly the engine's 15s tick
      unmount(mounted.pop()!);
      await vi.advanceTimersByTimeAsync(180000);
      expect(mockFetch).toHaveBeenCalledTimes(2); // the $effect cleanup killed the poll
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders the nameable reason, zero requests, when no model exists to count", async () => {
    boot(EMPTY);
    const host = await render(LiveOrders);
    await paint(host, () => host.textContent!.includes("no model"));
    expect(host.textContent).toContain("no model in this API has any model to aggregate.");
    expect(host.querySelector("svg, [role='status']")).toBeNull();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("shows the friendly error line when the count feed fails", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ detail: "boom" }, 500));
    const host = await render(LiveOrders);
    await paint(host, () => host.textContent!.includes("Could not load"));
    expect(host.textContent).toContain("Could not load this widget's data.");
  });
});

describe("TodayRevenue", () => {
  it("draws the 7-day window behind the last bucket's value, bars off the day counts", async () => {
    boot(SCHEMA);
    const keys = dayKeys(7);
    mockFetch.mockResolvedValue(
      jsonReply({
        count: 5,
        results: [
          { id: 1, created_at: `${keys[6]}T08:00:00Z` },
          { id: 2, created_at: `${keys[6]}T09:00:00Z` },
          { id: 3, created_at: `${keys[6]}T10:00:00Z` },
          { id: 4, created_at: `${keys[3]}T09:00:00Z` },
          { id: 5, created_at: `${keys[0]}T09:00:00Z` },
        ],
        next: null,
      }),
    );
    const host = await render(TodayRevenue);
    await paint(host, () => host.querySelectorAll("svg rect").length > 0);

    expect(host.querySelector("svg")?.getAttribute("aria-label")).toBe(
      "Records per day, last 7 days — today: 3",
    );
    const rects = [...host.querySelectorAll("svg rect")];
    expect(rects.length).toBe(7); // one bar per day of the window, zeros included
    const height = (r: Element) => Number(r.getAttribute("height"));
    expect(height(rects[6])).toBe(36); // today: 3 of max 3 → the full (H-4) band
    expect(height(rects[0])).toBe(12); // 6 days ago: 1 of 3
    expect(height(rects[5])).toBe(0); // yesterday: zero rows, zero bar
    expect([...host.querySelectorAll("svg rect title")].map((t) => t.textContent)).toEqual([
      `${keys[0]} — 1`, `${keys[1]} — 0`, `${keys[2]} — 0`,
      `${keys[3]} — 1`, `${keys[4]} — 0`, `${keys[5]} — 0`, `${keys[6]} — 3`,
    ]);
    expect(host.textContent).toContain("Order · created at · last 7 days");
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/orders/?page=1&page_size=100");
    expect((init.headers as Record<string, string>).Authorization).toBe("Token tkn");
  });

  it("stays ready on an all-zero window: a flat baseline, a 0 tile, no NaN geometry", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 0, results: [], next: null }));
    const host = await render(TodayRevenue);
    await paint(host, () => host.querySelectorAll("svg rect").length > 0);
    expect([...host.querySelectorAll("svg rect")].every((r) => Number(r.getAttribute("height")) === 0)).toBe(true);
    expect(host.querySelectorAll("svg line").length).toBe(1); // the flat baseline
    expect(host.textContent).toContain("today · Order · created at");
    expect(host.textContent).not.toContain("NaN");
  });

  it("renders the nameable reason, zero requests, when no date field can bucket it", async () => {
    boot(NO_FEED);
    const host = await render(TodayRevenue);
    await paint(host, () => host.textContent!.includes("date or datetime"));
    expect(host.textContent).toContain("no model in this API has a date or datetime field to aggregate.");
    expect(host.querySelector("svg")).toBeNull();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("an instance override pointing at an unknown model refuses with the engine's wording", async () => {
    boot(SCHEMA);
    const host = await render(TodayRevenue, { data: { endpoint: "nope", aggregate: "bucket" } });
    await paint(host, () => host.textContent!.includes("not in this API's schema"));
    expect(host.textContent).toContain('model "nope" is not in this API\'s schema.');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("shows the friendly error line when the bucket feed fails", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ detail: "boom" }, 500));
    const host = await render(TodayRevenue);
    await paint(host, () => host.textContent!.includes("Could not load"));
    expect(host.textContent).toContain("Could not load this widget's data.");
  });
});

describe("CompletionGauge", () => {
  it("sizes one arc off the leading choice's fraction and captions the grouped count", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply(groupRows(["pending", 3], ["paid", 2], ["shipped", 1])));
    const host = await render(CompletionGauge);
    await paint(host, () => host.querySelectorAll("svg circle").length === 2);

    const circles = [...host.querySelectorAll("svg circle")];
    expect(circles[0].getAttribute("stroke-dasharray")).toBeNull(); // [0] is the track
    // pending is 3/6 of the ring — half the circumference, from the top
    expect(circles[1].getAttribute("stroke-dasharray")).toBe(`${((3 / 6) * C).toFixed(2)} ${C.toFixed(2)}`);
    expect(circles[1].getAttribute("stroke-dashoffset")).toBe("0");
    expect(host.querySelector("svg text")?.textContent).toBe("50%");
    expect(host.querySelector("svg")?.getAttribute("aria-label")).toBe("pending 50% of 6");
    const legend = [...host.querySelectorAll("ul li")].map((li) =>
      (li.textContent ?? "").replace(/\s+/g, " ").trim(),
    );
    expect(legend).toEqual(["pending 3", "paid 2", "shipped 1"]); // declared order, no cut needed
    expect(host.textContent).toContain("Order · status · grouped from 6 records");

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/orders/?page=1&page_size=100");
    expect((init.headers as Record<string, string>).Authorization).toBe("Token tkn");
  });

  it("folds every group past the fifth into one (other) legend row", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(
      jsonReply(groupRows(["pending", 5], ["paid", 4], ["shipped", 3], ["refunded", 2], ["canceled", 2], ["held", 1])),
    );
    const host = await render(CompletionGauge);
    await paint(host, () => host.querySelectorAll("ul li").length > 0);
    const legend = [...host.querySelectorAll("ul li")].map((li) =>
      (li.textContent ?? "").replace(/\s+/g, " ").trim(),
    );
    expect(legend.length).toBe(6);
    expect(legend[5]).toContain("(other)");
    expect(legend[5]).toContain("1");
    // "held" is never the leading choice: pending keeps the arc and the name
    expect(host.querySelector("svg")?.getAttribute("aria-label")).toBe("pending 29% of 17");
  });

  it("stays ready on an empty feed: an empty track, an em-dash, and an honest 0-record caption", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 0, results: [], next: null }));
    const host = await render(CompletionGauge);
    await paint(host, () => host.querySelectorAll("svg circle").length === 2);
    expect(host.querySelector("svg text")?.textContent).toBe("—");
    expect(host.querySelectorAll("ul li").length).toBe(0);
    expect(host.textContent).toContain("grouped from 0 records"); // rows.length, not a claimed cap
    expect(host.textContent).not.toContain("NaN");
  });

  it("renders the nameable reason, zero requests, when no enum field can feed it", async () => {
    boot(NO_FEED);
    const host = await render(CompletionGauge);
    await paint(host, () => host.textContent!.includes("enum"));
    expect(host.textContent).toContain("no model in this API has an enum (choices) field to aggregate.");
    expect(host.querySelector("svg")).toBeNull();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("shows the friendly error line when the group feed fails", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply(groupRows(["pending", 1]), 500));
    const host = await render(CompletionGauge);
    await paint(host, () => host.textContent!.includes("Could not load"));
    expect(host.textContent).toContain("Could not load this widget's data.");
  });
});
