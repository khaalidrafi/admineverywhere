/** FR-R008 feed contract, graded through the REAL grid.
 *
 *  Before this file the mounted proof was two components imported by name
 *  (widgetMount.test.ts) plus a schema-less grid (dashboardMount.test.ts).
 *  What no reviewer could see: whether the `data` block the widget registry
 *  globs off `meta.data` ever reaches the engine, whether EVERY data-fed
 *  widget paints (not just the two hand-picked ones), whether a refusal
 *  renders its nameable reason as DOM a user reads, and whether a widget
 *  wakes when the schema arrives after mount — the exact `$effect`-not-
 *  `onMount` law AGENTS.md records for widgets.
 *
 *  Nothing here imports a chart component: the widgets come out of the same
 *  `widgets[]` glob Dashboard renders, so a drop-in that cannot feed fails
 *  the way a user sees it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import Dashboard from "../../pages/Dashboard.svelte";
import { widgets } from "../../widgets";
import { app } from "../stores";
import { dayKeys, validateWidgetData, type WidgetDataSpec } from "../widgets/feed";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

const BASE = "http://feed.test";
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
let host: HTMLElement;

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  mockFetch.mockReset();
  app.update((a) => ({ ...a, schema: null, apiUrlOverride: "" }));
});

function jsonReply(rows: any[], count: number | null = null) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ count: count ?? rows.length, results: rows, next: null }),
    text: async () => JSON.stringify({ count: count ?? rows.length, results: rows, next: null }),
  };
}

const f = (name: string, type: string, extra: Partial<FieldSpec> = {}): FieldSpec =>
  ({ name, type: type as FieldSpec["type"], required: false, readOnly: false, ...extra });

function model(id: string, name: string, fields: FieldSpec[]): ModelSpec {
  const m: ModelSpec = {
    id,
    name,
    singular: name.toLowerCase(),
    listPath: `/api/${id}/`,
    detailPath: `/api/${id}/{id}/`,
    fields,
    byName: Object.fromEntries(fields.map((x) => [x.name, x])),
    labelField: "id",
  };
  return m;
}

/** The rig's shape: an Order with a server-written timestamp and a status
 *  enum — everything a bucket/group/delta feed auto-picks without a name
 *  being declared anywhere in the widget. */
const FEEDABLE: AdminSchema = (() => {
  const orders = model("orders", "Order", [
    f("id", "number"),
    f("created_at", "datetime", { readOnly: true }),
    f("status", "enum", { choices: ["pending", "paid", "shipped"] }),
    f("total", "number"),
  ]);
  return { models: [orders], byId: { orders } };
})();

/** A schema that can feed NOTHING. With a count-fed tile in the registry
 *  (LiveOrders: "any model" is enough to serve a count) that means literally
 *  zero models — one bare model would feed the count tile happily, and this
 *  sweep grades EVERY FED widget's refusal, not a hand-picked subset. */
const UNFEEDABLE: AdminSchema = { models: [], byId: {} };

/** Rows spread over both delta windows, with every status the enum declares. */
function feedableRows() {
  const keys = dayKeys(35);
  const today = keys[keys.length - 1];
  const twoAgo = keys[keys.length - 3];
  const lastWeek = keys[keys.length - 12];
  return [
    { id: 1, created_at: `${today}T08:00:00Z`, status: "pending", total: "10.00" },
    { id: 2, created_at: `${today}T09:00:00Z`, status: "pending", total: "5.50" },
    { id: 3, created_at: `${today}T10:00:00Z`, status: "paid", total: "7.25" },
    { id: 4, created_at: `${twoAgo}T08:00:00Z`, status: "paid", total: "3.00" },
    { id: 5, created_at: `${twoAgo}T11:00:00Z`, status: "shipped", total: "1.00" },
    { id: 6, created_at: `${lastWeek}T08:00:00Z`, status: "pending", total: "2.00" },
  ];
}

/** Widgets the glob found that declare a feed — the domain of this harness. */
const FED = widgets
  .filter((w) => (w.data as WidgetDataSpec | undefined)?.aggregate)
  .map((w) => ({ ...w, spec: w.data as WidgetDataSpec }));

