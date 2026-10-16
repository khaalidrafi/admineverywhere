/** widgets/index.ts tests — glob auto-import contract. */
import { describe, expect, it, vi } from "vitest";

// Mock import.meta.glob
vi.mock("../../widgets/*.svelte", async () => {
  const { createRawSnippet } = await import("svelte");
  const mockComponent = createRawSnippet(() => ({
    render: () => "<div>Mock Widget</div>",
    setup: () => {},
  }));

  return {
    "../../widgets/TestWidget.svelte": {
      default: mockComponent,
      meta: { title: "Test Widget", size: "sm" },
    },
    "../../widgets/LargeWidget.svelte": {
      default: mockComponent,
      meta: { title: "Large Widget", size: "lg" },
    },
  };
});

describe("widgets auto-import", () => {
  it("discovers all .svelte files in src/widgets/", async () => {
    const { widgets } = await import("../widgets/index");
    expect(Object.keys(widgets)).toHaveLength(2);
    expect(widgets).toHaveProperty("TestWidget");
    expect(widgets).toHaveProperty("LargeWidget");
  });

  it("extracts meta from each module", async () => {
    const { widgets } = await import("../widgets/index");
    expect(widgets.TestWidget.meta).toEqual({ title: "Test Widget", size: "sm" });
    expect(widgets.LargeWidget.meta).toEqual({ title: "Large Widget", size: "lg" });
  });

  it("assigns grid units: sm=1, lg=2", async () => {
    const { widgets, widgetUnits } = await import("../widgets/index");
    expect(widgetUnits(widgets.TestWidget)).toBe(1);
    expect(widgetUnits(widgets.LargeWidget)).toBe(2);
  });
});
