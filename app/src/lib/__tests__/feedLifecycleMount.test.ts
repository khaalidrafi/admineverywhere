/** FR-R008 feed LIFECYCLE proof — what happens around a widget's mount, not inside it.
 *
 *  chartMount.test.ts and widgetMount.test.ts are thorough about the chart a
 *  feed paints, but every one of them does `app.update(schema)` BEFORE
 *  `mount()`. So the reason the widgets use a schema-reactive `$effect` at all
 *  — AGENTS.md: "Widgets render from a schema-reactive `$effect`, not `onMount`
 *  (the schema arrives after mount)", the war story behind `initApp()` loading
 *  the schema asynchronously — was graded by NOTHING. Reverting all five feed
 *  widgets to `onMount` keeps 461 vitest green while the real dashboard shows
 *  five skeletons forever, because in the running app `$app.schema` is null at
 *  mount. Same family as chatMount: a suite that grades a module nobody renders.
 *
 *  The legs here are all about the store changing AROUND a live instance:
 *  1. the schema arriving after mount starts the feed (and pre-schema paints a
 *     skeleton with ZERO requests),
 *  2. a schema swap re-resolves the source — the request moves to the NEW
 *     schema's discovered listPath — and the previous feed's poll timer dies,
 *  3. a mistyped 100 ms pollInterval is floored to 5 s by the RENDERED widget
 *     (unit tests graded the value validateWidgetData returns; nothing graded
 *     the timer the browser actually arms),
 *  4. a swap that removes a pinned model renders the nameable refusal and
 *     NOTHING keeps polling the vanished model,
 *  5. a `<script module>` declaration the engine refuses (aggregate "median")
 *     comes out as a friendly empty with zero requests, through a real
 *     component rather than a hand-built spec object,
 *  6. the harness's own domain: the two probe fixtures still carry the hostile
 *     declarations these legs depend on, and neither leaked into the shipped
 *     widget glob.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import TrendArea from "../../widgets/TrendArea.svelte";
import DeltaChip from "../../widgets/DeltaChip.svelte";
import FeedProbe from "./fixtures/FeedProbe.svelte";
import BadDeclProbe from "./fixtures/BadDeclProbe.svelte";
import { widgets } from "../../widgets";
import { app } from "../stores";
import { dayKeys } from "../widgets/feed";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

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

const ORDERS = model("orders", "Order", [
  f("created_at", "datetime", { readOnly: true }),
  f("status", "enum", { choices: ["pending", "paid"] }),
]);
/** The other half of every swap: a model set that does NOT contain "orders". */
const INVOICES = model("invoices", "Invoice", [f("issued_at", "datetime", { readOnly: true })]);

const ORDERS_ONLY: AdminSchema = { models: [ORDERS], byId: { orders: ORDERS } };
const INVOICES_ONLY: AdminSchema = { models: [INVOICES], byId: { invoices: INVOICES } };

function boot(schema: AdminSchema | null) {
  app.update((a) => ({ ...a, schema, token: "tkn", apiUrlOverride: "http://api.test" }));
}

function render(component: any): HTMLElement {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host }));
  });
  return host;
}

/** Flush fake timers (or microtasks) and let Svelte paint. */
async function settle(ms = 0) {
  await vi.advanceTimersByTimeAsync(ms);
  flushSync(() => {});
}

const urls = () => mockFetch.mock.calls.map((c) => String(c[0]));

describe("the schema arrives after the widget mounts", () => {
  it("paints its skeleton and asks for NOTHING until a schema exists", () => {
    boot(null);
    const host = render(TrendArea);
    expect(host.querySelector(".skeleton"), "a schema-less widget must show its own loading state").not.toBeNull();
    expect(mockFetch, "a widget fetched before any schema existed").not.toHaveBeenCalled();
  });

  it("starts the feed when the schema lands on a LIVE instance (the $effect law, not onMount)", async () => {
    boot(null);
    const host = render(TrendArea);
    const keys = dayKeys(30);
    mockFetch.mockResolvedValue(
      jsonReply({
        count: 2,
        results: [
          { id: 1, created_at: `${keys[29]}T10:00:00Z` },
          { id: 2, created_at: `${keys[29]}T11:00:00Z` },
        ],
        next: null,
      }),
    );
    // the real app's order of events: mount, THEN initApp() hands over the schema
    boot(ORDERS_ONLY);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.querySelectorAll("svg circle").length, "the feed never restarted when the schema arrived").toBeGreaterThan(0);
    });
    expect(host.textContent).toContain("Order · created at");
    expect(urls()).toEqual(["http://api.test/api/orders/?page=1&page_size=100"]);
    expect((mockFetch.mock.calls[0] as [string, RequestInit])[1].headers as Record<string, string>).toMatchObject({
      Authorization: "Token tkn",
    });
  });

  it("a live schema swap moves the request to the NEW schema's listPath and leaves no old poll running", async () => {
    vi.useFakeTimers();
    boot(ORDERS_ONLY);
    const host = render(DeltaChip);
    mockFetch.mockResolvedValue(jsonReply({ count: 0, results: [], next: null }));
    await settle();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(urls()[0]).toContain("/api/orders/");
    await settle(60_000); // DeltaChip's declared 60 s poll, alive on orders
    expect(mockFetch).toHaveBeenCalledTimes(2);

    boot(INVOICES_ONLY); // the user re-points the client at another API
    await settle();
    expect(host.textContent, "the swapped feed did not paint from the new schema").toContain("Invoice");
    const after = urls();
    expect(after[2]).toContain("/api/invoices/");

    await settle(120_000);
    const all = urls();
    expect(all.filter((u) => u.includes("/api/orders/")), "the previous feed's poll timer survived the swap").toHaveLength(2);
    expect(all.slice(2).every((u) => u.includes("/api/invoices/"))).toBe(true);
    expect(all.filter((u) => u.includes("/api/invoices/")).length, "the new feed does not poll on its own timer").toBeGreaterThanOrEqual(3);
  });
});