function renderGrid(schema: AdminSchema | null): HTMLElement {
  app.update((a) => ({ ...a, schema, token: "", apiUrlOverride: BASE }));
  host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(Dashboard, { target: host }));
  });
  return host;
}

/** Cells addressed through the grid by their registry title, so a widget that
 *  never reached the grid is a miss naming itself instead of an undefined. */
function cellFor(title: string): HTMLElement {
  const cell = [...host.querySelectorAll(".grid > div")].find(
    (c) => (c.querySelector("h2")?.textContent ?? "").trim() === title,
  );
  expect(cell, `grid rendered no cell titled "${title}"`).not.toBeUndefined();
  return cell as HTMLElement;
}

const skeleton = (el: HTMLElement) => el.querySelector(".skeleton") !== null;
const chartDom = (el: HTMLElement) =>
  el.querySelector("svg, [role='status'], li, span[title]") !== null;
const reasonLine = (el: HTMLElement) =>
  [...el.querySelectorAll("div, span, p")]
    .map((n) => (n.textContent ?? "").trim())
    .filter((t) => t.startsWith("no model in this API has"))[0] ?? "";

function requestedPaths(): string[] {
  return mockFetch.mock.calls.map((call) => {
    const url = new URL(String(call[0]));
    return url.pathname + url.search;
  });
}

