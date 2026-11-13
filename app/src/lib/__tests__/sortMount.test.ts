/** Changelist sorting + generic delete-selected, mounted for real — the wire
 *  proof of the django.contrib.admin parity slice: a header click sends
 *  ?ordering= (the param the DOCUMENT promised, DRF OrderingFilter wire) and
 *  the selection bar's delete hands one confirmed DELETE per selected row.
 *  Same law as lifecycleMount.test.ts — assert the bytes, not a builder. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPage from "../../pages/ModelPage.svelte";
import Toaster from "../../components/Toaster.svelte";
import type { AdminSchema, ModelSpec } from "../types";
import { app, toasts } from "../stores";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const hosts: Array<Record<string, any>> = [];
afterEach(() => {
  while (hosts.length) unmount(hosts.pop()!.instance);
  hosts.length = 0;
  mockFetch.mockReset();
  toasts.set([]);
  app.set({} as any);
  // Pops the confirm stub AND the fetch stub; the next beforeEach re-stubs
  // fetch so the module-level wiring stays the single source of truth.
  vi.unstubAllGlobals();
});
beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
});

function reply(status: number, data: any) {
  return { ok: status < 400, status, json: async () => data, text: async () => JSON.stringify(data) };
}

const SORT_MODEL: ModelSpec = {
  id: "things",
  name: "Thing",
  singular: "thing",
  listPath: "/api/things/",
  detailPath: "/api/things/{id}/",
  ordering: true,
  fields: [
    { name: "id", type: "number", required: false, readOnly: true },
    { name: "name", type: "text", required: false, readOnly: false },
    { name: "price", type: "number", required: false, readOnly: false },
  ],
  byName: {},
  labelField: "name",
};
SORT_MODEL.byName = Object.fromEntries(SORT_MODEL.fields.map((f) => [f.name, f]));

const PLAIN_MODEL: ModelSpec = { ...SORT_MODEL, ordering: undefined };
delete (PLAIN_MODEL as any).ordering;

const SCHEMA: AdminSchema = { models: [SORT_MODEL, PLAIN_MODEL], byId: { things: SORT_MODEL, plain: PLAIN_MODEL } };

const ROWS = [
  { id: 1, name: "Alpha", price: "5.00" },
  { id: 2, name: "Beta", price: "9.00" },
];

function routeThings() {
  mockFetch.mockImplementation(async (url: string, init: any) => {
    const u = String(url);
    if (init?.method === "DELETE") return reply(204, null);
    if (u.includes("/things/")) return reply(200, { count: ROWS.length, results: ROWS, next: null, previous: null });
    return reply(200, { count: 0, results: [] });
  });
}

function render(modelId: string) {
  const host = document.createElement("div");
  const toastHost = document.createElement("div");
  document.body.append(host, toastHost);
  app.update((a) => ({
    ...a,
    schema: SCHEMA,
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
const listUrls = () => urls().filter((u) => u.includes("/things/") && !u.includes("/things/1/") && !u.includes("/things/2/"));
const button = (host: HTMLElement, text: string) =>
  [...host.querySelectorAll("button")].find((b) => b.textContent?.trim() === text) as HTMLButtonElement | undefined;
const buttonByTitle = (host: HTMLElement, title: string) =>
  [...host.querySelectorAll("button")].find((b) => b.getAttribute("title") === title) as HTMLButtonElement | undefined;

describe("mounted changelist sorting — the bytes on the wire", () => {
  beforeEach(() => {
    routeThings();
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  it("sends ordering= on the first header click, flips on the second", async () => {
    const { host } = render("things");
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Alpha");
    });

    const sortName = buttonByTitle(host, "Sort by name");
    expect(sortName).toBeTruthy(); // the document carries ordering -> headers are toggles

    sortName!.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(listUrls().some((u) => u.endsWith("ordering=name"))).toBe(true);
    });

    sortName!.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(listUrls().some((u) => u.endsWith("ordering=-name"))).toBe(true);
    });

    // a new column starts ascending again
    buttonByTitle(host, "Sort by price")!.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(listUrls().some((u) => u.endsWith("ordering=price"))).toBe(true);
    });
  });

  it("renders no sort toggles when the document carries no ordering param", async () => {
    const { host } = render("plain");
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Alpha");
    });
    expect(buttonByTitle(host, "Sort by name")).toBeUndefined();
    expect(listUrls().every((u) => !u.includes("ordering="))).toBe(true);
  });

  it("delete-selected fires one confirmed DELETE per selected row", async () => {
    const { host, toastHost } = render("things");
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Alpha");
    });

    // select both rows, the selection bar must light with the generic action
    const boxes = [...host.querySelectorAll('input[type="checkbox"][aria-label="Select row"]')] as HTMLInputElement[];
    expect(boxes.length).toBe(2);
    flushSync(() => boxes.forEach((b) => b.click()));
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(button(host, "Delete selected")).toBeTruthy();
    });

    button(host, "Delete selected")!.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("2 Thing records deleted");
    });

    const deletes = mockFetch.mock.calls.filter((c) => (c[1] as any)?.method === "DELETE");
    expect(deletes.map((c) => String(c[0])).sort()).toEqual([
      "http://api.test/api/things/1/",
      "http://api.test/api/things/2/",
    ]);
    const confirmMock = confirm as unknown as ReturnType<typeof vi.fn>;
    expect(confirmMock).toHaveBeenCalledWith("Delete 2 Thing record(s)? This cannot be undone.");
  });

  it("a refused delete fails only its own row and says so", async () => {
    mockFetch.mockImplementation(async (url: string, init: any) => {
      const u = String(url);
      if (init?.method === "DELETE") {
        return u.includes("/things/1/") ? { ok: false, status: 403, json: async () => ({}), text: async () => "{}" } : reply(204, null);
      }
      if (u.includes("/things/")) return reply(200, { count: ROWS.length, results: ROWS, next: null, previous: null });
      return reply(200, { count: 0, results: [] });
    });
    vi.stubGlobal("confirm", vi.fn(() => true));

    const { host, toastHost } = render("things");
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Alpha");
    });

    const boxes = [...host.querySelectorAll('input[type="checkbox"][aria-label="Select row"]')] as HTMLInputElement[];
    flushSync(() => boxes.forEach((b) => b.click()));
    button(host, "Delete selected")!.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("1 deleted, 1 failed");
    });
  });
});
