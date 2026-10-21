/** FR-R008 dashboard grid proof — the widget registry rendered through Dashboard.
 *
 *  widgetMount.test.ts mounts ONE widget component; nothing yet mounted the
 *  grid that turns `widgets[]` into DOM. That grid is the only place the
 *  registry's `component` field is used for real, so it is the only place a
 *  drop-in widget can silently fail to appear.
 *
 *  Deliberately written against whatever the glob discovers (same house rule
 *  as widgets.test.ts / pages.test.ts): no pinned widget count, no widget name
 *  asserted as required — except that a widget with no `meta.title` must never
 *  reach the registry at all.
 *
 *  `$app.schema` stays null, which is also the contract for an unvisited
 *  dashboard: schema-gated widgets show their own loading placeholder and the
 *  grid asks the network for NOTHING.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import Dashboard from "../../pages/Dashboard.svelte";
import { widgets } from "../../widgets";
import { app } from "../stores";

const mockFetch = vi.fn(() => Promise.reject(new Error("no network in tests")));
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
let host: HTMLElement;

function renderDashboard(): HTMLElement {
  host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(Dashboard, { target: host }));
  });
  return host;
}

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
  mockFetch.mockClear();
  app.update((a) => ({ ...a, schema: null }));
});

describe("Dashboard renders the widget registry", () => {
  it("one grid cell per registered widget, in registry order", () => {
    const grid = renderDashboard().querySelector(".grid");
    expect(grid, "Dashboard rendered no widget grid").not.toBeNull();

    const cells = [...(grid as HTMLElement).children] as HTMLElement[];
    expect(cells.length, "grid cells != registered widgets").toBe(widgets.length);
    expect(widgets.length, "the widget glob found nothing — this test proves nothing").toBeGreaterThan(0);

    cells.forEach((cell, i) => {
      const w = widgets[i];
      const title = cell.querySelector("h2");
      expect(title, `cell ${i} rendered no title`).not.toBeNull();
      expect(title!.textContent!.trim(), `cell ${i} title != registry title`).toBe(w.title);
      // size drives the span class, and nothing else
      const spans = cell.className.includes("md:col-span-2");
      expect(spans, `cell ${i} span class wrong for size ${w.size}`).toBe(w.size === "lg");
    });
  });

  it("mounts each widget component, not just its card header", () => {
    const grid = renderDashboard().querySelector(".grid") as HTMLElement;
    const cells = [...grid.children] as HTMLElement[];

    cells.forEach((cell, i) => {
      const card = cell.querySelector(".card") as HTMLElement;
      expect(card, `cell ${i} has no card`).not.toBeNull();
      const header = card.querySelector("div.mb-3") as HTMLElement;
      expect(header, `cell ${i} has no header div`).not.toBeNull();

      // the mounted component is whatever the card holds besides the header
      const body = [...card.children].filter((c) => c !== header);
      expect(body.length, `cell ${i} rendered no widget body`).toBeGreaterThan(0);
      body.forEach((el) => expect(el.tagName, `cell ${i} body is not an element`).not.toBe("H2"));
    });
  });

  it("renders real content and asks the network for nothing before a schema", () => {
    const rendered = renderDashboard();
    // QuoteCard is schema-free, so it paints a quote immediately
    expect(rendered.querySelectorAll("blockquote").length).toBeGreaterThan(0);
    expect(mockFetch, "the dashboard fetched without a schema").not.toHaveBeenCalled();
  });
});
