/** branding.ts — the runtime CSS-variable injector (in-app rebranding). */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { applyBrand, BRAND_DEFAULTS, brandToCss, injectBrandCss, revertBrand, sanitizeFont } from "../branding";
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

describe("applyBrand / revertBrand (DOM side effects)", () => {
  beforeEach(() => {
    // Mock document
    document.head.innerHTML = "";
    document.title = "Old Title";
  });

  afterEach(() => {
    document.head.innerHTML = "";
  });

  it("applyBrand injects <style> and sets title", () => {
    const brand: Brand = {
      appName: "New App",
      colors: { primary: "#ff0000" },
      radius: "1rem",
      font: "Inter",
    };
    applyBrand(brand);

    const style = document.getElementById("brand-runtime") as HTMLStyleElement;
    expect(style).not.toBeNull();
    expect(style.textContent).toContain("--brand-primary: #ff0000");
    expect(document.title).toBe("New App");
  });

  it("applyBrand uses default title if appName empty", () => {
    const brand: Brand = {
      appName: "",
      colors: {},
      radius: "1rem",
      font: "Inter",
    };
    applyBrand(brand);
    expect(document.title).toBe("Admin");
  });

  it("revertBrand restores original brand", () => {
    const original: Brand = {
      appName: "Original",
      colors: { primary: "#0000ff" },
      radius: "0.5rem",
      font: "Arial",
    };
    const draft: Brand = {
      appName: "Draft",
      colors: { primary: "#ff0000" },
      radius: "1rem",
      font: "Inter",
    };

    applyBrand(draft);
    expect(document.title).toBe("Draft");

    revertBrand(original);
    expect(document.title).toBe("Original");

    const style = document.getElementById("brand-runtime") as HTMLStyleElement;
    expect(style.textContent).toContain("--brand-primary: #0000ff");
  });

  it("applyBrand is idempotent", () => {
    const brand: Brand = {
      appName: "Test",
      colors: { primary: "#ff0000" },
      radius: "1rem",
      font: "Inter",
    };

    applyBrand(brand);
    applyBrand(brand);
    applyBrand(brand);

    const styles = document.querySelectorAll("#brand-runtime");
    expect(styles.length).toBe(1);
  });
});

describe("edge cases", () => {
  it("handles undefined colors gracefully", () => {
    // sanitizeFont/colors tolerate absent values the Brand type forbids, so
    // the edge case rides one cast rather than a widened contract.
    const brand = {
      appName: "Test",
      colors: undefined,
      radius: "1rem",
      font: undefined,
    } as unknown as Brand;
    const css = brandToCss(brand);
    expect(css).toContain(`--brand-primary: ${BRAND_DEFAULTS.primary}`);
  });

  it("handles partial colors object", () => {
    const brand = {
      appName: "Test",
      colors: { primary: "#ff0000", accent: "#00ff00" },
      radius: "1rem",
      font: undefined,
    } as unknown as Brand;
    const css = brandToCss(brand);
    expect(css).toContain("--brand-primary: #ff0000");
    expect(css).toContain("--brand-accent: #00ff00");
    expect(css).toContain(`--brand-bg: ${BRAND_DEFAULTS.bg}`);
  });
});