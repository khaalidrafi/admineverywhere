/** FR-R003 client half, MOUNTED — the proof class the unit tests could not give.
 *  actions.test.ts grades `actionPath`/`callRecordAction` as functions, and
 *  lifecycleMount.test.ts grades the audit SUB-VIEW; nothing on the tree ever
 *  clicked a drop-in action button. So the item's own open row — "the
 *  buttons/dialog were never clicked" — is closed here against the REAL
 *  registry (src/actions/flag.ts + bulk_flag.ts, globbed exactly as the app
 *  globs them) and the REAL page: the reason the dialog collects, the URL the
 *  client believed in, the ids a bulk selection carries, and the guard `reason`
 *  a rejected action surfaces verbatim. Same wire law as chatMount and
 *  lifecycleMount: assert the captured request, never a hand-built string.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPage from "../../pages/ModelPage.svelte";
import Toaster from "../../components/Toaster.svelte";
import { normalizeOpenAPI } from "../openapi";
import { actions } from "../actions/index";
import { app, claims, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";
import type { AdminSchema } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const hosts: Array<{ instance: any; toastHost: HTMLElement }> = [];
afterEach(() => {
  while (hosts.length) {
    const h = hosts.pop()!;
    unmount(h.instance);
    document.body.textContent = "";
  }
  mockFetch.mockReset();
  toasts.set([]);
  app.set({} as any);
  claims.set(null);
});

const LIVE = normalizeOpenAPI(fixture);

/** One orders row, pending, pk 7 — the same record the lifecycle proof uses. */
const ROW = { id: 7, status: "pending", total: "12.50", customer: 3, created_at: "2026-10-20T10:00:00Z" };
const PAGE = { count: 1, results: [ROW] };
const PRODUCT_PAGE = { count: 1, results: [{ id: 4, name: "Mango", price: "2.50" }] };

const ENTRY = (id: number) => ({ id, action: "order.flag", actor: "admin", created_at: "2026-10-22T09:00:00Z", data: {} });

function reply(status: number, data: any) {
  return { ok: status < 400, status, json: async () => data, text: async () => JSON.stringify(data) };
}

/** Route by URL, so every assertion below is about WHICH endpoint the client
 *  believed in. `flag`/`bulkFlag` carry the answer the server will give;
 *  `list` is a SEQUENCE of list pages, one per read (the last repeats) — that is
 *  how a test grades "the table re-read after the write" instead of counting
 *  requests that a substring happens to match. */
function route(
  opts: { flag?: { status: number; body: any }; bulkFlag?: { status: number; body: any }; list?: any[] } = {},
) {
  let reads = 0;
  mockFetch.mockImplementation(async (url: string) => {
    const u = String(url);
    if (u.includes("/flag/")) return reply(opts.flag?.status ?? 201, opts.flag?.body ?? ENTRY(11));
    if (u.includes("/bulk_flag/")) return reply(opts.bulkFlag?.status ?? 201, opts.bulkFlag?.body ?? [ENTRY(12), ENTRY(13)]);
    if (u.includes("/transition/")) return reply(200, ROW);
    if (u.includes("/history/")) return reply(200, []);
    if (u.includes("/audit/")) return reply(200, { count: 0, results: [] });
    if (u.includes("/products/")) return reply(200, PRODUCT_PAGE);
    if (u.includes("/orders/")) {
      const page = opts.list ? opts.list[Math.min(reads, opts.list.length - 1)] : PAGE;
      reads += 1;
      return reply(200, page);
    }
    return reply(200, { count: 0, results: [] });
  });
  return { listReads: () => reads };
}

function renderPage(schema: AdminSchema, modelId = "orders") {
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
    const instance = mount(ModelPage, { target: host, props: { modelId } });
    hosts.push({ instance, toastHost });
    mount(Toaster, { target: toastHost });
  });
  return { host, toastHost };
}

const buttonsIn = (el: ParentNode) => [...el.querySelectorAll("button")];
const byLabel = (el: ParentNode, label: string) => buttonsIn(el).filter((b) => b.textContent?.trim() === label);
const urls = () => mockFetch.mock.calls.map((c) => String(c[0]));
const flagUrls = () => urls().filter((u) => u.includes("/flag/"));
const bulkUrls = () => urls().filter((u) => u.includes("/bulk_flag/"));
const initOf = (needle: string) => mockFetch.mock.calls.find((c) => String(c[0]).includes(needle))?.[1];

/** Wait for the row to render, then open one record-scope dialog. */
async function openRecordAction(host: HTMLElement, label: string) {
  await vi.waitFor(() => {
    flushSync(() => {});
    expect(byLabel(host, label).length).toBeGreaterThan(0);
  });
  byLabel(host, label)[0].click();
  flushSync(() => {});
}

/** The confirm dialog is the card carrying the action's label as a heading —
 *  ModelPage also renders a table search box with class `input`, so every
 *  dialog read MUST be scoped here or it grades the wrong field. */
function dialog(host: HTMLElement): HTMLElement {
  const card = [...host.querySelectorAll("div.card")].find((c) => c.querySelector("h2"));
  expect(card).toBeTruthy();
  return card as HTMLElement;
}

/** Type into the dialog's input the way a user does: value + input event. */
function typeInto(box: ParentNode, value: string) {
  const field = box.querySelector("input") as HTMLInputElement;
  expect(field).toBeTruthy();
  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  flushSync(() => {});
  return field;
}

/** The dialog renders AFTER the table, so scoping to the dialog card is what
 *  separates its submit from the row button that opened it. */
const submitOf = (box: ParentNode, label: string) => byLabel(box, label).at(-1)! as HTMLButtonElement;

