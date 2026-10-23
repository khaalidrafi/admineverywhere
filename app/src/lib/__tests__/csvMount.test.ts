/** FR-R005 mounted proof — the two export layers, as the user actually clicks them.
 *  csv.test.ts grades the writer and api.test.ts grades fetchCsv, but both call
 *  their subject directly: neither can see the RENDERED half — which button exists,
 *  which URL the click really lands on, whether the page's own rows reach the file.
 *  Same law as lifecycleMount / actionMount / kanbanMount: mount the real page over
 *  the captured fixture, stub fetch, route by URL, assert the bytes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MockInstance } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPage from "../../pages/ModelPage.svelte";
import Toaster from "../../components/Toaster.svelte";
import { normalizeOpenAPI } from "../openapi";
import { app, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";
import type { AdminSchema } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const hosts: Array<Record<string, any>> = [];
let downloads: Array<{ name: string; blob: Blob }> = [];
let createSpy: MockInstance<(...args: any[]) => any>;
let clickSpy: MockInstance<(...args: any[]) => any>;

/** A download is an object URL plus an anchor click — capture both halves. */
beforeEach(() => {
  downloads = [];
  createSpy = vi.spyOn(URL, "createObjectURL").mockImplementation((blob: any) => {
    downloads.push({ name: "", blob });
    return "blob:captured";
  });
  const realClick = HTMLElement.prototype.click;
  clickSpy = vi.spyOn(HTMLElement.prototype, "click").mockImplementation(function (this: HTMLElement) {
    const name = this.getAttribute("download");
    if (name === null) return realClick.call(this);
    downloads[downloads.length - 1].name = name;
  });
});

afterEach(() => {
  while (hosts.length) unmount(hosts.pop()!.instance);
  hosts.length = 0;
  mockFetch.mockReset();
  toasts.set([]);
  app.set({} as any);
  clickSpy.mockRestore();
  createSpy.mockRestore();
});

const LIVE = normalizeOpenAPI(fixture);

const ORDERS_ROW = {
  id: 7,
  status: "pending",
  total: "12.50",
  notes: "buy 2, ship 1",
  customer: 3,
  created_at: "2026-10-20T10:00:00Z",
};

function reply(status: number, data: any, headers: Record<string, string> = {}) {
  return {
    ok: status < 400,
    status,
    json: async () => data,
    text: async () => (typeof data === "string" ? data : JSON.stringify(data)),
    headers: { get: (k: string) => headers[k] ?? headers[k.toLowerCase()] ?? null },
  };
}

/** Route by URL, so every assertion is about the endpoint the client believed in. */
function route(opts: { csv?: { text: string; disposition?: string } | null; exportStatus?: number } = {}) {
  const { csv = null, exportStatus = 200 } = opts;
  mockFetch.mockImplementation(async (url: string) => {
    const u = String(url);
    if (u.includes("/export/")) {
      if (csv === null) throw new Error(`unexpected export call to ${u}`);
      if (exportStatus !== 200) return reply(exportStatus, { detail: "not for you" });
      return reply(200, csv.text, csv.disposition ? { "Content-Disposition": csv.disposition } : {});
    }
    if (u.includes("/transition/")) return reply(200, {});
    if (u.includes("/history/")) return reply(200, []);
    if (u.includes("/audit/")) return reply(200, { count: 0, results: [] });
    if (u.includes("/orders/")) return reply(200, { count: 1, results: [ORDERS_ROW] });
    return reply(200, { count: 0, results: [] });
  });
}

function render(schema: AdminSchema, modelId = "orders") {
  const host = document.createElement("div");
  const toastHost = document.createElement("div");
  document.body.append(host, toastHost);
  app.update((a) => ({
    ...a,
    schema,
    token: "tok",
    booted: true,
    apiUrlOverride: "http://api.test",
    config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
  }));
  flushSync(() => {
    hosts.push({ instance: mount(ModelPage, { target: host, props: { modelId } }) });
    hosts.push({ instance: mount(Toaster, { target: toastHost }) });
  });
  return { host, toastHost };
}

const buttonNames = (host: HTMLElement) =>
  [...host.querySelectorAll("button")].map((b) => b.textContent?.trim() ?? "");

function exportButton(host: HTMLElement, label: string): HTMLButtonElement {
  const btn = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
  if (!btn) throw new Error(`no "${label}" button — found ${buttonNames(host).join(" | ")}`);
  return btn as HTMLButtonElement;
}

const urls = () => mockFetch.mock.calls.map((c) => String(c[0]));
const csvUrls = () => urls().filter((u) => u.includes("/export/"));
const body = (blob: Blob) => blob.text();

/** The table's own visible columns, read off the rendered <th> row. */
const renderedColumns = (host: HTMLElement) =>
  [...host.querySelectorAll("thead th")].map((th) => th.textContent?.trim() ?? "");

