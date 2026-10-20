/** FR-R008 mounted-widget proof — a real chart component rendered from a
 *  real feed. Same harness as shell.test.ts (browser resolve condition +
 *  manual flushSync); this time it proves the drop-in data contract paints
 *  DOM: meta.data resolves against $app.schema, fetches through api.ts and
 *  the SVG/cells land in the document. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import HeatStrip from "../../widgets/HeatStrip.svelte";
import DeltaChip from "../../widgets/DeltaChip.svelte";
import { app } from "../stores";
import { dayKeys } from "../widgets/feed";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  mockFetch.mockReset();
});

function jsonReply(data: any) {
  return { ok: true, status: 200, json: async () => data, text: async () => JSON.stringify(data) };
}

const f = (name: string, type: string, extra: Partial<FieldSpec> = {}): FieldSpec =>
  ({ name, type: type as FieldSpec["type"], required: false, readOnly: false, ...extra });
const ORDERS: ModelSpec = {
  id: "orders",
  name: "Order",
  singular: "order",
  listPath: "/api/orders/",
  detailPath: "/api/orders/{id}/",
  fields: [f("created_at", "datetime", { readOnly: true }), f("status", "enum", { choices: ["pending", "paid"] })],
  byName: {},
  labelField: "id",
};
ORDERS.byName = Object.fromEntries(ORDERS.fields.map((x) => [x.name, x]));
const SCHEMA: AdminSchema = { models: [ORDERS], byId: { orders: ORDERS } };

async function render(component: any, props = {}) {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  // let the feed's fetch promise settle, then paint
  await vi.waitFor(() => {
    flushSync(() => {});
    expect(host.querySelector("svg, [role='status'], [role='img']")).not.toBeNull();
  });
  return host;
}

describe("mounted feed widgets", () => {
  it("HeatStrip renders 35 day cells from the bucketed feed", async () => {
    app.update((a) => ({ ...a, schema: SCHEMA, token: "", apiUrlOverride: "http://api.test" }));
    const today = dayKeys(1)[0];
    mockFetch.mockResolvedValue(
      jsonReply({ count: 2, results: [{ id: 1, created_at: `${today}T08:00:00Z` }, { id: 2, created_at: `${today}T09:00:00Z` }], next: null }),
    );
    const host = await render(HeatStrip);
    const cells = [...host.querySelectorAll("span[title]")];
    expect(cells.length).toBe(35);
    expect(cells.some((c) => (c.getAttribute("title") ?? "").endsWith("— 2"))).toBe(true);
    expect(host.textContent).toContain("Order");
    expect(mockFetch.mock.calls[0][0]).toContain("/api/orders/");
  });

  it("DeltaChip polls and its timer dies with the component", async () => {
    vi.useFakeTimers();
    app.update((a) => ({ ...a, schema: SCHEMA, token: "", apiUrlOverride: "http://api.test" }));
    mockFetch.mockResolvedValue(jsonReply({ count: 0, results: [], next: null }));
    const host = document.createElement("div");
    document.body.append(host);
    try {
      flushSync(() => {
        const inst = mount(DeltaChip, { target: host });
        mounted.push(inst);
      });
      await vi.advanceTimersByTimeAsync(0);
      flushSync(() => {});
      expect(mockFetch).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(60000);
      expect(mockFetch).toHaveBeenCalledTimes(2);
      // unmount must cancel the $effect cleanup — no orphan timer polling
      unmount(mounted.pop()!);
      await vi.advanceTimersByTimeAsync(180000);
      expect(mockFetch).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
