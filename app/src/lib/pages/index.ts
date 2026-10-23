/** Page registry — the FR R-006 drop-in contract, mirroring src/widgets/.
 *
 *  Adding a page (a non-CRUD module: a report, an audit screen, a settings
 *  pane) means dropping ONE file into `src/pages/`:
 *
 *    <script module>
 *      export const meta = {
 *        title: "Activity",          // required — no title, the file is ignored
 *        path: "/activity",          // required, absolute; :param and :param? slots
 *        nav: "main",                // false | "main" | "settings" (default "main")
 *        icon: "chat",               // sidebar Icon name
 *        order: 30,                  // sidebar sort, default 100
 *        standalone: true,           // renders outside the shell (auth gate only)
 *      };
 *    </script>
 *
 *  Nothing else is edited: the route table in lib/router.ts is injected from
 *  here, the shell renders the discovered component, and the sidebar lists the
 *  discovered nav entries. That is the whole point of R-006 — "non-CRUD modules
 *  stop being forks".
 *
 *  A declaration that cannot be honoured is REFUSED with a nameable reason
 *  (same law as an illegal kanban axis): it never registers a half-route, and
 *  `refusedPages` says why. Files with no `meta` at all are merely ignored, so
 *  a half-written page is harmless.
 */
import type { Component } from "svelte";
import { compilePattern, patternProblem, hashHref, setPages, type PatternSegment } from "../router";

export interface PageMeta {
  title: string;
  path: string;
  nav?: boolean | "main" | "settings";
  icon?: string;
  order?: number;
  standalone?: boolean;
  /** FR-R007: role names that may see this entry in the nav. Absent or
   *  empty = visible to everyone; the sidebar hides it only when the
   *  server actually emitted claims that lack every listed role. */
  roles?: string[];
}

export type NavSection = false | "main" | "settings";

export interface RegisteredPage {
  id: string;
  title: string;
  path: string;
  segments: PatternSegment[];
  params: string[];
  nav: NavSection;
  icon: string;
  order: number;
  standalone: boolean;
  component: Component;
  roles?: string[];
}

export interface RefusedPage {
  id: string;
  path: string;
  reason: string;
}

type PageModule = { default?: Component; meta?: PageMeta };

function pageIdFromPath(path: string): string {
  return path.split("/").pop()!.replace(/\.svelte$/, "");
}

function navSection(meta: PageMeta): NavSection {
  if (meta.nav === false) return false;
  if (meta.nav === "settings") return "settings";
  return "main";
}

/** Pure half of the contract: glob-shaped [path, module] entries in, the
 *  accepted + refused split out. Exported so the refusal reasons are testable
 *  with synthetic declarations, no DOM and no file writes. */
export function collectPages(
  entries: Iterable<[string, PageModule]>,
): { pages: RegisteredPage[]; refused: RefusedPage[] } {
  const accepted: RegisteredPage[] = [];
  const refused: RefusedPage[] = [];

  for (const [file, mod] of entries) {
    const meta = mod?.meta;
    if (!meta || typeof meta.title !== "string" || meta.title === "") continue; // ignored
    const id = pageIdFromPath(file);

    const problem = patternProblem(meta.path);
    if (problem) {
      refused.push({ id, path: String(meta.path ?? ""), reason: problem });
      continue;
    }
    if (!mod.default) {
      refused.push({ id, path: meta.path, reason: `page ${id} declares meta but has no default export` });
      continue;
    }

    const { segments } = compilePattern(meta.path);
    const params = segments.filter((s) => s.kind !== "static").map((s) => (s as { name: string }).name);
    const nav = navSection(meta);
    if (nav !== false && params.length > 0) {
      refused.push({
        id,
        path: meta.path,
        reason: `nav "${nav}" needs a param-free path, but "${meta.path}" captures ${params.join(", ")}`,
      });
      continue;
    }

    if (meta.roles !== undefined) {
      if (!Array.isArray(meta.roles) || meta.roles.some((r) => typeof r !== "string" || r === "")) {
        refused.push({ id, path: meta.path, reason: `roles must be a list of non-empty strings, got ${JSON.stringify(meta.roles)}` });
        continue;
      }
    }

    const clash = accepted.find((p) => overlaps(p.segments, segments));
    if (clash) {
      refused.push({
        id,
        path: meta.path,
        reason: `path "${meta.path}" overlaps "${clash.path}", already claimed by "${clash.id}"`,
      });
      continue;
    }

    accepted.push({
      id,
      title: meta.title,
      path: meta.path,
      segments,
      params,
      nav,
      icon: typeof meta.icon === "string" && meta.icon ? meta.icon : "table",
      order: typeof meta.order === "number" ? meta.order : 100,
      standalone: meta.standalone === true,
      ...(Array.isArray(meta.roles) && meta.roles.length ? { roles: meta.roles } : {}),
      component: mod.default,
    });
  }

  accepted.sort((a, b) => a.order - b.order || a.title.localeCompare(b.title) || a.id.localeCompare(b.id));
  return { pages: accepted, refused };
}

