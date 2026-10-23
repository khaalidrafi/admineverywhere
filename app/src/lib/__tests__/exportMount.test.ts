/** FR-R005, mounted for real — closes the row docs/csv-export.md §6 left open.
 *
 *  Everything that graded the two export layers before this file was written
 *  looked at a PURE function or an HTTP client: csv.test.ts feeds buildCsv a
 *  matrix, api.test.ts calls fetchCsv directly, openapi.test.ts checks that
 *  exportPath was discovered. None of them ever rendered the page, so every
 *  promise a REVIEWER reads off the screen was unproven: that the button
 *  exports the columns the table ACTUALLY rendered (not a re-derived copy),
 *  the CURRENT page only, with ZERO server calls; that "Full export" vanishes
 *  with the document that omits the endpoint instead of probing a guessed
 *  path; that the bytes downloaded are the server's, BOM and all. That is the
 *  same shape of gap the R-004 board had until kanbanMount.test.ts.
 *
 *  Same harness law as kanbanMount/lifecycleMount: browser resolve condition,
 *  flushSync, stubbed fetch, the captured fixture through normalizeOpenAPI —
 *  and the download is intercepted at the anchor click, so the assertions are
 *  about the FILE A USER WOULD GET, not about a re-call of the writer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPage from "../../pages/ModelPage.svelte";
import Toaster from "../../components/Toaster.svelte";
import { normalizeOpenAPI } from "../openapi";
import { app, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";
import type { AdminSchema, ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const LIVE = normalizeOpenAPI(fixture);
const BOM = "﻿";

/** The six columns the table renders for the rig's Order model — its first six
 *  normalized fields. `product` and `created_at` sit outside that slice, so a
 *  file that carries either one exported more than the user can see. */
const VISIBLE = ["id", "status", "total", "weight", "notes", "customer"];
const HIDDEN = ["product", "created_at"];

const ROW_PAID = {
  id: 1,
  status: "paid",
  total: "19.99",
  weight: 1e-7,
  notes: "Gizmo, big",
  created_at: "2026-10-20T21:00:00Z",
  customer: 3,
  product: 5,
};
const ROW_FORMULA = {
  id: 2,
  status: "pending",
  total: "-5.00",
  weight: null,
  notes: "=SUM(A1:A9)",
  created_at: "2026-10-21T09:30:00Z",
  customer: 4,
  product: 6,
};
const LONG_NOTE = "n".repeat(200);

const hosts: Array<{ instance: any }> = [];
const anchorClicks: Array<{ filename: string; href: string }> = [];
const blobs = new Map<string, Blob>();
let blobSeq = 0;
let origAnchorClick: any;
let origCreateObjectURL: any;
let origRevokeObjectURL: any;

beforeEach(() => {
  // Intercept a download where the product code performs it: createElement("a")
  // -> a.download -> a.click(). The blob is the file's bytes; nothing here
  // re-calls buildCsv, so a divergence inside the component is still caught.
  origAnchorClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
    if (this.download) {
      anchorClicks.push({ filename: this.download, href: this.getAttribute("href") ?? "" });
      return;
    }
    return origAnchorClick.apply(this, arguments as any);
  };
  origCreateObjectURL = (URL as any).createObjectURL;
  origRevokeObjectURL = (URL as any).revokeObjectURL;
  (URL as any).createObjectURL = (blob: Blob) => {
    const url = `blob:test/${++blobSeq}`;
    blobs.set(url, blob);
    return url;
  };
  (URL as any).revokeObjectURL = (url: string) => {
    blobs.delete(url);
  };
});

afterEach(() => {
  while (hosts.length) unmount(hosts.pop()!.instance);
  hosts.length = 0;
  anchorClicks.length = 0;
  blobs.clear();
  if (origAnchorClick) HTMLAnchorElement.prototype.click = origAnchorClick;
  (URL as any).createObjectURL = origCreateObjectURL;
  (URL as any).revokeObjectURL = origRevokeObjectURL;
  mockFetch.mockReset();
  toasts.set([]);
  app.set({} as any);
});