describe("FR-R008: the globbed feed declaration reaches the engine through the grid", () => {
  function oneFedBy(what: string, pred: (w: (typeof FED)[number]) => boolean): (typeof FED)[number] {
    const hit = FED.find(pred);
    expect(hit, `no data-fed widget matches ${what} — the feed domain moved`).toBeTruthy();
    return hit!;
  }

  it("the registry carries a non-trivial feed domain", () => {
    // Population pin first: a collapsed glob or a registry that stopped
    // exporting `data` would make every assertion below grade nothing.
    expect(FED.length, "widgets declaring meta.data collapsed").toBeGreaterThanOrEqual(4);
    const kinds = new Set(FED.map((w) => w.spec.aggregate));
    for (const kind of ["bucket", "group", "delta"]) {
      expect(kinds.has(kind as any), `no built-in widget feeds by "${kind}" anymore`).toBe(true);
    }
    for (const w of FED) {
      // every shipped declaration obeys the contract it is read with
      expect(validateWidgetData(w.data), `"${w.title}" declares an invalid meta.data`).toHaveProperty("spec");
    }
  });

  it("every data-fed widget paints chart DOM from the schema-resolved feed", async () => {
    mockFetch.mockResolvedValue(jsonReply(feedableRows()));
    renderGrid(FEEDABLE);

    await vi.waitFor(() => {
      flushSync(() => {});
      for (const w of FED) {
        const cell = cellFor(w.title);
        expect(skeleton(cell), `"${w.title}" is still a skeleton`).toBe(false);
        expect(reasonLine(cell), `"${w.title}" refused a feed the schema can serve`).toBe("");
        expect(chartDom(cell), `"${w.title}" rendered no chart DOM`).toBe(true);
      }
    });

    // the buckets and the groups are the engine's output, seen as text
    const heat = cellFor(oneFedBy("the 35-day bucket", (w) => w.spec.aggregate === "bucket" && w.spec.days === 35).title);
    expect(heat.querySelectorAll("span[title]").length, "heat strip lost its day cells").toBe(35);
    const bars = cellFor(oneFedBy("an enum-group feed", (w) => w.spec.aggregate === "group").title);
    for (const status of ["pending", "paid", "shipped"]) {
      expect(bars.textContent, `group "${status}" never rendered`).toContain(status);
    }
    expect(bars.textContent, "grouped row count never surfaced").toContain("6");
    const chip = cellFor(oneFedBy("a delta feed", (w) => w.spec.aggregate === "delta").title);
    expect(chip.textContent, "delta chip rendered no window comparison").toContain("5 vs 1");
  });

  it("every feed request is base + the schema-discovered listPath, never a hand-built URL", async () => {
    mockFetch.mockResolvedValue(jsonReply(feedableRows()));
    renderGrid(FEEDABLE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(mockFetch.mock.calls.length).toBeGreaterThan(0);
      expect(FED.every((w) => !skeleton(cellFor(w.title)))).toBe(true);
    });

    const allowed = FEEDABLE.models.map((m) => m.listPath);
    const hrefs = mockFetch.mock.calls.map((call) => String(call[0]));
    for (const p of requestedPaths()) {
      const [pathname] = p.split("?");
      expect(allowed.includes(pathname), `a feed requested the undeclared path ${pathname}`).toBe(true);
    }
    // the base join is part of the same law: apiUrl + listPath must stay one
    // well-formed origin+path (AGENTS.md records `http://hostapi…` — a dropped
    // separator silently breaks every call and no per-side unit test sees it)
    for (const href of hrefs) {
      expect(href, `feed request left the configured origin: ${href}`).toMatch(
        /^http:\/\/feed\.test\/api\/orders\/(\?[\w=&%.-]*)?$/,
      );
    }
    // polling widgets ask for pages, so a feed that guessed a whole-row path
    // (detail/export/custom segment) is visible as an unlisted pathname
    expect(hrefs.some((h) => /page=\d+/.test(h)), "no feed paginated through api.ts").toBe(true);
  });

  it("a widget wakes when the schema lands after mount (the $effect law)", async () => {
    mockFetch.mockResolvedValue(jsonReply(feedableRows()));
    renderGrid(null);
    // schema-less boot: the grid paints its placeholders and sends nothing
    expect(mockFetch.mock.calls.length, "the grid fetched without a schema").toBe(0);

    const schema = FEEDABLE;
    app.update((a) => ({ ...a, schema }));
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(mockFetch.mock.calls.length, "a late schema never woke the feeds").toBeGreaterThan(0);
      for (const w of FED) expect(chartDom(cellFor(w.title)), `"${w.title}" stayed dead`).toBe(true);
    });
  });

  it("an unfeedable schema renders each widget's nameable reason as DOM", async () => {
    mockFetch.mockResolvedValue(jsonReply([{ id: 1, body: "hi" }]));
    renderGrid(UNFEEDABLE);

    const wantByKind: Record<string, string> = {
      group: "enum (choices) field",
      bucket: "a date or datetime field",
      delta: "a date or datetime field",
    };
    await vi.waitFor(() => {
      flushSync(() => {});
      for (const w of FED) {
        const cell = cellFor(w.title);
        expect(skeleton(cell), `"${w.title}" is still loading on a refused feed`).toBe(false);
        const said = reasonLine(cell);
        // the engine's wording, not a component's "no data": the reason is the
        // promise AGENTS.md:41 makes ("friendly empty with a nameable reason")
        expect(said, `"${w.title}" hid its refusal`).toContain(wantByKind[w.spec.aggregate] ?? "no model");
        expect(said, `"${w.title}" says "${said}"`).toContain("no model in this API has");
        expect(chartDom(cell), `"${w.title}" painted a chart over its own refusal`).toBe(false);
      }
    });

    // a refusal opens NO new URL: whatever was requested is still a
    // schema-discovered listPath (a guessed /api/trend/ would land here)
    const allowed = UNFEEDABLE.models.map((m) => m.listPath);
    for (const p of requestedPaths()) {
      const [pathname] = p.split("?");
      expect(allowed.includes(pathname), `a refused feed requested ${pathname}`).toBe(true);
    }
  });

  it("a refused feed stays refused quietly: one render, no retry barrage", async () => {
    mockFetch.mockResolvedValue(jsonReply([{ id: 1, body: "hi" }]));
    renderGrid(UNFEEDABLE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(FED.every((w) => reasonLine(cellFor(w.title)) !== "")).toBe(true);
    });
    const before = mockFetch.mock.calls.length;
    // startWidgetFeed returns a no-op stop and schedules nothing, so the
    // count cannot move while the reason sits on screen
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(mockFetch.mock.calls.length, "a refused feed kept hammering the API").toBe(before);
    });
  });
});
