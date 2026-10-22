/** src/widgets/index.ts tests — glob auto-import contract.
 *
 *  Importing the registry the Dashboard actually renders, not a sibling copy:
 *  a contract graded on an unused module stays green while the shipped one
 *  drifts. Written against whatever `import.meta.glob` discovers, never a
 *  pinned count or id list: dropping a new .svelte widget into src/widgets/
 *  must widen the suite's domain, not break it. That is the product promise in
 *  docs/DEVGUIDE.md ("no registry to edit"), and a toHaveLength(N) assertion
 *  punishes it.
 */
import { describe, expect, it } from "vitest";
import { widgets, widgetUnits, type Widget } from "../../widgets/index";
import { validateWidgetData } from "../widgets/feed";

// The declarations themselves, read the way the registry reads them, so the
// suite grades what a dropped-in file promises instead of only what the
// registry's own normalization handed back.
const declared = Object.entries(
  import.meta.glob("../../widgets/*.svelte", { eager: true }) as Record<string, any>,
)
  .map(([file, mod]) => ({ file, meta: mod?.meta }))
  .filter((entry) => entry.meta?.title);

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

function widgetName(w: Widget): string {
  return w.file.split("/").pop()!.replace(/\.svelte$/, "");
}

function label(widget: Widget): string {
  return `${widget.file}: ${widget.title} ${widget.size} ${JSON.stringify(widget.data)}`;
}

const synthetic = (size: "sm" | "lg"): Widget =>
  ({ file: `./Synthetic.svelte`, title: "Synthetic", size, component: () => {} }) as Widget;

describe("widgets auto-import", () => {
  it("discovers the built-ins without pinning the set", () => {
    const names = widgets.map(widgetName);
    for (const builtIn of BUILT_INS) {
      expect(names, `missing built-in ${builtIn}`).toContain(builtIn);
    }
    // The glob is *.svelte only — non-widget modules in the dir stay out.
    expect(names).not.toContain("index");
    expect(names).not.toContain("quotes");
    // A file that declares a title must never be dropped by the registry.
    for (const entry of declared) {
      expect(names, `declared widget ${entry.file} missing from the registry`)
        .toContain(entry.file.split("/").pop()!.replace(/\.svelte$/, ""));
    }
  });

  it("every discovered widget has valid meta", () => {
    expect(widgets.length).toBeGreaterThan(0);
    for (const entry of declared) {
      expect(["sm", "lg"], `declared size in ${entry.file}`).toContain(entry.meta.size);
    }
    for (const widget of widgets) {
      expect(typeof widget.title, label(widget)).toBe("string");
      expect(widget.title.length, label(widget)).toBeGreaterThan(0);
      expect(["sm", "lg"], label(widget)).toContain(widget.size);
    }
  });

  it("widgetUnits maps sm->1 and lg->2 for every widget", () => {
    expect(widgetUnits(synthetic("lg"))).toBe(2);
    expect(widgetUnits(synthetic("sm"))).toBe(1);
    for (const widget of widgets) {
      expect(widgetUnits(widget), label(widget)).toBe(widget.size === "lg" ? 2 : 1);
    }
  });

  it("every discovered widget exports a component", () => {
    for (const widget of widgets) {
      expect(widget.component, label(widget)).toBeDefined();
      expect(typeof widget.component, label(widget)).toBe("function");
    }
  });

  it("a declared meta.data feed always validates", () => {
    // FR-R008: any widget that carries a data declaration must be usable by
    // the feed engine — a broken declaration is a build-time mistake the
    // suite catches, not something the user's dashboard silently degrades on.
    const feeds = declared.filter((entry) => entry.meta.data != null);
    expect(feeds.length, "at least one built-in must demonstrate the feed contract").toBeGreaterThan(0);
    for (const entry of feeds) {
      const r = validateWidgetData(entry.meta.data);
      expect("spec" in r, `meta.data in ${entry.file}`).toBe(true);
    }
  });
});
