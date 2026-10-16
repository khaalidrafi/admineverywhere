/** widgets/index.ts tests — glob auto-import contract.
 *
 *  Written against whatever `import.meta.glob` discovers, never a pinned count
 *  or id list: dropping a new .svelte widget into src/widgets/ must widen the
 *  suite's domain, not break it. That is the product promise in AGENTS.md
 *  ("no registry to edit"), and a toHaveLength(N) assertion punishes it.
 */
import { describe, expect, it } from "vitest";
import { widgets, widgetUnits, type Widget } from "../widgets/index";

const BUILT_INS = ["ActivityChart", "QuoteCard", "StatsCards"];

function label(widget: Widget): string {
  return `${widget.id}: ${JSON.stringify(widget.meta)}`;
}

describe("widgets auto-import", () => {
  it("discovers the built-ins without pinning the set", () => {
    const ids = Object.keys(widgets);
    for (const builtIn of BUILT_INS) {
      expect(ids, `missing built-in ${builtIn}`).toContain(builtIn);
    }
    // The glob is *.svelte only — non-widget modules in the dir stay out.
    expect(ids).not.toContain("index");
    expect(ids).not.toContain("quotes");
  });

  it("every discovered widget has valid meta", () => {
    const discovered = Object.values(widgets);
    expect(discovered.length).toBeGreaterThan(0);
    for (const widget of discovered) {
      expect(typeof widget.meta.title, label(widget)).toBe("string");
      expect(widget.meta.title.length, label(widget)).toBeGreaterThan(0);
      expect(["sm", "lg"], label(widget)).toContain(widget.meta.size);
    }
  });

  it("widgetUnits maps sm->1 and lg->2 for every widget", () => {
    for (const widget of Object.values(widgets)) {
      expect(widgetUnits(widget), label(widget)).toBe(widget.meta.size === "lg" ? 2 : 1);
    }
  });

  it("every discovered widget exports a component", () => {
    for (const widget of Object.values(widgets)) {
      expect(widget.component, label(widget)).toBeDefined();
      expect(typeof widget.component, label(widget)).toBe("function");
    }
  });
});
