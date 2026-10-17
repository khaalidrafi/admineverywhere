/** Client-side branding application — the runtime half of the brand system.
 *
 * The static half ships in the bundle (public/brand.css + brand.json,
 * written by `manage.py build_admin`) so first paint is branded with no
 * FOUC. This module is the dynamic half: whenever a brand object arrives
 * — boot fetch from a backend running the admincraft plugin, or a save
 * from the in-app editor — we inject the same `--brand-*` CSS variables
 * through a dedicated <style> element and the whole UI re-themes
 * instantly, no reload.
 *
 * Mirrors branding.py's render_css() output so the runtime look matches
 * the build-time look exactly; the server re-validates everything
 * anyway (closed schema), so this only needs defensive defaults.
 */
import type { Brand } from "./types";

const STYLE_ID = "brand-runtime";

export const BRAND_DEFAULTS = {
  primary: "#4f46e5",
  accent: "#06b6d4",
  bg: "#0f172a",
  surface: "#1e293b",
  text: "#f1f5f9",
  radius: "0.75rem",
  font: "Inter",
};

const DEFAULTS = BRAND_DEFAULTS;

/** Font names go into a CSS url() — keep to letters/digits/spaces (server
 *  enforces the same rule, this is just graceful degradation). */
export function sanitizeFont(font: string | undefined): string {
  return (font ?? DEFAULTS.font).replace(/[^A-Za-z0-9 ]/g, "").trim() || DEFAULTS.font;
}

export function brandToCss(brand: Brand): string {
  const colors = { ...DEFAULTS, ...(brand.colors ?? {}) };
  const font = sanitizeFont(brand.font);
  // "||" not "??": an empty string is not nullish but IS invalid CSS
  const radius = brand.radius || DEFAULTS.radius;
  const importName = encodeURIComponent(font).replace(/%20/g, "+");
  return `/* runtime brand — injected by admincraft */
@import url('https://fonts.googleapis.com/css2?family=${importName}:wght@400;500;600;700&display=swap');

:root {
  --brand-primary: ${colors.primary};
  --brand-accent: ${colors.accent};
  --brand-bg: ${colors.bg};
  --brand-surface: ${colors.surface};
  --brand-text: ${colors.text};
  --brand-radius: ${radius};
  --brand-font: '${font}', ui-sans-serif, system-ui, sans-serif;
}`;
}

/** Create-or-update the runtime brand <style>. Idempotent, sync, cheap. */
export function injectBrandCss(brand: Brand): void {
  if (typeof document === "undefined") return;
  let el = document.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = brandToCss(brand);
}