function reply(status: number, data: any, headers: Record<string, string> = {}) {
  return {
    ok: status < 400,
    status,
    json: async () => data,
    text: async () => (typeof data === "string" ? data : JSON.stringify(data)),
    headers: { get: (name: string) => headers[name] ?? headers[Object.keys(headers).find((k) => k.toLowerCase() === name.toLowerCase())!] ?? null },
  };
}

/** Route by URL. `list` answers the table page, `exportBody` the layer-2
 *  document, `exportStatus` the endpoint's verdict. */
function route(opts: {
  list?: any;
  exportBody?: string;
  exportStatus?: number;
  exportHeaders?: Record<string, string>;
} = {}) {
  const page = opts.list ?? { count: 12, results: [ROW_PAID, ROW_FORMULA] };
  mockFetch.mockImplementation(async (url: string) => {
    const u = String(url);
    if (u.includes("/export/")) {
      return reply(opts.exportStatus ?? 200, opts.exportBody ?? `${BOM}id,status\r\n1,paid\r\n`, opts.exportHeaders ?? {});
    }
    if (u.includes("/history/")) return reply(200, []);
    if (u.includes("/audit/")) return reply(200, { count: 0, results: [] });
    if (u.includes("/orders/") || u.includes("/customers/")) return reply(200, page);
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

const urls = () => mockFetch.mock.calls.map((c) => String(c[0]));
const button = (host: HTMLElement, label: string) =>
  ([...host.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) ?? null) as HTMLButtonElement | null;

function settleTo(host: HTMLElement, text: string) {
  return vi.waitFor(() => {
    flushSync(() => {});
    expect(host.textContent).toContain(text);
  });
}

/** The bytes of the most recent intercepted download. */
async function downloadedText(): Promise<string> {
  const href = anchorClicks[anchorClicks.length - 1].href;
  const blob = blobs.get(href);
  if (!blob) throw new Error(`no blob behind download href ${href} (captured ${blobs.size})`);
  if (typeof (blob as any).text === "function") return (blob as any).text();
  return new TextDecoder().decode(await (blob as any).arrayBuffer());
}

/** Re-arm the layer-2 answer for a later click within one test. */
function answerExport(status: number, data: any, headers: Record<string, string> = {}) {
  mockFetch.mockImplementation(async (url: string) => {
    const u = String(url);
    if (u.includes("/export/")) return reply(status, data, headers);
    if (u.includes("/history/")) return reply(200, []);
    if (u.includes("/audit/")) return reply(200, { count: 0, results: [] });
    if (u.includes("/orders/") || u.includes("/customers/")) return reply(200, { count: 12, results: [ROW_PAID, ROW_FORMULA] });
    return reply(200, { count: 0, results: [] });
  });
}

describe("mounted layer 1 — the table's own columns, this page only, no server call", () => {
  it("exports exactly the columns the table rendered, for the current page", async () => {
    route();
    const { host } = render(LIVE);
    await settleTo(host, "12 records");

    const before = mockFetch.mock.calls.length;
    const exportBtn = button(host, "Export table");
    expect(exportBtn).toBeTruthy();

    // the rendered <th> set is the contract: the file must match the screen.
    // The select-all header (empty label) and the "Actions" tail are chrome,
    // not data columns, so the compare strips exactly those two.
    const columnHeads = [...host.querySelectorAll("thead th")]
      .map((th) => th.textContent?.trim() ?? "")
      .filter((t) => t !== "" && t !== "Actions");
    expect(columnHeads).toEqual(["id", "status", "total", "weight", "notes", "customer"]);

    flushSync(() => exportBtn!.click());
    expect(anchorClicks.length).toBe(1);
    const text = await downloadedText();
    const [headerLine, ...dataLines] = text.replace(BOM, "").split("\r\n").filter(Boolean);

    expect(headerLine).toBe(VISIBLE.join(","));
    // 1:1 with the rendered headers (machine names vs the humanised <th>)
    expect(headerLine.split(",").map((n) => n.replace(/_/g, " "))).toEqual(columnHeads);
    // the page says 12 records; the file carries the 2 rows on screen only
    expect(dataLines.length).toBe(2);
    // …and never a field the table does not show
    for (const hidden of HIDDEN) expect(headerLine).not.toContain(hidden);
    expect(dataLines[0]).toBe("1,paid,19.99,1e-7,\"Gizmo, big\",3");
    // layer 1 is pure client: the click asked the backend for NOTHING
    expect(mockFetch.mock.calls.length).toBe(before);
    expect(urls().some((u) => u.includes("/export/"))).toBe(false);
  });

  it("the file is DATA, not the rendered cell: no truncation, null empty, decimal un-reflowed, guard on, one BOM", async () => {
    route({
      list: {
        count: 3,
        results: [
          ROW_PAID,
          { ...ROW_FORMULA, weight: null },
          { ...ROW_PAID, id: 3, notes: LONG_NOTE },
          { ...ROW_PAID, id: 4, notes: "first, second\nthird" },
        ],
      },
    });
    const { host } = render(LIVE);
    await settleTo(host, "3 records");

    // the table truncates the long note for display; the file must not
    expect(host.textContent).not.toContain(LONG_NOTE);

    flushSync(() => button(host, "Export table")!.click());
    const text = await downloadedText();

    expect(text.startsWith(BOM)).toBe(true);
    expect(text.split(BOM).length - 1).toBe(1); // never a doubled BOM
    expect(text.endsWith("\r\n")).toBe(true);
    expect(text).toContain(LONG_NOTE); // formatCell's 60-char cap stays on screen
    expect(text).not.toContain("—"); // null renders as "—" in a cell, as "" in a file
    expect(text).toContain("19.99"); // the DecimalField string, un-re-flowed
    expect(text).toContain("1e-7"); // ECMAScript's own rendering of the parsed float
    // data rows, byte for byte: QUOTE_MINIMAL on the comma, lowercase booleans,
    // the formula lead apostrophised, the null an empty field, an embedded LF
    // quoted rather than allowed to start a new record
    expect(text).toContain('"Gizmo, big"');
    expect(text).toContain("2,pending,-5.00,,'=SUM(A1:A9),4"); // null → empty field
    expect(text).toContain('"first, second\nthird"');
  });

  it("an empty page exports nothing: an info toast and zero downloads", async () => {
    route({ list: { count: 0, results: [] } });
    const { host, toastHost } = render(LIVE);
    await settleTo(host, "0 records");

    flushSync(() => button(host, "Export table")!.click());
    await settleTo(toastHost, "Nothing to export");

    expect(anchorClicks.length).toBe(0);
    expect(urls().some((u) => u.includes("/export/"))).toBe(false);
  });
});

describe("mounted layer 2 — bound to the documented endpoint, never to a guess", () => {
  it('"Full export" renders only where the document carries GET …/export/', async () => {
    route();
    const { host } = render(LIVE, "orders");
    await settleTo(host, "12 records");
    expect(button(host, "Full export")).toBeTruthy();
    unmount(hosts.pop()!.instance);
    document.body.innerHTML = "";

    // the same page for a model whose document has no export endpoint
    const { host: custHost } = render(LIVE, "customers");
    await settleTo(custHost, "record");
    expect(button(custHost, "Full export")).toBeNull();
    // layer 1 does not depend on the server, so it stays
    expect(button(custHost, "Export table")).toBeTruthy();
    expect(urls().some((u) => u.includes("/export/"))).toBe(false);
  });

  it("an exportPath stripped from the schema removes the button AND the request", async () => {
    const stripped: ModelSpec[] = LIVE.models.map((m) => {
      if (m.id !== "orders") return m;
      const copy: ModelSpec = { ...m };
      delete copy.exportPath;
      return copy;
    });
    const NO_EXPORT: AdminSchema = {
      ...LIVE,
      models: stripped,
      byId: Object.fromEntries(stripped.map((m) => [m.id, m])),
    };
    expect(NO_EXPORT.byId["orders"].exportPath).toBeUndefined();

    route();
    const { host, toastHost } = render(NO_EXPORT);
    await settleTo(host, "12 records");

    expect(button(host, "Full export")).toBeNull();
    expect(button(host, "Export table")).toBeTruthy();
    // the whole point of the evidence law: no probe of a guessed /api/export/
    await new Promise((r) => setTimeout(r, 50));
    expect(urls().some((u) => u.includes("export"))).toBe(false);
    expect(toastHost.textContent).toBe("");
  });

  it("downloads the server's own bytes from the discovered path, with the server's filename slugified", async () => {
    const serverDoc = `${BOM}id,status,total\r\n1,paid,19.99\r\n2,pending,-5.00\r\n`;
    route({
      exportBody: serverDoc,
      exportHeaders: { "Content-Disposition": 'attachment; filename="../../etc/Order Lines.csv"' },
    });
    const { host, toastHost } = render(LIVE);
    await settleTo(host, "12 records");

    const full = button(host, "Full export");
    flushSync(() => full!.click());
    await settleTo(toastHost, "Full export saved as");

    expect(urls()).toContain("http://api.test/api/orders/export/");
    const call = mockFetch.mock.calls.find((c) => String(c[0]).includes("/export/"))!;
    const init = call[1] as any;
    expect(init.headers.Accept).toContain("text/csv");
    expect(init.headers.Authorization).toBe("Token tok");

    // a header is data, not a save path: hostile name survives as a slug
    expect(anchorClicks.length).toBe(1);
    expect(anchorClicks[0].filename).toBe("etc-order-lines.csv");
    expect(anchorClicks[0].filename).not.toContain("..");
    expect(anchorClicks[0].filename).not.toContain("/");

    const text = await downloadedText();
    // untouched, and the client's BOM pass never doubles the server's
    expect(text).toBe(serverDoc);
    expect(text.split(BOM).length - 1).toBe(1);
    // layer 2 does not re-ask for the table page
    expect(urls().filter((u) => u.includes("/export/")).length).toBe(1);
  });

  it("a refused export surfaces the server's reason, downloads nothing, and re-enables the button", async () => {
    route({ exportStatus: 400, exportBody: "This backend has no export endpoint" });
    const { host, toastHost } = render(LIVE);
    await settleTo(host, "12 records");

    flushSync(() => button(host, "Full export")!.click());
    await settleTo(toastHost, "This backend has no export endpoint");

    expect(anchorClicks.length).toBe(0);
    const again = button(host, "Full export");
    expect(again).toBeTruthy();
    expect(again!.disabled).toBe(false);
    expect(again!.textContent).toContain("Full export");
  });

  it("the button labels itself Exporting… while the request is in flight", async () => {
    let release: (v: any) => void = () => {};
    mockFetch.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes("/export/")) return new Promise((res) => (release = res));
      if (u.includes("/orders/")) return Promise.resolve(reply(200, { count: 12, results: [ROW_PAID, ROW_FORMULA] }));
      return Promise.resolve(reply(200, { count: 0, results: [] }));
    });
    const { host } = render(LIVE);
    await settleTo(host, "12 records");

    flushSync(() => button(host, "Full export")!.click());
    await vi.waitFor(() => {
      flushSync(() => {});
      // the label itself moves, so the pre-click button no longer exists
      expect(button(host, "Full export")).toBeNull();
      const busy = button(host, "Exporting…")!;
      expect(busy.disabled).toBe(true);
      // while one export runs, layer 1 is inert too — no double download
      expect(button(host, "Export table")!.disabled).toBe(true);
    });

    flushSync(() => {
      release(reply(200, `${BOM}id\r\n1\r\n`, { "Content-Disposition": 'attachment; filename="orders-line.csv"' }));
    });
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(button(host, "Full export")!.disabled).toBe(false);
    });
    expect(anchorClicks.length).toBe(1);
    expect(anchorClicks[0].filename).toBe("orders-line.csv");
  });
});

describe("layer 1 keeps working where layer 2 is refused (the two layers stay uncollapsed)", () => {
  it("a 404 on the endpoint does not stop the current page from exporting", async () => {
    answerExport(404, "Not Found");
    const { host, toastHost } = render(LIVE);
    await settleTo(host, "12 records");

    flushSync(() => button(host, "Full export")!.click());
    await settleTo(toastHost, "API 404");

    flushSync(() => button(host, "Export table")!.click());
    expect(anchorClicks.length).toBe(1);
    const text = await downloadedText();
    expect(text.split("\r\n").filter(Boolean).length).toBe(3); // header + 2 rows
  });
});
