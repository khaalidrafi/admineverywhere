/** FR-R008 chart-widget wire proof — the four chart components that render
 *  a feed but were never mounted: StatusDonut, LeaderBars, TrendArea,
 *  ActivityChart. Same harness as widgetMount.test.ts (browser resolve
 *  condition + manual flushSync). Pure-module tests over feed.ts stay green
 *  while a chart maps the wrong field, draws the wrong slice geometry or
 *  guesses a URL — so the assertions here are DOM- and request-level, judged
 *  through the component. ActivityChart is the last hand-rolled chart (it
 *  bypasses the feed engine), so its OWN model-picker (readOnly created_at
 *  wins) and its 3-page walk get pinned here too. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import StatusDonut from "../../widgets/StatusDonut.svelte";
import LeaderBars from "../../widgets/LeaderBars.svelte";
import TrendArea from "../../widgets/TrendArea.svelte";
import ActivityChart from "../../widgets/ActivityChart.svelte";
import { app } from "../stores";
import { dayKeys } from "../widgets/feed";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const C = 2 * Math.PI * 42; // the donut's own circumference (r=42)

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

/** Schema that can feed every chart: an enum field + a readOnly created_at. */
const ORDERS = model("orders", "Order", [
  f("created_at", "datetime", { readOnly: true }),
  f("status", "enum", { choices: ["pending", "paid", "shipped", "refunded"] }),
]);
const SCHEMA: AdminSchema = { models: [ORDERS], byId: { orders: ORDERS } };

/** A second timestamped model whose fields rank worse — the picker must
 *  still choose the readOnly created_at on the first model. */
const SHIPMENTS = model("shipments", "Shipment", [
  f("created_at", "datetime"),
  f("timestamp", "datetime", { readOnly: true }),
]);
const TWO_MODELS: AdminSchema = {
  models: [ORDERS, SHIPMENTS],
  byId: { orders: ORDERS, shipments: SHIPMENTS },
};

/** Nothing dateish and no enum — both refusal paths in one schema. */
const PLAIN = model("notes", "Note", [f("body", "string")]);
const NO_FEED: AdminSchema = { models: [PLAIN], byId: { notes: PLAIN } };

function boot(schema: AdminSchema) {
  app.update((a) => ({ ...a, schema, token: "tkn", apiUrlOverride: "http://api.test" }));
}

async function render(component: any) {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host }));
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

const legendOf = (host: HTMLElement) =>
  [...host.querySelectorAll("ul li")].map((li) => (li.textContent ?? "").replace(/\s+/g, " ").trim());

describe("StatusDonut", () => {
  it("draws one slice per group with exact dash geometry and the total in the middle", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(
      jsonReply(groupRows(["pending", 8], ["paid", 3], ["shipped", 1], ["canceled", 2])),
    );
    const host = await render(StatusDonut);
    await paint(host, () => host.querySelectorAll("svg circle").length === 5);

    const slices = [...host.querySelectorAll("svg circle")].slice(1); // [0] is the ring
    expect(slices.length).toBe(4); // zero-count declared choices are dropped, unseen values appended
    const legend = legendOf(host);
    expect(legend.map((l) => l.split(" ")[0])).toEqual(["pending", "paid", "shipped", "canceled"]);
    expect(legend[0]).toContain("8");
    expect(legend[3]).toContain("2");
    // geometry: pending is 8/14 of the ring at offset 0; paid starts one 8/14 turn later
    const dash = (i: number) => slices[i].getAttribute("stroke-dasharray")!;
    const offset = (i: number) => slices[i].getAttribute("stroke-dashoffset")!;
    expect(dash(0).split(" ")[0]).toBe(((8 / 14) * C).toFixed(2));
    expect(offset(0)).toBe("0.00");
    expect(offset(1)).toBe((-(8 / 14) * C).toFixed(2));
    expect(host.querySelector("svg text")?.textContent).toBe("14");

    // and the request went through the schema-discovered path, token and all
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/orders/?page=1&page_size=100");
    expect((init.headers as Record<string, string>).Authorization).toBe("Token tkn");
  });

  it("folds every group past the fifth into one (other) slice", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(
      jsonReply(groupRows(["pending", 5], ["paid", 4], ["shipped", 3], ["refunded", 2], ["canceled", 2], ["held", 1])),
    );
    const host = await render(StatusDonut);
    await paint(host, () => host.querySelectorAll("svg circle").length === 7);
    const legend = legendOf(host);
    expect(legend.length).toBe(6);
    expect(legend[5]).toContain("(other)");
    expect(legend[5]).toContain("1"); // "held" — the only group past the cut
    expect(legend.slice(0, 5).every((l) => !l.includes("(other)"))).toBe(true);
    expect(host.querySelector("svg text")?.textContent).toBe("17");
  });

  it("renders the nameable reason, zero requests, when no enum field can feed it", async () => {
    boot(NO_FEED);
    const host = await render(StatusDonut);
    await paint(host, () => host.textContent!.includes("enum"));
    expect(host.textContent).toContain("no model in this API has an enum (choices) field to aggregate.");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("shows the friendly error line when the feed fails", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ detail: "boom" }, 500));
    const host = await render(StatusDonut);
    await paint(host, () => host.textContent!.includes("Could not load"));
    expect(host.textContent).toContain("Could not load this widget's data.");
  });
});

