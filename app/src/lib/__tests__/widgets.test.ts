/** widgets/index.ts tests — glob auto-import contract against real widgets. */
import { describe, expect, it } from "vitest";
import { widgets, widgetUnits } from "../widgets/index";

describe("widgets auto-import", () => {
  it("discovers all .svelte files in src/widgets/", () => {
    const widgetIds = Object.keys(widgets);
    expect(widgetIds).toHaveLength(3);
    expect(widgetIds.sort()).toEqual(["ActivityChart", "QuoteCard", "StatsCards"]);
  });

  it("extracts meta from each widget module", () => {
    expect(widgets.ActivityChart.meta).toEqual({
      title: "Activity — last 14 days",
      size: "lg",
    });
    expect(widgets.QuoteCard.meta).toEqual({
      title: "Daily Spark",
      size: "sm",
    });
    expect(widgets.StatsCards.meta).toEqual({
      title: "Records",
      size: "lg",
    });
  });

  it("assigns grid units: sm=1, lg=2", () => {
    expect(widgetUnits(widgets.QuoteCard)).toBe(1); // sm
    expect(widgetUnits(widgets.ActivityChart)).toBe(2); // lg
    expect(widgetUnits(widgets.StatsCards)).toBe(2); // lg
  });

  it("each widget has a valid component", () => {
    for (const widget of Object.values(widgets)) {
      expect(widget.component).toBeDefined();
      expect(typeof widget.component).toBe("function");
    }
  });
});
