/** Hash router — bulletproof in web mode, Tauri, and packaged file builds.
 *
 *  FR R-006: this module owns NO route table. Pages are DECLARED by the page
 *  files themselves (`src/pages/*.svelte` exporting `meta{title,path,…}`) and
 *  injected via `setPages()` by `lib/pages/index.ts`, which discovers them with
 *  a Vite glob. Adding a module therefore touches one file: the module.
 *
 *  Patterns in a `meta.path`:
 *    "/"                    root, exact
 *    "/branding"            static segment
 *    "/m/:modelId"          captured segment → props
 *    "/m/:modelId/:recordId?" trailing optional segment (absent → not captured)
 *
 *  An unknown hash resolves to `kind: "none"` — the router never guesses a
 *  page from a prefix, the same law as the kanban axis and action paths.
 */
import { writable } from "svelte/store";

export type PatternSegment =
  | { kind: "static"; value: string }
  | { kind: "param"; name: string }
  | { kind: "optional"; name: string };

/** What the router needs to know about a page. `lib/pages` builds these. */
export interface RoutePage {
  id: string;
  title: string;
  /** declared pattern, e.g. "/m/:modelId/:recordId?" — for hrefs + debug only */
  path: string;
  segments: PatternSegment[];
  /** rendered outside the shell (the auth gate) — never inside it */
  standalone?: boolean;
}

export interface Route {
  kind: "page" | "none";
  pageId: string | null;
  title: string;
  /** the concrete normalized path of the current hash, e.g. "/m/order/7" */
  path: string;
  params: Record<string, string>;
  standalone: boolean;
}

/** "/a/b" -> ["a","b"]; "/" -> []. Percent-decodes each segment. */
export function splitPath(path: string): string[] {
  const trimmed = (path || "/").replace(/^#/, "").replace(/^\/+/, "").replace(/\/+$/, "");
  if (trimmed === "") return [];
  return trimmed.split("/").map((s) => {
    try {
      return decodeURIComponent(s);
    } catch {
      return s; // a malformed escape stays literal rather than throwing
    }
  });
}

/** Why a `meta.path` is not a compilable pattern, or null when it is. */
export function patternProblem(path: unknown): string | null {
  if (typeof path !== "string") return `meta.path is required and must be a string, got ${String(path)}`;
  if (!path.startsWith("/")) return `path "${path}" does not start with "/"`;
  const raw = splitRaw(path);
  if (raw.some((s) => s === "")) return `path "${path}" has an empty segment`;
  const names: string[] = [];
  for (let i = 0; i < raw.length; i++) {
    const seg = raw[i];
    if (!seg.startsWith(":")) continue;
    const optional = seg.endsWith("?");
    const name = optional ? seg.slice(1, -1) : seg.slice(1);
    if (name === "") return `path "${path}" has a parameter with no name`;
    if (optional && i !== raw.length - 1) {
      return `path "${path}" puts an optional parameter before the end`;
    }
    if (names.includes(name)) return `path "${path}" repeats the parameter "${name}"`;
    names.push(name);
  }
  return null;
}

function splitRaw(path: string): string[] {
  const trimmed = path.replace(/^\/+/, "").replace(/\/+$/, "");
  return trimmed === "" ? [] : trimmed.split("/");
}

/** Compile a validated pattern. Call `patternProblem` first — an invalid
 *  pattern compiles to a shape that simply never matches. */
export function compilePattern(path: string): { segments: PatternSegment[] } {
  const segments: PatternSegment[] = splitRaw(path).map((seg) => {
    if (!seg.startsWith(":")) return { kind: "static", value: seg };
    const optional = seg.endsWith("?");
    const name = optional ? seg.slice(1, -1) : seg.slice(1);
    return optional ? { kind: "optional", name } : { kind: "param", name };
  });
  return { segments };
}

/** Match concrete path segments against a compiled pattern; null if no fit. */
export function matchPath(
  segments: PatternSegment[],
  parts: string[],
): Record<string, string> | null {
  const params: Record<string, string> = {};
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (seg.kind === "static") {
      if (parts[i] !== seg.value) return null;
    } else if (seg.kind === "param") {
      if (parts[i] === undefined) return null;
      params[seg.name] = parts[i];
    } else if (parts[i] !== undefined) {
      params[seg.name] = parts[i];
    }
  }
  if (parts.length > segments.length) return null;
  // a required param the path did not supply (optional counted past its slot)
  for (const seg of segments) {
    if (seg.kind === "param" && !(seg.name in params)) return null;
  }
  return params;
}

/** Fewest captures wins, so "/legacy" is not swallowed by a "/:id" sibling. */
function specificity(page: RoutePage): number {
  return page.segments.filter((s) => s.kind !== "static").length;
}

let pages: RoutePage[] = [];

/** Inject the declared pages. Called once by `lib/pages/index.ts` at import
 *  time; exported for tests, which drive the matcher with synthetic sets. */
export function setPages(next: RoutePage[]): void {
  pages = [...next].sort((a, b) => specificity(a) - specificity(b) || a.id.localeCompare(b.id));
  route.set(parseHash());
}

export function registeredPages(): RoutePage[] {
  return pages;
}

function normalize(hash: string): string {
  const h = (hash || "#/").replace(/^#/, "");
  const path = "/" + splitPath(h).filter((s) => s !== "").join("/");
  return path === "/" ? "/" : path.replace(/\/+$/, "");
}

/** Resolve a hash against the declared pages. Never guesses. */
export function parseHash(hash: string = typeof location !== "undefined" ? location.hash : "#/"): Route {
  const path = normalize(hash);
  const parts = path === "/" ? [] : path.slice(1).split("/");
  for (const page of pages) {
    const params = matchPath(page.segments, parts);
    if (params) {
      return {
        kind: "page",
        pageId: page.id,
        title: page.title,
        path,
        params,
        standalone: page.standalone === true,
      };
    }
  }
  return { kind: "none", pageId: null, title: "", path, params: {}, standalone: false };
}

export const route = writable<Route>(parseHash("#/"));

if (typeof window !== "undefined") {
  window.addEventListener("hashchange", () => route.set(parseHash()));
}

export function navigate(hash: string): void {
  if (location.hash === hash) {
    route.set(parseHash()); // re-trigger for same-hash nav
  } else {
    location.hash = hash;
  }
}

/** Turn a declared path (or a built one) into a hash href. */
export function hashHref(path: string): string {
  return "#" + (path.startsWith("/") ? path : "/" + path);
}

/** Is the current path this nav entry — including one of its child paths?
 *  Root is exact-only, otherwise startsWith("/") would light on everything. */
export function isActive(currentPath: string, navPath: string): boolean {
  if (navPath === "/" || navPath === "") return currentPath === "/";
  return currentPath === navPath || currentPath.startsWith(navPath + "/");
}
