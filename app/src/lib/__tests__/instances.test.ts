/** Widget instances — the store, the validation and the threshold engine.
 *
 *  The studio + dashboard mount tests cover the UI wiring; this file grades
 *  the CONTRACT they both rely on: instances validate through the feed
 *  engine's own grammar (a custom widget cannot out-declare a built-in),
 *  persistence is capped plain JSON, import is all-or-nothing, and a notify
 *  rule fires exactly on its promised transitions — never twice for the
 *  same state.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { get } from "svelte/store";
import {
  instances,
  addInstance,
  updateInstance,
  removeInstance,
  moveInstance,
  exportInstances,
  importInstances,
  validateInstance,
  numericValue,
  shouldFire,
  resetInstanceMemory,
  __resetInstancesForTests,
  INSTANCE_CAP,
  type WidgetInstance,
} from "../widgets/instances";
import type { FeedResult } from "../widgets/feed";

beforeEach(() => {
  localStorage.clear();
  __resetInstancesForTests();
  resetInstanceMemory();
});

const base: WidgetInstance = {
  id: "x1",
  type: "TrendArea",
  title: "My trend",
  size: "sm",
  accent: "brand",
  data: { endpoint: "orders", aggregate: "bucket", field: "", days: 7, pollInterval: 0, rowCap: 300 },
  enabled: true,
};

describe("validateInstance", () => {
  it("accepts a minimal draft with defaults", () => {
    const v = validateInstance({ type: "QuoteCard" });
    expect(v).toMatchObject({ instance: { type: "QuoteCard", title: "QuoteCard", size: "sm", accent: "brand", enabled: true } });
  });

  it("refuses non-objects and typeless drafts with a nameable problem", () => {
    expect(validateInstance(null)).toHaveProperty("problem");
    expect(validateInstance([1])).toHaveProperty("problem");
    expect(validateInstance({ title: "no type" }).problem).toContain("type");
  });

  it("refuses unknown accent and unknown notify mode", () => {
    expect(validateInstance({ type: "T", accent: "chartreuse" }).problem).toContain("accent");
    expect(validateInstance({ type: "T", notify: { mode: "explode" } }).problem).toContain("notify mode");
  });

  it("refuses above/below without a finite threshold", () => {
    expect(validateInstance({ type: "T", notify: { mode: "above" } }).problem).toContain("threshold");
    expect(validateInstance({ type: "T", notify: { mode: "below", value: Number.NaN } }).problem).toContain("threshold");
  });

  it("routes the data block through the FEED ENGINE's grammar", () => {
    expect(validateInstance({ type: "T", data: { aggregate: "nope" } }).problem).toContain("unknown aggregate");
    const ok = validateInstance({ type: "T", data: { aggregate: "count" } });
    expect(ok).toHaveProperty("instance");
    if ("instance" in ok) expect(ok.instance.data).toMatchObject({ aggregate: "count" });
  });
});

describe("the instance store", () => {
  it("adds with a fresh id and persists", () => {
    const r = addInstance({ type: "TrendArea", title: "Mine" });
    expect(r).toHaveProperty("instance");
    expect(get(instances)).toHaveLength(1);
    const stored = JSON.parse(localStorage.getItem("dad.widgetInstances.v1") ?? "[]");
    expect(stored[0].title).toBe("Mine");
  });

  it("caps the dashboard and refuses the overflow loudly", () => {
    for (let i = 0; i < INSTANCE_CAP; i++) addInstance({ type: "QuoteCard", title: `c${i}` });
    const r = addInstance({ type: "QuoteCard", title: "overflow" });
    expect(r.problem).toContain("at most");
    expect(get(instances)).toHaveLength(INSTANCE_CAP);
  });

  it("updates merge and REVALIDATE — a bad patch changes nothing", () => {
    const { instance } = addInstance({ type: "TrendArea", title: "Mine" }) as { instance: WidgetInstance };
    const ok = updateInstance(instance.id, { title: "Renamed", size: "lg" });
    expect(ok).toHaveProperty("instance");
    expect(get(instances)[0]).toMatchObject({ title: "Renamed", size: "lg" });
    expect(updateInstance(instance.id, { accent: "chartreuse" }).problem).toContain("accent");
    expect(get(instances)[0].title).toBe("Renamed"); // untouched by the refused patch
  });

  it("removes and reorders by neighbour swap", () => {
    const a = (addInstance({ type: "QuoteCard", title: "A" }) as { instance: WidgetInstance }).instance;
    const b = (addInstance({ type: "QuoteCard", title: "B" }) as { instance: WidgetInstance }).instance;
    const c = (addInstance({ type: "QuoteCard", title: "C" }) as { instance: WidgetInstance }).instance;
    moveInstance(c.id, -1);
    expect(get(instances).map((i) => i.title)).toEqual(["A", "C", "B"]);
    removeInstance(b.id);
    expect(get(instances).map((i) => i.title)).toEqual(["A", "C"]);
  });

  it("export/import round-trips; import is all-or-nothing", () => {
    addInstance({ type: "TrendArea", title: "Mine", data: { aggregate: "count" } });
    const text = exportInstances();
    __resetInstancesForTests();
    expect(get(instances)).toEqual([]);

    expect(importInstances("not json").problem).toContain("JSON");
    expect(importInstances('{"x":1}').problem).toContain("array");
    expect(get(instances)).toEqual([]); // refusals change nothing

    const r = importInstances(text);
    expect(r).toEqual({ added: 1 });
    expect(get(instances)[0]).toMatchObject({ type: "TrendArea", title: "Mine" });

    // one bad entry among good ones: the whole import is refused
    const mixed = JSON.parse(text);
    mixed.push({ type: 42 });
    expect(importInstances(JSON.stringify(mixed)).problem).toContain("type");
    expect(get(instances)).toHaveLength(1); // still the earlier import
  });
});

describe("the threshold engine", () => {
  const num = (value: number | null, label = "orders"): FeedResult =>
    ({ kind: "number", value, label } as FeedResult);

  it("numericValue reads every feed kind", () => {
    expect(numericValue({ kind: "count", value: 7, label: "l" } as FeedResult)).toBe(7);
    expect(numericValue(num(3))).toBe(3);
    expect(numericValue({ kind: "delta", current: 5, previous: 1, pct: 400, label: "l" } as FeedResult)).toBe(5);
    expect(numericValue({ kind: "series", days: ["a", "b"], values: [1, 9], label: "l" } as FeedResult)).toBe(9);
    expect(numericValue({ kind: "groups", groups: [], total: 4, label: "l" } as FeedResult)).toBe(4);
  });

  it("above fires once on crossing, then stays silent while hot", () => {
    const inst: WidgetInstance = { ...base, notify: { mode: "above", value: 10 } };
    expect(shouldFire(inst, num(5)).fire).toBe(false); // cold
    expect(shouldFire(inst, num(12)).fire).toBe(true); // cold -> hot
    expect(shouldFire(inst, num(14)).fire).toBe(false); // still hot
    expect(shouldFire(inst, num(3)).fire).toBe(false); // back cold
    expect(shouldFire(inst, num(11)).fire).toBe(true); // crossing again
    expect(shouldFire(inst, num(null)).fire).toBe(false); // no number, no verdict
  });

  it("below is the mirror image and mentions the threshold in its text", () => {
    const inst: WidgetInstance = { ...base, notify: { mode: "below", value: 2 } };
    const first = shouldFire(inst, num(1));
    expect(first.fire).toBe(true);
    expect(first.text).toContain("below 2");
    expect(shouldFire(inst, num(1)).fire).toBe(false);
  });

  it("change fires once per actual change after a baseline tick", () => {
    const inst: WidgetInstance = { ...base, notify: { mode: "change" } };
    expect(shouldFire(inst, num(5)).fire).toBe(false); // baseline
    expect(shouldFire(inst, num(6)).fire).toBe(true);
    expect(shouldFire(inst, num(6)).fire).toBe(false);
    expect(shouldFire(inst, num(6)).fire).toBe(false); // no drift, no fire
    expect(shouldFire(inst, num(4)).fire).toBe(true);
  });

  it("no rule, no fire; resetInstanceMemory forgets the crossing", () => {
    const quiet: WidgetInstance = { ...base };
    expect(shouldFire(quiet, num(100)).fire).toBe(false);

    const inst: WidgetInstance = { ...base, notify: { mode: "above", value: 10 } };
    shouldFire(inst, num(12));
    resetInstanceMemory();
    expect(shouldFire(inst, num(12)).fire).toBe(true); // cold again after reset
  });
});
