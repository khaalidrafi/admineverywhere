/** widgets/index.ts tests — glob auto-import contract.
 *
 *  Written against whatever `import.meta.glob` discovers, never a pinned count
 *  or id list: dropping a new .svelte widget into src/widgets/ must widen the
 *  suite's domain, not break it. That is the product promise in AGENTS.md
 *  ("no registry to edit"), and a toHaveLength(N) assertion punishes it.
 */
import { describe, expect, it } from "vitest";
import { widgets, widgetUnits, type Widget } from "../widgets/index";
import { validateWidgetData } from "../widgets/feed";

const BUILT_INS = [
  "ActivityChart",
  "QuoteCard",
  "StatsCards",
  // FR-R008 chart drop-ins riding the meta.data feed contract
  "TrendArea",
  "StatusDonut",
  "LeaderBars",
  "HeatStrip",
  "DeltaChip",
];

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

  it("a declared meta.data feed always validates", () => {
    // FR-R008: any widget that carries a data declaration must be usable by
    // the feed engine — a broken declaration is a build-time mistake the
    // suite catches, not something the user's dashboard silently degrades on.
    const declared = Object.values(widgets).filter((w) => w.meta.data != null);
    expect(declared.length, "at least one built-in must demonstrate the feed contract").toBeGreaterThan(0);
    for (const widget of declared) {
      const r = validateWidgetData(widget.meta.data);
      expect("spec" in r, label(widget)).toBe(true);
    }
  });
});
