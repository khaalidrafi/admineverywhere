/** FR-R001 client half, mounted for real — the wire-level proof the renderer
 *  unit tests could not give: a transition click sends exactly the bytes the
 *  server contract promises, to the URL the DOCUMENT proves, and a guard
 *  failure surfaces the server's `reason` verbatim. The same law as
 *  chatMount.test.ts (the prompt the panel ACTUALLY sends) and rbac.test.ts
 *  (the table fed through the DISCOVERED listPath): assert the wire, not a
 *  hand-written builder. Harness = browser resolve condition + flushSync +
 *  stubbed fetch, and the schema is normalizeOpenAPI of the captured fixture.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ModelPage from "../../pages/ModelPage.svelte";
import Toaster from "../../components/Toaster.svelte";
import { normalizeOpenAPI } from "../openapi";
import { lifecycleAvailable, lifecycleProblem } from "../statusTransitions";
import { app, toasts } from "../stores";
import fixture from "./fixtures/openapi.json";
import type { AdminSchema } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const hosts: Array<Record<string, any>> = [];
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

/** Route by URL so the test asserts WHICH endpoint the client believed in. */
function routeOrders(page: any, transition?: { status: number; body: any }) {
  mockFetch.mockImplementation(async (url: string) => {
    const u = String(url);
    if (u.includes("/transition/")) {
      if (!transition) throw new Error(`unexpected transition call to ${u}`);
      return reply(transition.status, transition.body);
    }
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

const PENDING_ROW = { id: 7, status: "pending", total: "12.50", customer: 3, created_at: "2026-10-20T10:00:00Z" };
const PAGE = { count: 1, results: [PENDING_ROW] };

const urls = () => mockFetch.mock.calls.map((c) => String(c[0]));
const transitionUrls = () => urls().filter((u) => u.includes("/transition/"));

describe("mounted lifecycle renderer — the bytes on the wire", () => {
  it("binds the discovered transition URL and sends only the target", async () => {
    routeOrders(PAGE, { status: 200, body: { ...PENDING_ROW, status: "paid" } });
    const { host, toastHost } = render(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("paid");
    });

    // pending's ONLY legal target — shipped/refunded must not be offered
    const buttons = [...host.querySelectorAll("button")].map((b) => b.textContent?.trim());
    expect(buttons.filter((t) => t?.startsWith("→"))).toEqual(["→ paid"]);

    const paid = [...host.querySelectorAll("button")].find((b) => b.textContent?.trim() === "→ paid")!;
    paid.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain("Transitioned to paid");
    });

    expect(transitionUrls()).toEqual(["http://api.test/api/orders/7/transition/"]);
    const init = mockFetch.mock.calls.find((c) => String(c[0]).includes("/transition/"))![1];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ transition: "paid" });
    expect(init.headers.Authorization).toBe("Token tok");
  });

  it("surfaces a 409 guard failure's reason verbatim, untranslated", async () => {
    const REASON = "pending → shipped is not allowed by the lifecycle";
    routeOrders(PAGE, { status: 409, body: { reason: REASON } });
    const { host, toastHost } = render(LIVE);
    let paid: HTMLButtonElement | undefined;
    await vi.waitFor(() => {
      flushSync(() => {});
      paid = [...host.querySelectorAll("button")].find((b) => b.textContent?.trim() === "→ paid") as HTMLButtonElement;
      expect(paid).toBeTruthy();
    });

    paid!.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(toastHost.textContent).toContain(REASON);
    });
    // the shape is exactly one key, `reason` — never a generic failure banner
    expect(toastHost.textContent).not.toContain("API 409");
  });

  it("offers nothing when the API does not document the machine", async () => {
    // Same rig, R-001 actions stripped: the client-side registry still declares
    // the machine, but there is no POST …/transition/ to bind, so the row must
    // render as plain CRUD — no dead buttons, and zero requests to a guess.
    const { transitionPath, historyPath, ...bare } = LIVE.byId.orders;
    const schema: AdminSchema = {
      ...LIVE,
      models: LIVE.models.map((m) => (m.id === "orders" ? (bare as typeof m) : m)),
      byId: { ...LIVE.byId, orders: bare as typeof LIVE.byId.orders },
    };
    expect(lifecycleAvailable(schema.byId.orders)).toBe(false);
    expect(lifecycleProblem(schema.byId.orders)).toMatch(/does not document POST/);

    routeOrders(PAGE);
    const { host } = render(schema);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });
    const targets = [...host.querySelectorAll("button")].map((b) => b.textContent?.trim() ?? "");
    expect(targets.filter((t) => t.startsWith("→"))).toEqual([]);
    expect(transitionUrls()).toEqual([]);
  });

  it("reads the trail through the discovered history path", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      const u = String(url);
      if (u.includes("/history/")) {
        return reply(200, [
          { id: 1, order: 7, from_status: "", to_status: "pending", actor: null, created_at: "2026-10-17T09:00:00Z" },
          { id: 2, order: 7, from_status: "pending", to_status: "paid", actor: "admin", created_at: "2026-10-17T11:30:00Z" },
        ]);
      }
      if (u.includes("/audit/")) return reply(200, { count: 0, results: [] });
      if (u.includes("/orders/")) return reply(200, PAGE);
      return reply(200, { count: 0, results: [] });
    });
    const { host } = render(LIVE);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("pending");
    });

    const historyBtn = host.querySelector<HTMLButtonElement>("button[title='History & audit']");
    expect(historyBtn).toBeTruthy();
    historyBtn!.click();
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("created as pending");
    });
    expect(urls().some((u) => u === "http://api.test/api/orders/7/history/")).toBe(true);
    // oldest first, as the contract pins it — the render order follows the body
    const trail = host.textContent ?? "";
    expect(trail.indexOf("created as pending")).toBeLessThan(trail.indexOf("pending → paid"));
  });
});