describe("a widget's own declaration cannot run away with the API", () => {
  it("a mistyped 100 ms pollInterval is floored to 5 s in the RENDERED widget", async () => {
    vi.useFakeTimers();
    boot(ORDERS_ONLY);
    render(FeedProbe);
    mockFetch.mockResolvedValue(jsonReply({ count: 7, results: [], next: null }));
    await settle();
    expect(mockFetch).toHaveBeenCalledTimes(1);

    await settle(4_000);
    expect(mockFetch, "a 100 ms poll would have fired ~40 times by now — the 5 s floor is not applied").toHaveBeenCalledTimes(1);

    await settle(1_500);
    expect(mockFetch, "the floored 5 s poll never re-armed").toHaveBeenCalledTimes(2);
  });

  it("a swap that removes the pinned model renders the reason and stops every poll", async () => {
    vi.useFakeTimers();
    boot(ORDERS_ONLY);
    const host = render(FeedProbe);
    mockFetch.mockResolvedValue(jsonReply({ count: 7, results: [], next: null }));
    await settle();
    await settle(5_000);
    expect(mockFetch).toHaveBeenCalledTimes(2); // poll alive on "orders"

    boot(INVOICES_ONLY); // "orders" is gone from the schema
    await settle();
    const empty = host.querySelector("[data-state='empty']");
    expect(empty, `widget rendered ${host.textContent?.slice(0, 80)} instead of a refusal`).not.toBeNull();
    expect(empty!.textContent).toContain('model "orders" is not in this API\'s schema');

    await settle(300_000);
    expect(urls(), "the vanished model is still being polled").toEqual([
      "http://api.test/api/orders/?page=1&page_size=1",
      "http://api.test/api/orders/?page=1&page_size=1",
    ]);
  });

  it("a <script module> declaration the engine refuses is a friendly empty with zero requests", async () => {
    boot(ORDERS_ONLY);
    const host = render(BadDeclProbe);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.querySelector("[data-state='empty']"), host.textContent ?? "nothing painted").not.toBeNull();
    });
    expect(host.textContent).toContain('unknown aggregate "median"');
    expect(mockFetch, "a refused declaration still hit the network").not.toHaveBeenCalled();
  });
});

/** The declarations these legs depend on, read as shipped text rather than as a
 *  hand-built spec object — so a fixture quietly "fixed" (100 → 5000) or a probe
 *  leaked into the product glob is red here instead of silently ungrading a leg. */
describe("this harness can see its own fixtures", () => {
  const sources = import.meta.glob("./fixtures/*Probe.svelte", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const textOf = (name: string) => {
    const hit = Object.entries(sources).find(([key]) => key.endsWith(name));
    expect(hit, `${name} left the fixture domain`).not.toBeUndefined();
    return hit![1];
  };

  it("the probes still carry the hostile declarations", () => {
    const feed = textOf("FeedProbe.svelte");
    expect(feed).toContain("pollInterval: 100");
    expect(feed).toContain('endpoint: "orders"');
    expect(feed).toContain('aggregate: "count"');
    expect(textOf("BadDeclProbe.svelte")).toContain('aggregate: "median"');
    expect(Object.keys(sources), "the fixture domain is not exactly the two probes").toHaveLength(2);
  });

  it("neither probe joined the shipped widget registry", () => {
    const titles = widgets.map((w) => w.title);
    expect(titles.filter((t) => t.includes("Probe")), "a test probe leaked into the product glob").toEqual([]);
    expect(widgets.length, "the widget glob collapsed; the registry legs prove nothing").toBeGreaterThan(0);
  });
});
