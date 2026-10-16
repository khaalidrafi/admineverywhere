/** Widget registry — auto-imports every .svelte in this folder.

Widget contract (add a widget = drop ONE file here, nothing else):
  <script module>
    export const meta = { title: "Daily Spark", size: "sm" | "lg" };
  </script>
Anything without `meta` is ignored. Files without `meta.title` never render,
so half-finished files are harmless.
*/
const modules = import.meta.glob("./*.svelte", { eager: true }) as Record<string, any>;

export interface Widget {
  file: string;
  title: string;
  size: "sm" | "lg";
  component: any;
}

export const widgets: Widget[] = Object.entries(modules)
  .filter(([, mod]) => mod?.meta?.title)
  .map(([file, mod]) => ({
    file,
    title: String(mod.meta.title),
    size: mod.meta.size === "lg" ? ("lg" as const) : ("sm" as const),
    component: mod.default,
  }))
  .sort((a, b) => a.file.localeCompare(b.file));