describe("LeaderBars", () => {
  it("sorts bars by value descending, cuts after six, widths are percent-of-max", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(
      jsonReply(groupRows(["pending", 10], ["paid", 5], ["shipped", 7], ["refunded", 1], ["canceled", 2], ["held", 3], ["archived", 4])),
    );
    const host = await render(LeaderBars);
    await paint(host, () => host.querySelectorAll("ul li").length > 0);
    const lis = [...host.querySelectorAll("ul li")];
    expect(lis.length).toBe(6);
    expect(lis.map((li) => li.querySelector("span")!.textContent)).toEqual([
      "pending", "shipped", "paid", "archived", "held", "canceled",
    ]);
    const widthOf = (li: Element) => li.querySelector("div[style]")?.getAttribute("style") ?? "";
    expect(widthOf(lis[0])).toMatch(/^width:\s*100%/); // max sets the scale
    expect(widthOf(lis[2])).toMatch(/^width:\s*50%/); // 5 of 10, rounded
    expect(host.textContent).toContain("Order · status");
  });

  it("names the rows it grouped, without claiming a cap that was not applied", async () => {
    boot(SCHEMA);
    const rows = Array.from({ length: 50 }, (_, i) => ({ id: i, status: i % 2 ? "pending" : "paid" }));
    mockFetch.mockResolvedValue(jsonReply({ count: 50, results: rows, next: null }));
    const host = await render(LeaderBars);
    await paint(host, () => host.textContent!.includes("records"));
    // The number is the rows aggregated, not a truncation: 50 < the 300 rowCap,
    // so the old copy "first 50 records" asserted a cap this feed never applied.
    expect(host.textContent).toContain("grouped from 50 records");
    expect(host.textContent).not.toContain("first");
  });

  it("when the rowCap IS the limit the caption names the capped count — 300 from an endless server", async () => {
    boot(SCHEMA);
    // Server whose `next` never ends: only a component that genuinely obeys
    // rowCap stops at 300. A well-behaved fixture would prove the server, not
    // the guard (14:01Z note), so this one paginates forever.
    let pages = 0;
    mockFetch.mockImplementation(async () => {
      pages++;
      return jsonReply({
        count: 99_999,
        results: Array.from({ length: 100 }, (_, i) => ({ id: `${pages}-${i}`, status: "pending" })),
        next: `http://api.test/api/orders/?page=${pages + 1}`,
      });
    });
    const host = await render(LeaderBars);
    await paint(host, () => host.textContent!.includes("records"));
    expect(host.textContent).toContain("grouped from 300 records");
    expect(pages).toBe(3); // pageSize 100 × 3 = the default rowCap, then stop walking
  });

  it("renders the nameable reason, zero requests, when no enum field can feed it", async () => {
    boot(NO_FEED);
    const host = await render(LeaderBars);
    await paint(host, () => host.textContent!.includes("enum"));
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("TrendArea", () => {
  it("plots the 30-day bucket: point circles match the day keys and counts", async () => {
    boot(SCHEMA);
    const keys = dayKeys(30);
    const rows = [
      { id: 1, created_at: `${keys[29]}T10:00:00Z` },
      { id: 2, created_at: `${keys[29]}T11:00:00Z` },
      { id: 3, created_at: `${keys[20]}T09:00:00Z` },
    ];
    mockFetch.mockResolvedValue(jsonReply({ count: 3, results: rows, next: null }));
    const host = await render(TrendArea);
    await paint(host, () => host.querySelectorAll("svg circle").length > 0);
    expect(host.querySelector("svg")?.getAttribute("aria-label")).toBe("Records per day, last 30 days");
    const titles = [...host.querySelectorAll("svg circle title")].map((t) => t.textContent);
    expect(titles).toEqual([`${keys[20]} — 1`, `${keys[29]} — 2`]); // zero days get no point
    expect(host.querySelector("path[stroke]")?.getAttribute("d")).toMatch(/^M8\.0,/);
    const axis = [...host.querySelectorAll("span")].map((s) => s.textContent);
    expect(axis).toContain(keys[0]);
    expect(host.textContent).toContain("Order · created at");
    const [url] = mockFetch.mock.calls[0] as [string];
    expect(url).toBe("http://api.test/api/orders/?page=1&page_size=100");
  });

  it("falls back to a flat baseline when the window is all zeros", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 0, results: [], next: null }));
    const host = await render(TrendArea);
    await paint(host, () => host.querySelectorAll("svg line").length > 0);
    expect(host.querySelectorAll("svg circle").length).toBe(0);
    expect(host.querySelectorAll("svg path").length).toBe(0);
  });
});

