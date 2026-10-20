/** FR-R008 widget data feed tests — validation, schema resolution, pure
 *  aggregation and the polling lifecycle. Fetches go through the real
 *  api.ts with a stubbed global fetch, so "URLs come from the
 *  schema-discovered listPath" is asserted end-to-end, not mocked away. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { app } from "../stores";
import {
  computeAggregate,
  dayKeys,
  resolveTarget,
  runFeedOnce,
  startWidgetFeed,
  validateWidgetData,
  type FeedState,
  type WidgetDataSpec,
} from "../widgets/feed";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function jsonReply(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

function mkField(name: string, type: string, extra: Partial<FieldSpec> = {}): FieldSpec {
  return { name, type: type as FieldSpec["type"], required: false, readOnly: false, ...extra };
}

function mkModel(id: string, name: string, fields: FieldSpec[]): ModelSpec {
  return {
    id,
    name,
    singular: name.toLowerCase(),
    listPath: `/api/${id}/`,
    detailPath: `/api/${id}/{id}/`,
    fields,
    byName: Object.fromEntries(fields.map((f) => [f.name, f])),
    labelField: "id",
  };
}

function schemaOf(...models: ModelSpec[]): AdminSchema {
  return { models, byId: Object.fromEntries(models.map((m) => [m.id, m])) };
}

function spec(patch: Partial<WidgetDataSpec> = {}): WidgetDataSpec {
  return { endpoint: "", field: "", aggregate: "count", days: 14, pollInterval: 0, rowCap: 300, ...patch };
}

const ORDERS = mkModel("orders", "Order", [
  mkField("total", "number", { format: "decimal" }),
  mkField("status", "enum", { choices: ["pending", "paid", "shipped"] }),
  mkField("created_at", "datetime", { readOnly: true }),
]);
const CATS = mkModel("categories", "Category", [mkField("name", "text"), mkField("created_at", "datetime")]);
const SCHEMA = schemaOf(ORDERS, CATS);

beforeEach(() => {
  mockFetch.mockReset();
  app.update((a) => ({ ...a, schema: SCHEMA, token: "tok", apiUrlOverride: "http://api.test" }));
});

describe("validateWidgetData", () => {
  it("accepts a bare object with contract defaults", () => {
    const r = validateWidgetData({});
    expect("spec" in r).toBe(true);
    if ("spec" in r) {
      expect(r.spec.aggregate).toBe("count");
      expect(r.spec.endpoint).toBe("");
      expect(r.spec.pollInterval).toBe(0);
      expect(r.spec.days).toBe(14);
    }
  });

  it("rejects non-objects and unknown aggregates with a nameable reason", () => {
    expect("problem" in validateWidgetData(null)).toBe(true);
    expect("problem" in validateWidgetData("orders")).toBe(true);
    const r = validateWidgetData({ aggregate: "median" });
    expect("problem" in r && r.problem.reason).toContain("median");
  });

  it("clamps pollInterval to the 5s floor and days to [2,366]", () => {
    const r = validateWidgetData({ pollInterval: 10, days: 5000 });
    expect("spec" in r && r.spec.pollInterval).toBe(5000);
    expect("spec" in r && r.spec.days).toBe(366);
    const z = validateWidgetData({ pollInterval: 60000, days: 7 });
    expect("spec" in z && z.spec.pollInterval).toBe(60000);
    const neg = validateWidgetData({ days: -3 });
    expect("spec" in neg && neg.spec.days).toBe(2);
  });
});

describe("resolveTarget", () => {
  it("resolves a declared endpoint + field against the schema", () => {
    const r = resolveTarget(SCHEMA, spec({ endpoint: "orders", field: "total", aggregate: "sum" }));
    expect("model" in r && r.model.id).toBe("orders");
    expect("model" in r && r.field?.name).toBe("total");
  });

  it("refuses an endpoint or field the schema does not carry", () => {
    const a = resolveTarget(SCHEMA, spec({ endpoint: "invoices" }));
    expect("problem" in a && a.problem.reason).toContain("invoices");
    const b = resolveTarget(SCHEMA, spec({ endpoint: "orders", field: "ghost", aggregate: "sum" }));
    expect("problem" in b && b.problem.reason).toContain("ghost");
  });

  it("auto-picks: group -> enum field, bucket -> readOnly created_at, sum -> numeric", () => {
    const g = resolveTarget(SCHEMA, spec({ aggregate: "group" }));
    expect("model" in g && g.model.id).toBe("orders");
    expect("model" in g && g.field?.name).toBe("status");
    const b = resolveTarget(SCHEMA, spec({ aggregate: "bucket" }));
    // readOnly created_at outranks the manual Category.created_at
    expect("model" in b && b.model.id).toBe("orders");
    expect("model" in b && b.field?.name).toBe("created_at");
    const s = resolveTarget(SCHEMA, spec({ aggregate: "sum" }));
    expect("model" in s && s.field?.name).toBe("total");
  });

  it("names the missing shape when nothing can feed the widget", () => {
    const only = schemaOf(mkModel("tags", "Tag", [mkField("label", "text")]));
    const g = resolveTarget(only, spec({ aggregate: "group" }));
    expect("problem" in g && g.problem.reason).toContain("enum");
    const s = resolveTarget(only, spec({ aggregate: "sum" }));
    expect("problem" in s && s.problem.reason).toContain("numeric");
    const e = resolveTarget(schemaOf(), spec({}));
    expect("problem" in e && e.problem.reason).toContain("any model");
  });
});

describe("computeAggregate", () => {
  const target = { model: ORDERS, field: ORDERS.byName["created_at"] };
  const now = new Date(2026, 9, 20, 12, 0, 0); // local — dayKeys is local too

  it("count prefers the server pagination count", () => {
    const r = computeAggregate(spec(), { model: ORDERS, field: null }, [], 42, now);
    expect(r.kind === "count" && r.value).toBe(42);
    const f = computeAggregate(spec(), { model: ORDERS, field: null }, [{ id: 1 }, { id: 2 }], null, now);
    expect(f.kind === "count" && f.value).toBe(2);
  });

  it("sum/avg coerce decimal-as-string and skip blanks", () => {
    const t = { model: ORDERS, field: ORDERS.byName["total"] };
    const rows = [{ total: "19.90" }, { total: "5" }, { total: null }, { total: "" }];
    const s = computeAggregate(spec({ aggregate: "sum" }), t, rows, null, now);
    expect(s.kind === "number" && s.value).toBeCloseTo(24.9);
    const a = computeAggregate(spec({ aggregate: "avg" }), t, rows, null, now);
    expect(a.kind === "number" && a.value).toBeCloseTo(12.45);
    const empty = computeAggregate(spec({ aggregate: "sum" }), t, [], null, now);
    expect(empty.kind === "number" && empty.value).toBe(null);
  });

  it("bucket fills every day key and counts in-window rows only", () => {
    const keys = dayKeys(14, now);
    const rows = [
      { created_at: keys[13] + "T09:00:00Z" },
      { created_at: keys[13] + "T21:00:00Z" },
      { created_at: keys[0] + "T00:00:01Z" },
      { created_at: "2000-01-01T00:00:00Z" }, // out of window — ignored
    ];
    const r = computeAggregate(spec({ aggregate: "bucket", days: 14 }), target, rows, null, now);
    expect(r.kind === "series" && r.values.length).toBe(14);
    expect(r.kind === "series" && r.values[13]).toBe(2);
    expect(r.kind === "series" && r.values[0]).toBe(1);
    expect(r.kind === "series" && r.days[13]).toBe(keys[13]);
  });

  it("group orders by declared choices, appends unseen values, buckets nulls", () => {
    const t = { model: ORDERS, field: ORDERS.byName["status"] };
    const rows = [
      { status: "paid" }, { status: "paid" }, { status: "pending" },
      { status: "archived" }, { status: null },
    ];
    const r = computeAggregate(spec({ aggregate: "group" }), t, rows, null, now);
    expect(r.kind === "groups" && r.total).toBe(5);
    expect(r.kind === "groups" && r.groups.map((g) => g.name)).toEqual(["pending", "paid", "archived", "(unset)"]);
    expect(r.kind === "groups" && r.groups.find((g) => g.name === "shipped")).toBe(undefined);
  });

  it("delta compares the window against the previous one; empty history -> null pct", () => {
    const cur = dayKeys(7, now);
    const prev = dayKeys(7, new Date(now.getTime() - 7 * 86_400_000));
    const rows = [...cur.slice(-3).map((k) => ({ created_at: k })), ...prev.slice(-2).map((k) => ({ created_at: k }))];
    const r = computeAggregate(spec({ aggregate: "delta", days: 7 }), target, rows, null, now);
    expect(r.kind === "delta" && r.current).toBe(3);
    expect(r.kind === "delta" && r.previous).toBe(2);
    expect(r.kind === "delta" && r.pct).toBeCloseTo(50);
    const fresh = computeAggregate(spec({ aggregate: "delta", days: 7 }), target, [{ created_at: cur[6] }], null, now);
    expect(fresh.kind === "delta" && fresh.pct).toBe(null);
  });
});

describe("runFeedOnce", () => {
  it("requests the schema-discovered listPath, never a hand-built URL", async () => {
    mockFetch.mockResolvedValue(jsonReply({ count: 42, results: [], next: null }));
    const r = await runFeedOnce(spec(), { model: ORDERS, field: null });
    expect(r.kind === "count" && r.value).toBe(42);
    const url: string = mockFetch.mock.calls[0][0];
    expect(url).toContain("http://api.test/api/orders/");
    expect(url).toContain("page_size=1");
    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers.Authorization).toBe("Token tok");
  });

  it("pages through rows for non-count aggregates", async () => {
    mockFetch
      .mockResolvedValueOnce(jsonReply({ count: 3, results: [{ id: 1, total: "1" }, { id: 2, total: "2" }], next: "x" }))
      .mockResolvedValueOnce(jsonReply({ count: 3, results: [{ id: 3, total: "3" }], next: null }));
    const t = { model: ORDERS, field: ORDERS.byName["total"] };
    const r = await runFeedOnce(spec({ aggregate: "sum", rowCap: 100 }), t);
    expect(r.kind === "number" && r.value).toBe(6);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

describe("startWidgetFeed lifecycle", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function recorder() {
    const seen: FeedState[] = [];
    return { seen, set: (s: FeedState) => seen.push(s), last: () => seen[seen.length - 1] };
  }

  it("refuses to fetch when the declaration cannot resolve — empty + reason", () => {
    const rec = recorder();
    const stop = startWidgetFeed({ endpoint: "ghost" }, rec.set, SCHEMA);
    expect(rec.last()?.status).toBe("empty");
    expect((rec.last() as any).reason).toContain("ghost");
    expect(mockFetch).not.toHaveBeenCalled();
    stop();
  });

  it("polls at the declared interval and stops dead on cleanup", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValue(jsonReply({ count: 1, results: [], next: null }));
    const rec = recorder();
    const stop = startWidgetFeed({ aggregate: "count", pollInterval: 60000 }, rec.set, SCHEMA);
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.last()?.status).toBe("ready");
    expect(mockFetch).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(59999);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(mockFetch).toHaveBeenCalledTimes(2);

    stop();
    await vi.advanceTimersByTimeAsync(180000);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("a late fetch that lands after stop cannot resurrect the widget", async () => {
    vi.useFakeTimers();
    let resolve: (v: any) => void = () => {};
    mockFetch.mockImplementation(() => new Promise((r) => (resolve = r)));
    const rec = recorder();
    const stop = startWidgetFeed({ aggregate: "count" }, rec.set, SCHEMA);
    await vi.advanceTimersByTimeAsync(0);
    stop();
    resolve(jsonReply({ count: 99, results: [], next: null }));
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.seen.every((s) => s.status !== "ready")).toBe(true);
  });

  it("fetch failure surfaces the error state, not a crash", async () => {
    vi.useRealTimers();
    mockFetch.mockResolvedValue(jsonReply({ detail: "nope" }, 500));
    const rec = recorder();
    const stop = startWidgetFeed({ aggregate: "count" }, rec.set, SCHEMA);
    await vi.waitFor(() => expect(rec.last()?.status).toBe("error"));
    expect((rec.last() as any).message).toBeTruthy();
    stop();
  });
});