/** Do two patterns claim the same hash? Static values must agree, parameter
 *  slots are interchangeable regardless of their names, and a trailing
 *  optional slot also answers the shorter pattern's hashes — so
 *  "/m/:modelId/:recordId?" overlaps "/m/:id" even though the lengths differ.
 *  Names are irrelevant: the collision is about which hashes get an owner. */
function overlaps(a: PatternSegment[], b: PatternSegment[]): boolean {
  const shorter = a.length <= b.length ? a : b;
  const longer = a.length <= b.length ? b : a;
  for (let i = 0; i < shorter.length; i++) {
    const x = shorter[i];
    const y = longer[i];
    if (x.kind === "static" || y.kind === "static") {
      if (x.kind !== y.kind || (x as { value: string }).value !== (y as { value: string }).value) {
        return false;
      }
    }
  }
  // every segment beyond the shared prefix must be optional, or the two
  // patterns answer disjoint hash lengths
  return longer.slice(shorter.length).every((s) => s.kind === "optional");
}

const modules = import.meta.glob<{ default: Component; meta: PageMeta }>(
  "../../pages/*.svelte",
  { eager: true },
);

const collected = collectPages(Object.entries(modules));

/** Every honoured page declaration, sidebar order. */
export const pages = collected.pages;

/** Declarations that were rejected, each with the reason a reviewer can act on. */
export const refusedPages = collected.refused;

export function pageById(id: string): RegisteredPage | undefined {
  return pages.find((p) => p.id === id);
}

/** Nav entries for one section (both sections when omitted), in sidebar order. */
export function navPages(section?: "main" | "settings"): RegisteredPage[] {
  return pages.filter((p) => p.nav !== false && (section === undefined || p.nav === section));
}

/** Pages that live outside the shell — the auth gate renders these. */
export const standalonePages = pages.filter((p) => p.standalone);

/** THE auth gate: the first standalone declaration in sidebar order. App.svelte
 *  renders this and the sidebar signs out into `authHref()`, so the selection is
 *  spelled once. A client that ships its own sign-in module (`nav: false`,
 *  `standalone: true`, any path) therefore moves BOTH the gate and Sign out —
 *  which is why no component may hand-type the login route: the raw-source scan
 *  in navMount.test.ts refuses a typed hash for any declared path. */
export const authPage: RegisteredPage | undefined = standalonePages[0];

export function authHref(): string {
  return authPage ? pageHref(authPage) : "#/";
}

export function pageHref(page: RegisteredPage): string {
  return hashHref(page.path);
}

// Hand the router its route table. One call, at import time, from the glob.
setPages(pages.map((p) => ({ id: p.id, title: p.title, path: p.path, segments: p.segments, standalone: p.standalone })));