describe("ActivityChart (hand-rolled — bypasses the feed engine)", () => {
  it("picks the readOnly created_at model, walks max 3 pages and buckets by day", async () => {
    boot(TWO_MODELS);
    const keys = dayKeys(14);
    mockFetch.mockImplementation(async (url: string) => {
      const n = Number(new URL(url).searchParams.get("page"));
      return jsonReply({
        count: 300,
        results: Array.from({ length: 100 }, (_, i) => ({ id: n * 100 + i, created_at: `${keys[13]}T12:00:00Z` })),
        next: n < 3 ? "http://api.test/api/orders/?page=more" : null,
      });
    });
    const host = await render(ActivityChart);
    await paint(host, () => host.querySelectorAll("svg circle").length > 0);
    expect(mockFetch.mock.calls.map((c) => c[0])).toEqual([
      "http://api.test/api/orders/?page=1",
      "http://api.test/api/orders/?page=2",
      "http://api.test/api/orders/?page=3",
    ]);
    const titles = [...host.querySelectorAll("svg circle title")].map((t) => t.textContent);
    expect(titles).toEqual(["300 on day -0"]);
    expect(host.textContent).toContain("Order by created at · first pages only");
    unmount(mounted.pop()!);
    // and the 3-page cap is the component's own, not the fixture's courtesy:
    // a server that never ends its pagination must still be walked at most 3x
    mockFetch.mockReset();
    mockFetch.mockImplementation(async () =>
      jsonReply({
        count: 999,
        results: Array.from({ length: 100 }, (_, i) => ({ id: i, created_at: `${keys[13]}T12:00:00Z` })),
        next: "http://api.test/api/orders/?page=more",
      }),
    );
    const host2 = await render(ActivityChart);
    await paint(host2, () => host2.querySelectorAll("svg circle").length > 0);
    expect(mockFetch.mock.calls.length).toBe(3);
    expect([...host2.querySelectorAll("svg circle title")].map((t) => t.textContent)).toEqual([
      "300 on day -0",
    ]);
  });

  it("refuses with a friendly line, zero requests, when no timestamped model exists", async () => {
    boot(NO_FEED);
    const host = await render(ActivityChart);
    await paint(host, () => host.textContent!.includes("No timestamped model"));
    expect(host.textContent).toContain("No timestamped model found in the schema.");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("renders the error copy when the page walk fails", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ detail: "nope" }, 500));
    const host = await render(ActivityChart);
    await paint(host, () => host.textContent!.includes("Could not load"));
    expect(host.textContent).toContain("Could not load activity data.");
  });
});
