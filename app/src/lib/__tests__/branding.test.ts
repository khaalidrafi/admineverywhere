/** branding.ts — the runtime CSS-variable injector (in-app rebranding). */
import { describe, expect, it } from "vitest";
import { BRAND_DEFAULTS, brandToCss, injectBrandCss, sanitizeFont } from "../branding";
import type { Brand } from "../types";

const BRAND: Brand = {
  appName: "Ledgerly",
  tagline: "Quiet tools",
  colors: {
    primary: "#111111",
    accent: "#222222",
    bg: "#333333",
    surface: "#444444",
    text: "#555555",
  },
  radius: "1rem",
  font: "Space Grotesk",
};

describe("brandToCss", () => {
  it("emits every --brand-* variable with the brand values", () => {
    const css = brandToCss(BRAND);
    for (const v of ["--brand-primary", "--brand-accent", "--brand-bg",
                     "--brand-surface", "--brand-text", "--brand-radius",
                     "--brand-font"]) {
      expect(css).toContain(v);
    }
    expect(css).toContain("#111111");
    expect(css).toContain("1rem");
    expect(css).toContain("'Space Grotesk'");
  });

  it("imports the Google Font with + encoded spaces", () => {
    expect(brandToCss(BRAND)).toContain("family=Space+Grotesk");
  });

  it("falls back to defaults for missing/empty pieces", () => {
    const css = brandToCss({ appName: "X", colors: {}, radius: "", font: "" });
    expect(css).toContain(BRAND_DEFAULTS.primary);
    expect(css).toContain(BRAND_DEFAULTS.radius);
    expect(css).toContain(`'${BRAND_DEFAULTS.font}'`);
  });
});

describe("sanitizeFont", () => {
  it("keeps plain names", () => {
    expect(sanitizeFont("Inter")).toBe("Inter");
    expect(sanitizeFont("Space Grotesk")).toBe("Space Grotesk");
  });

  it("strips characters that could break out of a CSS url/string", () => {
    expect(sanitizeFont("Inter'</style>")).toBe("Interstyle");
    expect(sanitizeFont("Bad();'\" Font")).toBe("Bad Font");
  });

  it("falls back to the default when nothing survives", () => {
    expect(sanitizeFont("<>")).toBe(BRAND_DEFAULTS.font);
  });
});

describe("injectBrandCss", () => {
  it("creates exactly one style element and updates it in place", () => {
    injectBrandCss(BRAND);
    const el = document.getElementById("brand-runtime") as HTMLStyleElement | null;
    expect(el).toBeTruthy();
    expect(el!.tagName).toBe("STYLE");
    expect(el!.textContent).toContain("#111111");

    injectBrandCss({ ...BRAND, colors: { ...BRAND.colors, primary: "#abcdef" } });
    const again = document.getElementById("brand-runtime");
    expect(again).toBe(el); // same node, patched
    expect(again!.textContent).toContain("#abcdef");
    expect(again!.textContent).not.toContain("#111111");
    expect(document.querySelectorAll("#brand-runtime")).toHaveLength(1);
  });
});
