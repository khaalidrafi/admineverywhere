/** FR-R004 board, mounted for real — closes the row the R-004 delivery note
 *  left open ("the board's wiring is proven by the pure module + build + live
 *  API, not by a rendered component"). The assertions are about the RENDERED
 *  DOM and the wire: toggling the view asks the DISCOVERED list path for a
 *  wide page, a card only reaches a column the machine allows, and the payload
 *  that leaves is the one `planMove` decided. Same harness law as
 *  lifecycleMount.test.ts: browser resolve condition + flushSync + stubbed
 *  fetch, schema from normalizeOpenAPI of the captured fixture.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPage from "../../pages/ModelPage.svelte";
import Toaster from "../../components/Toaster.svelte";
import { normalizeOpenAPI } from "../openapi";
import { resolveAxis } from "../kanban";
import { app, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";
import type { AdminSchema, ModelSpec } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const hosts: Array<{ instance: any }> = [];
afterEach(() => {
  while (hosts.length) unmount(hosts.pop()!.instance);
  hosts.length = 0;
  mockFetch.mockReset();
  toasts.set([]);
  app.set({} as any);
});

const LIVE = normalizeOpenAPI(fixture);

function reply(status: number, data: any) {
  return { ok: status < 400, status, json: async () => data, text: async () => JSON.stringify(data) };
}

const PENDING_ROW = { id: 7, status: "pending", total: "12.50", customer: 3, created_at: "2026-10-20T10:00:00Z" };
const PAGE = { count: 1, results: [PENDING_ROW] };

/** Route by URL, and record the METHOD + body so the test can name the bytes. */
function route(page: any = PAGE, transition: { status: number; body: any } = { status: 200, body: { ...PENDING_ROW, status: "paid" } }) {
  mockFetch.mockImplementation(async (url: string, init?: any) => {
    const u = String(url);
    if (u.includes("/transition/")) return reply(transition.status, transition.body);
    if (u.includes("/history/")) return reply(200, []);
    if (u.includes("/audit/")) return reply(200, { count: 0, results: [] });
    if (u.includes("/orders/")) return reply(200, page);
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
const bodies = (needle: string) =>
  mockFetch.mock.calls
    .filter((c) => String(c[0]).includes(needle))
    .map((c) => (c[1] as any)?.body);

/** happy-dom has no DragEvent constructor, and `dragstart` must carry a
 *  dataTransfer because the component writes the record id into it. A plain
 *  Event with the two fields the handlers read is the honest stand-in. */
function dragEvent(kind: "dragstart" | "dragover" | "drop") {
  const event: any = new Event(kind, { bubbles: true, cancelable: true });
  event.dataTransfer = { effectAllowed: "", dropEffect: "", setData: () => {}, getData: () => "" };
  return event;
}

function boardToggle(host: HTMLElement): HTMLButtonElement | null {
  return (
    [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Kanban")) ?? null
  ) as HTMLButtonElement | null;
}

function settleTo(host: HTMLElement, text: string) {
  return vi.waitFor(() => {
    flushSync(() => {});
    expect(host.textContent).toContain(text);
  });
}

describe("mounted kanban board — columns, keyboard path, wire", () => {
  it("the toggle asks the discovered list path for a board-sized page", async () => {
    route();
    const { host } = render(LIVE);
    await settleTo(host, "pending");
    expect(resolveAxis(LIVE.byId["orders"])).not.toBeNull();

    const toggle = boardToggle(host);
    expect(toggle).toBeTruthy();
    expect(toggle!.getAttribute("aria-pressed")).toBe("false");
    flushSync(() => toggle!.click());
    await settleTo(host, "Board by status");

    // table load first (no page_size), then the board's widened page — both on
    // the DISCOVERED listPath, never a hand-written /api/orders/
    expect(urls()[0]).toBe("http://api.test/api/orders/?page=1");
    expect(urls().some((u) => u.startsWith("http://api.test/api/orders/?") && u.includes("page_size=100"))).toBe(true);
    // every declared column renders, empty ones included
    const labels = [...host.querySelectorAll("section")].map((s) => s.getAttribute("aria-label"));
    expect(labels).toEqual([
      "pending column, 1 record",
      "paid column, 0 records",
      "shipped column, 0 records",
      "refunded column, 0 records",
    ]);
  });

  it("a card move fires POST <discovered detail path>transition/ with only the target", async () => {
    route();
    const { host, toastHost } = render(LIVE);
    await settleTo(host, "pending");
    flushSync(() => boardToggle(host)!.click());
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.querySelector("select[aria-label^='Move ']")).toBeTruthy();
    });

    const select = host.querySelector<HTMLSelectElement>("select[aria-label^='Move ']")!;
    const options = [...select.options].map((o) => ({ value: o.value, disabled: o.disabled }));
    // pending's only legal target is paid — the UI pre-filters, the server stays authority
    expect(options).toEqual([
      { value: "", disabled: false },
      { value: "pending", disabled: true },
      { value: "paid", disabled: false },
      { value: "shipped", disabled: true },
      { value: "refunded", disabled: true },
    ]);

    flushSync(() => {
      select!.value = "paid";
      select!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await settleTo(toastHost, "7 → paid");

    expect(bodies("/transition/")).toEqual(['{"transition":"paid"}']);
    expect(urls().filter((u) => u.includes("/transition/"))).toEqual([
      "http://api.test/api/orders/7/transition/",
    ]);
    // the board re-renders the moved record into its new column
    await vi.waitFor(() => {
      flushSync(() => {});
      const paid = [...host.querySelectorAll("section")].find((s) => s.getAttribute("aria-label")?.startsWith("paid"));
      expect(paid?.getAttribute("aria-label")).toBe("paid column, 1 record");
    });
  });

  it("drag offers drop feedback on legal columns only and refuses the illegal one", async () => {
    route();
    const { host } = render(LIVE);
    await settleTo(host, "pending");
    flushSync(() => boardToggle(host)!.click());
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.querySelector("article")).toBeTruthy();
    });

    const card = host.querySelector("article")!;
    expect(card.getAttribute("draggable")).toBe("true");
    const sections = [...host.querySelectorAll("section")];
    const paidCol = sections.find((s) => s.getAttribute("aria-label")?.startsWith("paid"))!;
    const shippedCol = sections.find((s) => s.getAttribute("aria-label")?.startsWith("shipped"))!;

    flushSync(() => card.dispatchEvent(dragEvent("dragstart")));
    const dropOn = (col: Element) => {
      col.dispatchEvent(dragEvent("dragover"));
      flushSync(() => col.dispatchEvent(dragEvent("drop")));
    };

    // illegal target: no feedback, and nothing reaches the network
    dropOn(shippedCol);
    await new Promise((r) => setTimeout(r, 50));
    expect(urls().some((u) => u.includes("/transition/"))).toBe(false);

    // legal target: the drag ends there and the transition fires once
    flushSync(() => card.dispatchEvent(dragEvent("dragstart")));
    dropOn(paidCol);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(urls().filter((u) => u.includes("/transition/")).length).toBe(1);
    });
    expect(bodies("/transition/")).toEqual(['{"transition":"paid"}']);
  });

  it("a record with an undeclared status lands in Unassigned, visible and read-only", async () => {
    const rows = { count: 2, results: [PENDING_ROW, { ...PENDING_ROW, id: 8, status: "void" }] };
    route(rows);
    const { host } = render(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("2 records");
    });
    flushSync(() => boardToggle(host)!.click());
    const unassigned = await vi.waitFor(() => {
      flushSync(() => {});
      const col = [...host.querySelectorAll("section")].find((c) =>
        c.getAttribute("aria-label") === "Unassigned column, 1 record",
      );
      // the column label appears while the board is still on its skeleton, so
      // wait for the CARD, not the heading — a transient frame is not evidence
      expect(col?.querySelector("article")).toBeTruthy();
      return col!;
    });
    const card = unassigned.querySelector("article")!;
    // display-only: not draggable, and its select is disabled
    expect(card.getAttribute("draggable")).not.toBe("true");
    expect(card.querySelector("select")!.disabled).toBe(true);
  });

  it("a backend that documents no transition endpoint gets no board at all", async () => {
    const stripped: ModelSpec[] = LIVE.models.map((m) => {
      if (m.id !== "orders") return m;
      const copy: ModelSpec = { ...m };
      delete copy.transitionPath;
      return copy;
    });
    const NO_MACHINE: AdminSchema = {
      ...LIVE,
      models: stripped,
      byId: Object.fromEntries(stripped.map((m) => [m.id, m])),
    };
    expect(NO_MACHINE.byId["orders"].transitionPath).toBeUndefined();
    expect(resolveAxis(NO_MACHINE.byId["orders"])).toBeNull();

    route();
    const { host, toastHost } = render(NO_MACHINE);
    await settleTo(host, "pending");
    expect(boardToggle(host)).toBeNull();
    await new Promise((r) => setTimeout(r, 150));
    expect(urls().some((u) => u.includes("/transition/"))).toBe(false);
    expect(toastHost.textContent).toBe("");
    // the table view still works — refusing the board is a degrade, not a break
    expect(host.textContent).toContain("pending");
  });
});
