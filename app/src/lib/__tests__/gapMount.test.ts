/** Mount proof for the four components the FR-R008 gap detector still found
 *  with ZERO test references: ErrorBanner, Modules, StatsCards, QuoteCard.
 *  Same harness as chartMount.test.ts (browser resolve condition + manual
 *  flushSync). Pure-module tests stay green while a component reads the wrong
 *  store field or guesses a URL, so every assertion here is DOM- or
 *  request-level, judged THROUGH the component. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import ErrorBanner from "../../components/ErrorBanner.svelte";
import Modules from "../../pages/Modules.svelte";
import StatsCards from "../../widgets/StatsCards.svelte";
import QuoteCard from "../../widgets/QuoteCard.svelte";
import { app } from "../stores";
import { QUOTES } from "../../widgets/quotes";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

/** Modules renders the registry's discovered/refused lists — plain module
 *  arrays the real glob can only ever fill with the shipped pages (no
 *  refusals). Stubbed so the refusal branch and a parameterised row are
 *  provable without dropping a deliberately broken file into src/pages/. */
const registry = vi.hoisted(() => ({
  pages: [] as Array<Record<string, unknown>>,
  refused: [] as Array<{ id: string; path: string; reason: string }>,
}));

vi.mock("../pages", () => ({
  get pages() {
    return registry.pages;
  },
  get refusedPages() {
    return registry.refused;
  },
  pageHref: (page: { path: string }) => "#" + page.path,
}));

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
let snapshot: any;

beforeEach(() => {
  const a = get(app);
  snapshot = { ...a, schema: null, config: a.config ?? null };
  registry.pages.length = 0;
  registry.refused.length = 0;
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  mockFetch.mockReset();
  app.set(snapshot);
  vi.useRealTimers();
  vi.restoreAllMocks();
  location.hash = "";
});

function jsonReply(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

const f = (name: string, type: string, extra: Partial<FieldSpec> = {}): FieldSpec =>
  ({ name, type: type as FieldSpec["type"], required: false, readOnly: false, ...extra });

function model(id: string, name: string, fields: FieldSpec[]): ModelSpec {
  return {
    id,
    name,
    singular: id.replace(/s$/, ""),
    listPath: `/api/${id}/`,
    detailPath: `/api/${id}/{id}/`,
    fields,
    byName: Object.fromEntries(fields.map((x) => [x.name, x])),
    labelField: "id",
  };
}

const ORDERS = model("orders", "Order", [f("id", "integer"), f("status", "enum", { choices: ["pending", "paid"] })]);
const PRODUCTS = model("products", "Product", [f("id", "integer"), f("name", "string")]);
const SCHEMA: AdminSchema = {
  models: [ORDERS, PRODUCTS],
  byId: { orders: ORDERS, products: PRODUCTS },
};
/** A second, distinct schema object — for proving the load happens once. */
const SAME_AGAIN: AdminSchema = {
  models: [ORDERS, PRODUCTS],
  byId: { orders: { ...ORDERS }, products: { ...PRODUCTS } },
};

function boot(schema: AdminSchema | null = SCHEMA, extra: Record<string, unknown> = {}) {
  app.update((a) => ({ ...a, schema, token: "tkn", apiUrlOverride: "http://api.test", ...extra }));
}

/** Mount + one synchronous paint. These components render from stores only,
 *  so no waiting is needed — and under vi.useFakeTimers() a waitFor would
 *  hang on the faked clock it depends on. */
function renderSync(component: any, props = {}) {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  expect(host.childNodes.length).toBeGreaterThan(0);
  return host;
}

async function render(component: any, props = {}) {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host, props }));
  });
  await vi.waitFor(() => {
    flushSync(() => {});
    expect(host.childNodes.length).toBeGreaterThan(0);
  });
  return host;
}

async function paint(host: HTMLElement, want: () => boolean) {
  await vi.waitFor(() => {
    flushSync(() => {});
    expect(want()).toBe(true);
  });
}