describe("mounted CSV export — the two layers on the wire", () => {
  it("renders BOTH layers only where the document proves them", async () => {
    route();
    const { host } = render(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });
    const names = buttonNames(host);
    expect(names).toContain("Export table");
    expect(names).toContain("Full export");

    // Same rig, the export endpoint deleted from the schema: layer 1 stays,
    // layer 2 has no button — the R-005/R-001 evidence law, proven in the DOM.
    const { exportPath, ...bare } = LIVE.byId.orders;
    const schema: AdminSchema = {
      ...LIVE,
      models: LIVE.models.map((m) => (m.id === "orders" ? (bare as typeof m) : m)),
      byId: { ...LIVE.byId, orders: bare as typeof LIVE.byId.orders },
    };
    mockFetch.mockClear();
    const { host: bareHost } = render(schema);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(bareHost.textContent).toContain("pending");
    });
    const bareNames = buttonNames(bareHost);
    expect(bareNames).toContain("Export table");
    expect(bareNames).not.toContain("Full export");
    // A negative about the wire needs the window in which the request WOULD land.
    await new Promise((r) => setTimeout(r, 150));
    expect(csvUrls()).toEqual([]);
  });

  it("layer 1 writes the visible columns of THIS page with ZERO server calls", async () => {
    route({ csv: null });
    const { host, toastHost } = render(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });
    mockFetch.mockClear();

    exportButton(host, "Export table").click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain(".csv");
    });
    expect(mockFetch.mock.calls.length).toBe(0);

    const [dl] = downloads;
    // the name is slugified schema data (model.name "Order" → "order"), never a
    // raw string that could carry a path separator
    expect(dl.name).toBe("order-page-1.csv");
    const text = await body(dl.blob);
    // the BOM ships once — Excel-on-Windows promise
    expect(text.startsWith("﻿")).toBe(true);
    expect(text.slice(1).includes("﻿")).toBe(false);
    const lines = text.slice(1).split("\r\n");
    // header = the machine names, in the SAME order the table rendered them
    const visible = LIVE.byId.orders.fields.filter((f) => f.type !== "json").slice(0, 6).map((f) => f.name);
    expect(lines[0]).toBe(visible.join(","));
    // the file's columns ARE the table's columns, in render order — a header the
    // user reads must equal a header the spreadsheet gets
    const shown = renderedColumns(host).filter((t) => t !== "Actions" && t !== "");
    expect(shown).toEqual(visible.map((n) => n.replace(/_/g, " ")));
    // one row per loaded record, current page only
    expect(lines[1]).toContain('"buy 2, ship 1"'); // QUOTE_MINIMAL: comma quoted
    expect(text.endsWith("\r\n")).toBe(true);
    // values are the API's bytes, never re-flowed through Number: DRF sent "12.50"
    expect(lines[1]).toContain("12.50");
    expect(lines[1]).not.toContain("12.5,");
  });

  it("layer 2 GETs the DISCOVERED path and passes the server bytes through untouched", async () => {
    // A server-supplied BOM must NOT be doubled (the stray ï»¿ bug) and the
    // line-level rows arrive as the server wrote them, CRLF included.
    const SERVER_BYTES = "﻿id,status,order_id\r\n58,paid,58\r\n59,pending,58\r\n";
    route({ csv: { text: SERVER_BYTES, disposition: 'attachment; filename="orders-line.csv"' } });
    const { host, toastHost } = render(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });

    exportButton(host, "Full export").click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("orders-line.csv");
    });

    expect(csvUrls()).toEqual(["http://api.test/api/orders/export/"]);
    const init = mockFetch.mock.calls.find((c) => String(c[0]).includes("/export/"))![1];
    expect(init.method ?? "GET").toMatch(/GET/i);
    expect(init.headers.Accept).toBe("text/csv, */*;q=0.8");
    expect(init.headers.Authorization).toBe("Token tok");

    const [dl] = downloads;
    expect(dl.name).toBe("orders-line.csv");
    expect(await body(dl.blob)).toBe(SERVER_BYTES);
  });

  it("layer 2 follows the DOCUMENT, not a hard-coded segment", async () => {
    // Rename the endpoint in the schema (as another app genuinely would) and
    // the click must move with it. `apiUrl + "export"` could never pass this.
    const moved: AdminSchema = {
      ...LIVE,
      models: LIVE.models.map((m) =>
        m.id === "orders" ? ({ ...m, exportPath: "/api/orders/download/" } as typeof m) : m,
      ),
      byId: { ...LIVE.byId, orders: { ...LIVE.byId.orders, exportPath: "/api/orders/download/" } },
    };
    mockFetch.mockImplementation(async (url: string) => {
      const u = String(url);
      if (u.endsWith("/download/")) return reply(200, "id\r\n7\r\n");
      if (u.includes("/orders/")) return reply(200, { count: 1, results: [ORDERS_ROW] });
      return reply(200, { count: 0, results: [] });
    });
    const { host } = render(moved);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });

    exportButton(host, "Full export").click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(downloads.length).toBe(1);
    });
    expect(urls().filter((u) => u.endsWith("/download/"))).toEqual(["http://api.test/api/orders/download/"]);
    expect(urls().some((u) => u.includes("/export/"))).toBe(false);
  });

  it("a refused export says so and downloads nothing", async () => {
    route({ csv: { text: "" }, exportStatus: 403 });
    const { host, toastHost } = render(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });

    exportButton(host, "Full export").click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toMatch(/403/);
    });
    expect(downloads.length).toBe(0);
  });
});
