/** FR-R004 board, mounted for real — closes the row the R-004 delivery note
 *  left open ("the board's wiring is proven by the pure module + build + live
 *  API, not by a rendered component"). The assertions are about the RENDERED
 *  DOM and the wire: toggling the view asks the DISCOVERED list path for a
 *  wide page, a card only reaches a column the machine allows, and the payload
 *  that leaves is the one `planMove` decided. Same harness law as
 *  lifecycleMount.test.ts: browser resolve condition + flushSync + stubbed
 *  fetch, schema from normalizeOpenAPI of the captured fixture.
 */
import { afterAll, beforeAll, afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPage from "../../pages/ModelPage.svelte";
import KanbanBoard from "../../components/KanbanBoard.svelte";
import Toaster from "../../components/Toaster.svelte";
import { normalizeOpenAPI } from "../openapi";
import { axisProblem, resolveAxis, type ResolvedAxis } from "../kanban";
import { statusTransitions } from "../statusTransitions";
import { app, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";
import type { AdminSchema, ModelSpec, RecordRow } from "../types";

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

/** Products routes for the declared patch axis (see the last describe). */
function routeProducts() {
  const BOX_ROW = { id: 11, name: "Olives", price: "8.00", stock: 3, packaging: "box" };
  const BLANK_ROW = { id: 12, name: "Cheese", price: "12.00", stock: 1, packaging: "" };
  mockFetch.mockImplementation(async (url: string, init?: any) => {
    const u = String(url);
    if (u.includes("/transition/")) return reply(404, { detail: "no machine governs this field" });
    if (/\/api\/products\/[^/]+\/$/.test(u)) return reply(200, { ...BOX_ROW, packaging: "crate" });
    if (u.includes("/api/products/")) return reply(200, { count: 2, results: [BOX_ROW, BLANK_ROW] });
    return reply(200, { count: 0, results: [] });
  });
}

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

describe("orders carry NO board — the no-approve/deny law, mounted", () => {
  it("orders get no Kanban toggle, no board-sized probe and no transition call", async () => {
    route();
    const { host } = render(LIVE, "orders");
    await settleTo(host, "pending");
    // the schema still documents the machine (transitionPath) and the board
    // machinery exists — the REGISTRY is the law: orders are plain records.
    expect(LIVE.byId["orders"].transitionPath).toBeTruthy();
    expect(resolveAxis(LIVE.byId["orders"])).toBeNull();

    expect(boardToggle(host)).toBeNull();
    await new Promise((r) => setTimeout(r, 150));
    expect(urls().some((u) => u.includes("page_size"))).toBe(false);
    expect(urls().some((u) => u.includes("/transition/"))).toBe(false);
    // the table view still renders the records — data, not a workflow
    expect(host.textContent).toContain("pending");
  });

  it("the board machinery still mounts for a DECLARED patch axis (products)", async () => {
    routeProducts();
    const { host } = render(LIVE, "products");
    await settleTo(host, "Olives");
    const toggle = boardToggle(host);
    expect(toggle).toBeTruthy();
    flushSync(() => toggle!.click());
    await settleTo(host, "Board by packaging");
    expect(
      urls().some((u) => u.startsWith("http://api.test/api/products/?") && u.includes("page_size=100")),
    ).toBe(true);
  });
});

/** The board's OWN legality gate, isolated from the page. Mounted through
 *  ModelPage an illegal drop is refused twice over — here and again in
 *  `planMove` (ModelPage.svelte:236) — so a wire-level test cannot tell which
 *  guard fired: weakening `drop()`'s `!allowed` at KanbanBoard.svelte:77 left
 *  every page-level assertion green (mutant survived, R-004 report 12:59Z).
 *  With a spy `onmove` the component is judged on its own contract. */
describe("KanbanBoard mounted alone — its drop guard answers to no one", () => {
  /** A synthetic governed model: the transition machinery must stay tested
   *  even though orders (the real governed model) is ungoverned by owner law
   *  2026-11-04. Registered here, never through shipped product code. */
  const JOBS: ModelSpec = {
    id: "jobs",
    name: "Job",
    singular: "job",
    listPath: "/api/jobs/",
    detailPath: "/api/jobs/{id}/",
    fields: [
      { name: "id", type: "number", required: false, readOnly: true },
      { name: "status", type: "enum", required: false, readOnly: false, choices: ["queued", "running", "done"] },
    ],
    byName: {},
    labelField: "id",
  };
  JOBS.byName = Object.fromEntries(JOBS.fields.map((f) => [f.name, f]));
  const AXIS: ResolvedAxis = { modelId: "jobs", field: "status", via: "transition", columns: ["queued", "running", "done"] };
  const QUEUED_ROW = { id: 7, status: "queued" };

  beforeAll(() => {
    statusTransitions.jobs = {
      statusField: "status",
      states: ["queued", "running", "done"],
      transitions: { queued: ["running"], running: ["done"], done: [] },
    };
  });
  afterAll(() => {
    delete statusTransitions.jobs;
  });

  function renderBoard(onmove: (row: RecordRow, column: string) => void) {
    const model = JOBS;
    const axis = AXIS;
    const host = document.createElement("div");
    document.body.append(host);
    flushSync(() => {
      hosts.push({ instance: mount(KanbanBoard, { target: host, props: { model, rows: [{ ...QUEUED_ROW }], axis, onmove } }) });
    });
    const column = (label: string) =>
      [...host.querySelectorAll("section")].find((s) => s.getAttribute("aria-label")?.startsWith(label))!;
    const card = host.querySelector("article")!;
    expect(card.getAttribute("draggable")).toBe("true");
    return { host, column, card };
  }

  it("a drop on a column the machine forbids never reaches onmove", () => {
    const onmove = vi.fn();
    const { column, card } = renderBoard(onmove);
    flushSync(() => card.dispatchEvent(dragEvent("dragstart")));
    const illegal = column("done"); // queued -> done is not a transition
    illegal.dispatchEvent(dragEvent("dragover"));
    flushSync(() => illegal.dispatchEvent(dragEvent("drop")));
    expect(onmove).not.toHaveBeenCalled();
  });

  it("a legal drop reaches onmove exactly once, and the drag is consumed", () => {
    const onmove = vi.fn();
    const { column, card } = renderBoard(onmove);
    flushSync(() => card.dispatchEvent(dragEvent("dragstart")));
    const legal = column("running");
    legal.dispatchEvent(dragEvent("dragover"));
    flushSync(() => legal.dispatchEvent(dragEvent("drop")));
    expect(onmove).toHaveBeenCalledTimes(1);
    expect(onmove.mock.calls[0][1]).toBe("running");
    expect(String(onmove.mock.calls[0][0].id)).toBe("7");
    // drop() calls endDrag, so a second drop on the same column is inert
    flushSync(() => legal.dispatchEvent(dragEvent("drop")));
    expect(onmove).toHaveBeenCalledTimes(1);
  });

  it("dragover announces itself legal only on allowed columns", () => {
    const onmove = vi.fn();
    const { column, card } = renderBoard(onmove);
    flushSync(() => card.dispatchEvent(dragEvent("dragstart")));
    const overLegal = dragEvent("dragover");
    column("running").dispatchEvent(overLegal);
    expect(overLegal.defaultPrevented).toBe(true);
    const overIllegal = dragEvent("dragover");
    column("done").dispatchEvent(overIllegal);
    expect(overIllegal.defaultPrevented).toBe(false);
  });
});

/** The OTHER half of the R-004 contract: a `patch` axis on a free enum. Every
 *  test above rides the orders lifecycle axis, so guardrail 1 of
 *  docs/independent-enums.md §6 — "a drop on a free-enum column is a plain PATCH
 *  of that one field and must touch nothing else" — was proven only inside
 *  `planMove` (kanban.test.ts), i.e. by the pure module, never on the wire. This
 *  block grades the bytes that actually leave the page: the method, the single
 *  key, the DISCOVERED detail path, and the fact that the lifecycle endpoint is
 *  never probed for a free enum.
 *
 *  The axis is real product code — `kanbanAxes.products` on the captured
 *  `Product.packaging` (the rig's `blank=True` choices field) — because
 *  ModelPage resolves the axis through the shipped registry. Injecting a source
 *  or mocking `../kanban` would grade a module nobody imports. */
describe("mounted kanban board — the free-enum (patch) axis", () => {
  const BOX_ROW = { id: 11, name: "Olives", price: "8.00", stock: 3, packaging: "box" };
  const BLANK_ROW = { id: 12, name: "Cheese", price: "12.00", stock: 1, packaging: "" };

  /** Products routes. A lifecycle probe answers 404 on purpose: if a free-enum
   *  move were ever mis-routed to the transition endpoint, the call would fail
   *  loudly instead of wearing the success assertion. */
  function routeProducts(moved: RecordRow = { ...BOX_ROW, packaging: "crate" }) {
    mockFetch.mockImplementation(async (url: string, init?: any) => {
      const u = String(url);
      if (u.includes("/transition/")) return reply(404, { detail: "no machine governs this field" });
      if (/\/api\/products\/[^/]+\/$/.test(u)) return reply(200, moved);
      if (u.includes("/api/products/")) return reply(200, { count: 2, results: [BOX_ROW, BLANK_ROW] });
      return reply(200, { count: 0, results: [] });
    });
  }

  /** Every non-GET call as `METHOD url body` — the exact shape guardrail 1 is
   *  about, so a whole-row PUT or a second key fails on the literal. */
  const writes = () =>
    mockFetch.mock.calls
      .filter((c) => ["POST", "PUT", "PATCH"].includes((c[1] as any)?.method))
      .map((c) => `${(c[1] as any).method} ${c[0]} ${(c[1] as any).body}`);

  const column = (host: HTMLElement, label: string) =>
    [...host.querySelectorAll("section")].find((s) => s.getAttribute("aria-label")?.startsWith(label))!;

  async function boardForProducts(schema: AdminSchema = LIVE) {
    routeProducts();
    const view = render(schema, "products");
    await settleTo(view.host, "Olives");
    flushSync(() => boardToggle(view.host)!.click());
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(view.host.querySelector("article")).toBeTruthy();
    });
    return view;
  }

  async function tableForProducts(schema: AdminSchema = LIVE) {
    routeProducts();
    const view = render(schema, "products");
    await settleTo(view.host, "Olives");
    return view;
  }

  it("groups by that field's own choices, empties and all", async () => {
    const axis = resolveAxis(LIVE.byId["products"])!;
    expect(axis.via).toBe("patch");
    expect(axis.columns).toEqual(["box", "crate", "pallet"]);

    const { host } = await boardForProducts();
    expect(host.textContent).toContain("Board by packaging");
    // the move kind is stated on the board, so a user can see this is not a
    // lifecycle board before dragging anything
    expect(host.textContent).toContain("moves are a one-field patch");
    // the wide page rides the DISCOVERED products list path, never a hand-written one
    expect(urls()[0]).toBe("http://api.test/api/products/?page=1");
    expect(
      urls().some((u) => u.startsWith("http://api.test/api/products/?") && u.includes("page_size=100")),
    ).toBe(true);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect([...host.querySelectorAll("section")].map((s) => s.getAttribute("aria-label"))).toEqual([
        "box column, 1 record",
        "crate column, 0 records",
        "pallet column, 0 records",
        "Unassigned column, 1 record", // the blank=True state: visible, never swallowed
      ]);
    });
  });

  it("a keyboard move PATCHes exactly one key to the discovered detail path", async () => {
    const { host, toastHost } = await boardForProducts();
    const select = column(host, "box").querySelector<HTMLSelectElement>("article select")!;
    // a free enum offers every OTHER declared column; only the current one is inert
    expect([...select.options].map((o) => ({ value: o.value, disabled: o.disabled }))).toEqual([
      { value: "", disabled: false },
      { value: "box", disabled: true },
      { value: "crate", disabled: false },
      { value: "pallet", disabled: false },
    ]);

    flushSync(() => {
      select.value = "crate";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await settleTo(toastHost, "Olives → crate");

    expect(writes()).toEqual(['PATCH http://api.test/api/products/11/ {"packaging":"crate"}']);
    expect(bodies("/api/products/11/")).toEqual(['{"packaging":"crate"}']);
    expect(urls().some((u) => u.includes("/transition/"))).toBe(false);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(column(host, "crate").getAttribute("aria-label")).toBe("crate column, 1 record");
    });
  });

  it("a drag sends the identical one-key PATCH; its own column stays inert", async () => {
    const { host } = await boardForProducts();
    const card = column(host, "box").querySelector("article")!;
    expect(card.getAttribute("draggable")).toBe("true");

    // no machine to refuse: both other columns announce themselves legal, and
    // the column the card already stands in does not
    flushSync(() => card.dispatchEvent(dragEvent("dragstart")));
    const overPallet = dragEvent("dragover");
    column(host, "pallet").dispatchEvent(overPallet);
    expect(overPallet.defaultPrevented).toBe(true);
    const overOwn = dragEvent("dragover");
    column(host, "box").dispatchEvent(overOwn);
    expect(overOwn.defaultPrevented).toBe(false);
    flushSync(() => column(host, "box").dispatchEvent(dragEvent("drop")));
    expect(writes()).toEqual([]);

    flushSync(() => card.dispatchEvent(dragEvent("dragstart")));
    column(host, "pallet").dispatchEvent(dragEvent("dragover"));
    flushSync(() => column(host, "pallet").dispatchEvent(dragEvent("drop")));
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(writes()).toEqual(['PATCH http://api.test/api/products/11/ {"packaging":"pallet"}']);
    });
  });

  it("an axis the customer schema does not carry gets no toggle and no probe", async () => {
    // Same degrade law as every other registry: the declaration is refused
    // against the loaded document, so a client built on a plain DRF API that
    // never shipped `packaging` shows no board rather than probing a field the
    // server does not know.
    const stripped: ModelSpec[] = LIVE.models.map((m) => {
      if (m.id !== "products") return m;
      const fields = m.fields.filter((f) => f.name !== "packaging");
      return { ...m, fields, byName: Object.fromEntries(fields.map((f) => [f.name, f])) };
    });
    const NO_FIELD: AdminSchema = {
      ...LIVE,
      models: stripped,
      byId: Object.fromEntries(stripped.map((m) => [m.id, m])),
    };
    expect(axisProblem(NO_FIELD.byId["products"])).toMatch(/is not a field of "products"/);
    expect(resolveAxis(NO_FIELD.byId["products"])).toBeNull();

    const { host, toastHost } = await tableForProducts(NO_FIELD);
    expect(boardToggle(host)).toBeNull();
    await new Promise((r) => setTimeout(r, 150));
    expect(writes()).toEqual([]);
    expect(urls().some((u) => u.includes("page_size"))).toBe(false);
    expect(toastHost.textContent).toBe(""); // a refused board is not an error
    expect(host.textContent).toContain("Olives"); // and the table view still works
  });
});