describe("mounted action registry — the drop-in buttons and the bytes they send", () => {
  it("renders the globbed registry and POSTs the collected reason to the discovered path", async () => {
    // the registry this page renders comes from the glob, not a hand-written list
    expect(Object.keys(actions).sort()).toEqual(["bulk_flag", "flag"]);
    route();
    const { host, toastHost } = renderPage(LIVE);
    await openRecordAction(host, "Flag");

    // meta.confirm is shown, meta.input is collected, and the guard holds
    const box = dialog(host);
    expect(box.textContent).toContain("Flag this record for review?");
    const submit = submitOf(box, "Flag");
    expect(submit.disabled).toBe(true);
    expect(flagUrls()).toEqual([]);

    typeInto(box, "duplicate shipment");
    expect(submitOf(box, "Flag").disabled).toBe(false);
    submitOf(box, "Flag").click();

    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("Flag: 1 audit entry written");
    });

    // the URL is listPath-derived, the pk is encoded into it, and the body is
    // exactly the one key the handler declares
    expect(flagUrls()).toEqual(["http://api.test/api/orders/7/flag/"]);
    const init = initOf("/flag/")!;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ reason: "duplicate shipment" });
    expect(init.headers.Authorization).toBe("Token tok");
  });

  it("refuses a whitespace-only reason and closes on Cancel — with zero action requests", async () => {
    route();
    const { host } = renderPage(LIVE);
    await openRecordAction(host, "Flag");
    const box = dialog(host);
    const field = typeInto(box, "   ");
    expect(field.value).toBe("   "); // the guard is graded on the dialog's own field
    expect(submitOf(box, "Flag").disabled).toBe(true);
    typeInto(box, "a real reason");
    expect(submitOf(box, "Flag").disabled).toBe(false);
    byLabel(box, "Cancel")[0].click();
    flushSync(() => {});
    expect(host.textContent).not.toContain("Flag this record for review?");
    expect(flagUrls()).toEqual([]);
  });

  it("surfaces a 400 guard failure's reason verbatim, untranslated", async () => {
    const REASON = "missing required field 'reason' from the reviewer";
    route({ flag: { status: 400, body: { reason: REASON } } });
    const { host, toastHost } = renderPage(LIVE);
    await openRecordAction(host, "Flag");
    const box = dialog(host);
    typeInto(box, "x");
    submitOf(box, "Flag").click();

    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain(`Flag rejected: ${REASON}`);
    });
    expect(toastHost.textContent).not.toContain("API 400");
  });

  it("re-reads the list after a written entry, so the table shows the server's state", async () => {
    // The witness is the SECOND PAGE RENDERED, not a request count: counting URLs
    // that contain "/orders/" is satisfied by the action POST too (measured with
    // `await load()` deleted — 2 urls, list + flag, and a count assertion still
    // green). So the re-read must answer a row the first read never carried.
    const r = route({ list: [PAGE, { count: 1, results: [{ ...ROW, notes: "flagged by qa" }] }] });
    const { host, toastHost } = renderPage(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });
    expect(host.textContent).not.toContain("flagged by qa");

    await openRecordAction(host, "Flag");
    const box = dialog(host);
    typeInto(box, "audit me");
    submitOf(box, "Flag").click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("Flag: 1 audit entry written");
      expect(host.textContent).toContain("flagged by qa");
    });
    expect(r.listReads()).toBeGreaterThan(1);
  });

  it("bulk scope: the selection column exists, and the batch posts the selected ids", async () => {
    route();
    const { host, toastHost } = renderPage(LIVE);
    // wait for a REAL row, not the loading skeleton: the header checkbox is
    // already on the page while rows are still being fetched, and toggling
    // "select all" over an empty table is a pass that proves nothing.
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });
    const boxes = host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    expect(boxes.length).toBe(2); // header + one row — the column exists only because a bulk action does
    boxes[boxes.length - 1].click();
    flushSync(() => {});

    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("1 selected");
    });
    expect(byLabel(host, "Flag batch").length).toBe(1);
    expect(bulkUrls()).toEqual([]);

    byLabel(host, "Flag batch")[0].click();
    flushSync(() => {});
    const box = dialog(host);
    typeInto(box, "quarterly sweep");
    submitOf(box, "Flag batch").click();

    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("Flag batch: 2 audit entries written");
    });
    expect(bulkUrls()).toEqual(["http://api.test/api/orders/bulk_flag/"]);
    expect(JSON.parse(initOf("/bulk_flag/")!.body)).toEqual({ ids: [7], reason: "quarterly sweep" });
  });

  it("a model with no registered action renders no action button and no selection column", async () => {
    route();
    const { host } = renderPage(LIVE, "products");
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Mango");
    });
    // meta.model "orders" scopes both reference actions; products must stay plain CRUD
    expect(byLabel(host, "Flag")).toEqual([]);
    expect(byLabel(host, "Flag batch")).toEqual([]);
    expect(host.querySelectorAll('input[type="checkbox"]').length).toBe(0);
    expect(flagUrls()).toEqual([]);
    expect(bulkUrls()).toEqual([]);
  });

  it("FR-R007: the managers-only batch button is hidden by claims, the record action is not", async () => {
    route();
    claims.set({ username: "auditor", isStaff: true, isSuperuser: false, roles: ["auditors"] });
    const { host } = renderPage(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(byLabel(host, "Flag").length).toBeGreaterThan(0);
    });
    // bulk_flag.ts declares roles: ["managers"]; an auditor keeps the record
    // button and loses the batch one — presentation only, the server still gates.
    expect(byLabel(host, "Flag batch")).toEqual([]);
    expect(host.querySelectorAll('input[type="checkbox"]').length).toBe(0);
  });
});