const text = (host: Element) => (host.textContent ?? "").replace(/\s+/g, " ").trim();
const byText = (host: Element, sel: string) =>
  [...host.querySelectorAll(sel)].map((el) => (el.textContent ?? "").replace(/\s+/g, " ").trim());

describe("ErrorBanner", () => {
  it("renders nothing while the backend is considered up", async () => {
    boot(SCHEMA, { backendDown: false });
    const host = document.createElement("div");
    document.body.append(host);
    flushSync(() => {
      mounted.push(mount(ErrorBanner, { target: host }));
    });
    expect(host.querySelector("div")).toBeNull();
  });

  it("names the override URL, not the stored config, when both exist", async () => {
    boot(SCHEMA, {
      backendDown: true,
      apiUrlOverride: "http://override.test",
      config: { apiUrl: "http://stale.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    });
    const host = renderSync(ErrorBanner);
    expect(text(host)).toContain("http://override.test");
    expect(text(host)).not.toContain("http://stale.test");
    expect(host.querySelector("button")?.textContent).toBe("Dismiss");
  });

  it("falls back to the config URL when no override was typed", async () => {
    boot(SCHEMA, {
      backendDown: true,
      apiUrlOverride: "",
      config: { apiUrl: "http://stale.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    });
    const host = renderSync(ErrorBanner);
    expect(text(host)).toContain("http://stale.test");
  });

  it("Dismiss clears the store flag, not just the DOM", async () => {
    boot(SCHEMA, { backendDown: true, apiUrlOverride: "http://override.test" });
    const host = renderSync(ErrorBanner);
    host.querySelector("button")!.click();
    flushSync(() => {});
    expect(get(app).backendDown).toBe(false);
    expect(host.querySelector("div")).toBeNull();
  });
});

function declaredPage(id: string, title: string, path: string, over: Record<string, unknown> = {}) {
  return {
    id,
    title,
    path,
    segments: [],
    params: [],
    nav: "main",
    icon: "table",
    order: 100,
    standalone: false,
    component: () => {},
    ...over,
  };
}

describe("Modules — the R-006 self-documenting page", () => {
  it("renders one row per registered page, title and declared path", async () => {
    // 3 pages vs the schema's 2 models: the header's two numbers must differ,
    // or swapping the variables behind them reads as correct.
    registry.pages.push(
      declaredPage("dashboard", "Dashboard", "/"),
      declaredPage("modules", "Modules", "/modules"),
      declaredPage("activity", "Activity", "/activity"),
    );
    boot(SCHEMA);
    const host = renderSync(Modules);
    expect(text(host)).toContain("3 registered pages · 2 schema models");
    const rows = [...host.querySelectorAll("tbody tr")];
    expect(rows.length).toBe(3);
    // registry order is honoured, not alphabetical
    expect(byText(rows[0], "td")).toEqual(["Dashboard", "/", "main", "Open"]);
    expect(byText(rows[1], "td")).toEqual(["Modules", "/modules", "main", "Open"]);
  });

  it("prints a dash for nav:false and badges a standalone page", async () => {
    registry.pages.push(
      declaredPage("login", "Login", "/login", { nav: false, standalone: true }),
      declaredPage("branding", "Branding", "/branding", { nav: "settings" }),
    );
    boot(SCHEMA);
    const host = renderSync(Modules);
    const rows = [...host.querySelectorAll("tbody tr")];
    expect(byText(rows[0], "td")[2]).toBe("— standalone");
    expect(byText(rows[1], "td")[2]).toBe("settings");
  });

  it("offers no Open button for a parameterised page", async () => {
    registry.pages.push(
      declaredPage("model", "Model", "/m/:modelId/:recordId?", {
        nav: false,
        params: ["modelId", "recordId"],
      }),
    );
    boot(SCHEMA);
    const host = renderSync(Modules);
    expect(host.querySelectorAll("button").length).toBe(0);
    expect(text(host)).toContain("parameterised");
  });

  it("Open navigates through the registry's own href, never a hand-built one", async () => {
    registry.pages.push(declaredPage("modules", "Modules", "/modules"));
    boot(SCHEMA);
    const host = renderSync(Modules);
    host.querySelector("button")!.click();
    flushSync(() => {});
    expect(location.hash).toBe("#/modules");
  });

  it("refused declarations render with their reason verbatim", async () => {
    registry.pages.push(declaredPage("modules", "Modules", "/modules"));
    registry.refused.push({
      id: "Broken",
      path: "modules",
      reason: 'path "modules" is not absolute — declare "/modules"',
    });
    boot(SCHEMA);
    const host = renderSync(Modules);
    expect(text(host)).toContain("Refused declarations");
    expect(text(host)).toContain("Broken: path \"modules\" is not absolute — declare \"/modules\"");
    expect(host.querySelectorAll("tbody tr").length).toBe(1); // refusals register no row
  });

  it("says nothing about refusals when there are none", async () => {
    registry.pages.push(declaredPage("modules", "Modules", "/modules"));
    boot(SCHEMA);
    const host = renderSync(Modules);
    expect(text(host)).not.toContain("Refused declarations");
  });
});

describe("StatsCards — counts through the schema, never a guessed URL", () => {
  it("waits for the schema: zero requests and a skeleton grid before it lands", async () => {
    boot(null);
    const host = document.createElement("div");
    document.body.append(host);
    flushSync(() => {
      mounted.push(mount(StatsCards, { target: host }));
    });
    await new Promise((r) => setTimeout(r, 0));
    flushSync(() => {});
    expect(mockFetch).not.toHaveBeenCalled();
    expect(host.querySelectorAll(".skeleton").length).toBe(6);
  });

  it("fetches exactly one page per model via its discovered listPath + token header", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 42, results: [{ id: 1 }], next: null }));
    const host = await render(StatsCards);
    await paint(host, () => host.querySelectorAll("button").length === 2);

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const urls = mockFetch.mock.calls.map((c) => c[0]);
    expect(urls).toContain("http://api.test/api/orders/?page=1&page_size=1");
    expect(urls).toContain("http://api.test/api/products/?page=1&page_size=1");
    for (const call of mockFetch.mock.calls) {
      expect((call[1] as any).headers.Authorization).toBe("Token tkn");
    }
    expect(text(host)).toContain("42");
    expect(byText(host, "button")).toEqual(["42 Order", "42 Product"]);
  });

  it("renders the server count per model, not a row length", async () => {
    boot(SCHEMA);
    mockFetch.mockImplementation(async (url: string) =>
      jsonReply(
        url.includes("/orders/")
          ? { count: 137, results: [{ id: 1 }], next: null }
          : { count: 3, results: [{ id: 9 }], next: null },
      ),
    );
    const host = await render(StatsCards);
    await paint(host, () => host.querySelectorAll("button").length === 2);
    const cards = byText(host, "button").sort();
    expect(cards).toEqual(["137 Order", "3 Product"]);
  });

  it("a model whose count fails leaves the others painted and names the failure", async () => {
    boot(SCHEMA);
    mockFetch.mockImplementation(async (url: string) =>
      url.includes("/orders/") ? jsonReply({ detail: "boom" }, 500) : jsonReply({ count: 7, results: [], next: null }),
    );
    const host = await render(StatsCards);
    await paint(host, () => text(host).includes("Some counts could not be loaded."));
    expect(text(host)).toContain("7 Product");
    expect(text(host)).not.toContain("Order"); // no card is painted for the failed model
  });

  it("clicking a card routes to that model, keyed by model id", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 1, results: [{ id: 1 }], next: null }));
    const host = await render(StatsCards);
    await paint(host, () => host.querySelectorAll("button").length === 2);
    const productCard = [...host.querySelectorAll("button")].find((b) => (b.textContent ?? "").includes("Product"))!;
    productCard.click();
    flushSync(() => {});
    expect(location.hash).toBe("#/m/products");
  });

  it("loads once: a later schema change does not re-fire the whole sweep", async () => {
    boot(SCHEMA);
    mockFetch.mockResolvedValue(jsonReply({ count: 5, results: [], next: null }));
    const host = await render(StatsCards);
    await paint(host, () => host.querySelectorAll("button").length === 2);
    expect(mockFetch).toHaveBeenCalledTimes(2);

    app.set({ ...get(app), schema: SAME_AGAIN });
    await new Promise((r) => setTimeout(r, 0));
    flushSync(() => {});
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

describe("QuoteCard", () => {
  /** Math.random -> a finite SCRIPT of quote indices. A constant stub is a
   *  trap: randomQuote()'s exclusion loop re-rolls until it differs from the
   *  current index, so a same-value-forever stub spins the test into an OOM.
   *  `consumed` counts the draws, so the re-roll itself is assertable. */
  function rollScript(...indices: number[]) {
    const state = { consumed: 0 };
    vi.spyOn(Math, "random").mockImplementation(() => {
      const i = indices[Math.min(state.consumed, indices.length - 1)];
      state.consumed++;
      return (i + 0.5) / QUOTES.length;
    });
    return state;
  }

  it("paints the brand name and the quote its index points at", async () => {
    rollScript(3);
    app.update((a) => ({ ...a, brand: { ...a.brand, appName: "Testly" } }));
    const host = renderSync(QuoteCard);
    expect(text(host)).toContain("Testly · Daily Spark");
    expect(host.querySelector("blockquote")!.textContent).toContain(QUOTES[3].text);
    expect(host.querySelector("footer")!.textContent).toContain(QUOTES[3].source);
  });

  it("a click flips, then swaps to a different quote after the half-flip", async () => {
    vi.useFakeTimers();
    rollScript(2, 5);
    const host = renderSync(QuoteCard);
    const before = host.querySelector("blockquote")!.textContent;
    expect(before).toContain(QUOTES[2].text);

    host.querySelector("button")!.click();
    flushSync(() => {});
    expect(host.querySelector(".flip-card")!.className).toContain("flipping");
    expect(host.querySelector(".flip-card > div span:last-child")!.className).toContain("rotate-180"); // the ↻ hint
    expect(host.querySelector("blockquote")!.textContent).toBe(before); // text holds mid-flip

    vi.advanceTimersByTime(225);
    flushSync(() => {});
    expect(host.querySelector("blockquote")!.textContent).toContain(QUOTES[5].text);
    expect(host.querySelector(".flip-card")!.className).not.toContain("flipping");
    expect(host.querySelector(".flip-card > div span:last-child")!.className).not.toContain("rotate-180");
  });

  it("a re-roll that lands back on the current quote is redrawn, not repeated", async () => {
    vi.useFakeTimers();
    const rolls = rollScript(4, 4, 11); // mount, click-lands-on-current, re-roll
    const host = renderSync(QuoteCard);
    expect(host.querySelector("blockquote")!.textContent).toContain(QUOTES[4].text);
    expect(rolls.consumed).toBe(1);

    host.querySelector("button")!.click();
    vi.advanceTimersByTime(225);
    flushSync(() => {});
    expect(rolls.consumed).toBe(3); // the exclusion loop re-rolled once
    expect(host.querySelector("blockquote")!.textContent).toContain(QUOTES[11].text);
  });

  it("a second click during the flip is ignored — the swap keeps the first click's schedule", async () => {
    vi.useFakeTimers();
    rollScript(7, 8, 9);
    const host = renderSync(QuoteCard);
    const button = host.querySelector("button")!;

    button.click();
    vi.advanceTimersByTime(100);
    button.click(); // mid-flip: must be swallowed, not re-armed
    vi.advanceTimersByTime(125); // 225ms after the FIRST click
    flushSync(() => {});
    expect(host.querySelector("blockquote")!.textContent).toContain(QUOTES[8].text);

    vi.advanceTimersByTime(2000);
    flushSync(() => {});
    expect(host.querySelector("blockquote")!.textContent).toContain(QUOTES[8].text);
  });
});
