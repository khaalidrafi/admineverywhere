/** Widgets auto-discovery via Vite glob import.
 *
 *  Any `.svelte` file in `src/widgets/` exporting:
 *    export const meta = { title: "Widget Title", size: "sm" | "lg" };
 *    export default Component;
 *
 *  will be auto-discovered here. Grid: sm = 1 unit, lg = 2 units.
 */
import type { Component } from "svelte";

export interface WidgetMeta {
  title: string;
  size: "sm" | "lg";
}

export interface Widget {
  id: string;
  meta: WidgetMeta;
  component: Component;
}

// Glob import all .svelte files in src/widgets/
const widgetModules = import.meta.glob<{
  default: Component;
  meta: WidgetMeta;
}>("../../widgets/*.svelte", { eager: true });

/** All discovered widgets, keyed by filename (without .svelte). */
export const widgets: Record<string, Widget> = Object.fromEntries(
  Object.entries(widgetModules).map(([path, mod]) => {
    const id = path.split("/").pop()!.replace(/\.svelte$/, "");
    return [
      id,
      {
        id,
        meta: mod.meta,
        component: mod.default,
      },
    ];
  })
);

/** Grid unit width: sm = 1, lg = 2. */
export function widgetUnits(w: Widget): number {
  return w.meta.size === "lg" ? 2 : 1;
}
