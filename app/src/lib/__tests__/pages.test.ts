/** Page-registration contract (FR R-006) — glob auto-discovery + declared routes.
 *
 *  The product promise: a non-CRUD module is a DROP-IN, not a fork. One
 *  `.svelte` file in `src/pages/` exporting `meta{title,path,nav}` gains a
 *  route and (optionally) a sidebar entry, with no edit to any registry,
 *  to the router's route table, or to the shell.
 *
 *  Like widgets.test.ts this is written against whatever the glob discovers,
 *  never a pinned count: adding a page must widen the suite's domain, not
 *  break it. Refusal cases are driven through the pure collector with fake
 *  modules, so a broken declaration is proven nameable without a DOM.
 */
import { describe, expect, it } from "vitest";
import {
  collectPages,
  pages,
  refusedPages,
  navPages,
  pageById,
  pageHref,
  type PageMeta,
} from "../pages/index";
import { compilePattern, matchPath, parseHash, setPages, isActive } from "../router";

type FakeModule = { default?: import("svelte").Component; meta?: PageMeta };

function fakeEntries(map: Record<string, FakeModule>) {
  return Object.entries(map).map(
    ([file, mod]) => [`/src/pages/${file}.svelte`, mod] as [string, FakeModule],
  );
}

function refusalOf(map: Record<string, FakeModule>): string[] {
  const { refused } = collectPages(fakeEntries(map));
  return refused.map((r) => r.reason);
}

const OK_COMPONENT = function Page() {} as unknown as import("svelte").Component;

describe("drop-in contract: every page in src/pages registers itself", () => {
  const BUILT_INS = ["Dashboard", "ModelPage", "Branding", "Login"];

  it("discovers the built-ins without pinning the set", () => {
    const ids = pages.map((p) => p.id);
    for (const builtIn of BUILT_INS) {
      expect(ids, `missing built-in page ${builtIn}`).toContain(builtIn);
    }
    // the registry lives outside src/pages, so it can never discover itself
    expect(ids).not.toContain("index");
  });

  it("the discovered set is what a drop-in would widen — no hard-coded table", () => {
    // Nothing in the registry may enumerate ids: the only source of truth is
    // the glob. If a future edit adds a hand-written list, this fails.
    expect(pages.length).toBeGreaterThanOrEqual(BUILT_INS.length);
    expect(pages.every((p) => typeof p.id === "string" && p.id.length > 0)).toBe(true);
  });

  it("every registered page declares a usable meta and a component", () => {
    for (const page of pages) {
      expect(typeof page.title, page.id).toBe("string");
      expect(page.title.length, page.id).toBeGreaterThan(0);
      expect(page.path.startsWith("/"), `${page.id} path ${page.path}`).toBe(true);
      expect(typeof page.component, page.id).toBe("function");
    }
  });

  it("no shipped page is refused at HEAD", () => {
    expect(refusedPages.map((r) => `${r.id}: ${r.reason}`)).toEqual([]);
  });

  it("the CRUD page is parameterised and stays out of the nav", () => {
    const model = pageById("ModelPage")!;
    expect(model.path).toBe("/m/:modelId/:recordId?");
    expect(model.nav).toBe(false);
    // a nav entry for a param path is impossible (no href to build) — so it
    // must be declared nav:false, not silently linked to a template string.
    expect(refusalOf({
      Board: { default: OK_COMPONENT, meta: { title: "Board", path: "/b/:id", nav: true } },
    })).toEqual([
      'nav "main" needs a param-free path, but "/b/:id" captures id',
    ]);
  });

  it("the auth page renders outside the shell (standalone)", () => {
    const login = pageById("Login")!;
    expect(login.standalone).toBe(true);
    expect(login.nav).toBe(false);
    expect(login.path).toBe("/login");
  });

  it("nav pages carry a title, an icon and a stable order", () => {
    const nav = navPages();
    expect(nav.length).toBeGreaterThan(0);
    for (const page of nav) {
      expect(pageHref(page), page.id).toMatch(/^#\//);
      expect(typeof page.icon, page.id).toBe("string");
    }
    const orders = nav.map((p) => p.order);
    expect(orders).toEqual([...orders].sort((a, b) => a - b));
  });

  it("the sidebar groups come from declarations, not hand-written links", () => {
    // "Modules" is itself a drop-in file: it appears here because the glob
    // found it, which is the entire R-006 promise.
    expect(navPages("main").map((p) => p.id)).toContain("Modules");
    expect(navPages("main").map((p) => p.id)).toContain("Dashboard");
    expect(navPages("settings").map((p) => p.id)).toContain("Branding");
    // a param page and a standalone page can never leak into the nav
    const all = navPages();
    expect(all.map((p) => p.id)).not.toContain("ModelPage");
    expect(all.map((p) => p.id)).not.toContain("Login");
    for (const page of all) {
      expect(page.params, page.id).toEqual([]);
    }
  });
});

describe("collector: a declaration is accepted or refused with a reason", () => {
  it("ignores files with no meta (a half-finished page is harmless)", () => {
    expect(collectPages(fakeEntries({ Wip: { default: OK_COMPONENT } })).pages).toEqual([]);
    expect(
      collectPages(fakeEntries({ Wip: { default: OK_COMPONENT, meta: { title: "", path: "/x" } } }))
        .pages,
    ).toEqual([]);
  });

  it("refuses a missing, non-absolute or malformed path", () => {
    expect(refusalOf({ A: { default: OK_COMPONENT, meta: { title: "A" } as PageMeta } })).toEqual([
      'meta.path is required and must be a string, got undefined',
    ]);
    expect(
      refusalOf({ A: { default: OK_COMPONENT, meta: { title: "A", path: "about" } } }),
    ).toEqual(['path "about" does not start with "/"']);
    expect(
      refusalOf({ A: { default: OK_COMPONENT, meta: { title: "A", path: "/a//b" } } }),
    ).toEqual(['path "/a//b" has an empty segment']);
    expect(
      refusalOf({ A: { default: OK_COMPONENT, meta: { title: "A", path: "/a/:" } } }),
    ).toEqual(['path "/a/:" has a parameter with no name']);
    expect(
      refusalOf({ A: { default: OK_COMPONENT, meta: { title: "A", path: "/a/:id?", nav: false } } }),
    ).toEqual([]); // trailing optional is legal
    expect(
      refusalOf({ A: { default: OK_COMPONENT, meta: { title: "A", path: "/a/:id?/b" } } }),
    ).toEqual(['path "/a/:id?/b" puts an optional parameter before the end']);
    expect(
      refusalOf({ A: { default: OK_COMPONENT, meta: { title: "A", path: "/a/:id/:id" } } }),
    ).toEqual(['path "/a/:id/:id" repeats the parameter "id"']);
  });

  it("refuses a page with no component — a route with nothing to render", () => {
    expect(
      refusalOf({ A: { meta: { title: "A", path: "/a" } } }),
    ).toEqual(["page A declares meta but has no default export"]);
  });

  it("refuses a colliding declaration, so one hash never has two owners", () => {
    // param NAMES differ, the coverage does not: both claim /m/<anything>
    const reasons = refusalOf({
      One: { default: OK_COMPONENT, meta: { title: "One", path: "/m/:modelId", nav: false } },
      Two: { default: OK_COMPONENT, meta: { title: "Two", path: "/m/:otherId", nav: false } },
    });
    expect(reasons).toEqual([
      'path "/m/:otherId" overlaps "/m/:modelId", already claimed by "One"',
    ]);
    expect(collectPages(fakeEntries({
      One: { default: OK_COMPONENT, meta: { title: "One", path: "/m/:modelId", nav: false } },
      Two: { default: OK_COMPONENT, meta: { title: "Two", path: "/m/:otherId", nav: false } },
    })).pages.map((p) => p.id)).toEqual(["One"]);
  });

  it("the owner of the wider pattern is the first declaration, not the name", () => {
    const reversed = collectPages(fakeEntries({
      Two: { default: OK_COMPONENT, meta: { title: "Two", path: "/m/:otherId", nav: false } },
      One: { default: OK_COMPONENT, meta: { title: "One", path: "/m/:modelId", nav: false } },
    }));
    expect(reversed.pages.map((p) => p.id)).toEqual(["Two"]);
    expect(reversed.refused[0].id).toBe("One");
  });

  it("a param route and a static route at the same depth do NOT collide", () => {
    // "/m/:id" and "/m/new" are both legal; the matcher prefers the static one
    expect(
      collectPages(fakeEntries({
        Model: { default: OK_COMPONENT, meta: { title: "Model", path: "/m/:id", nav: false } },
        New: { default: OK_COMPONENT, meta: { title: "New", path: "/m/new", nav: false } },
      })).refused,
    ).toEqual([]);
  });

  it("an optional tail that swallows the shorter pattern is a collision", () => {
    const reasons = refusalOf({
      List: { default: OK_COMPONENT, meta: { title: "List", path: "/m/:id", nav: false } },
      Detail: { default: OK_COMPONENT, meta: { title: "Detail", path: "/m/:id/:rec?", nav: false } },
    });
    expect(reasons).toEqual([
      'path "/m/:id/:rec?" overlaps "/m/:id", already claimed by "List"',
    ]);
  });
});

describe("matcher: hashes resolve against declared patterns only", () => {
  const declared = [
    { id: "Login", path: "/login" },
    { id: "Dashboard", path: "/" },
    { id: "About", path: "/about" },
    { id: "ModelPage", path: "/m/:modelId/:recordId?" },
    { id: "Legacy", path: "/legacy" },
  ];

  function resolved(hash: string) {
    setPages(
      declared.map((d) => {
        const compiled = compilePattern(d.path);
        return { id: d.id, title: d.id, path: d.path, segments: compiled.segments };
      }),
    );
    return parseHash(hash);
  }

  it("matches a static route to its page", () => {
    const r = resolved("#/about");
    expect(r.kind).toBe("page");
    expect(r.pageId).toBe("About");
    expect(r.params).toEqual({});
  });

  it("matches the root path", () => {
    expect(resolved("#/").pageId).toBe("Dashboard");
    expect(resolved("#").pageId).toBe("Dashboard");
    expect(resolved("#//").pageId).toBe("Dashboard");
  });

  it("captures parameters, optional ones included", () => {
    const one = resolved("#/m/product");
    expect(one.pageId).toBe("ModelPage");
    expect(one.params).toEqual({ modelId: "product" });

    const two = resolved("#/m/product/42");
    expect(two.pageId).toBe("ModelPage");
    expect(two.params).toEqual({ modelId: "product", recordId: "42" });
  });

  it("rejects a hash with more segments than the pattern allows", () => {
    expect(resolved("#/m/product/42/extra").kind).toBe("none");
  });

  it("never guesses: an undeclared hash resolves to no page", () => {
    expect(resolved("#/nope").kind).toBe("none");
    expect(resolved("#/m").kind).toBe("none");
    expect(resolved("#/login/extra").kind).toBe("none");
  });

  it("decodes percent-encoded parameters", () => {
    expect(resolved("#/m/sales%20orders").params).toEqual({ modelId: "sales orders" });
  });

  it("prefers the static route when a static and a param route both fit", () => {
    // "/legacy" is declared; a wildcard sibling must not swallow it
    setPages([
      { id: "Anything", title: "Anything", path: "/:id", ...compilePattern("/:id") },
      { id: "Legacy", title: "Legacy", path: "/legacy", ...compilePattern("/legacy") },
    ]);
    expect(parseHash("#/legacy").pageId).toBe("Legacy");
    expect(parseHash("#/other").pageId).toBe("Anything");
  });

  it("resolves against the real registered pages at HEAD", () => {
    setPages(pages.map((p) => ({ id: p.id, title: p.title, path: p.path, segments: p.segments })));
    expect(parseHash("#/branding").pageId).toBe("Branding");
    expect(parseHash("#/m/order/7").pageId).toBe("ModelPage");
    expect(parseHash("#/m/order/7").params).toEqual({ modelId: "order", recordId: "7" });
    expect(parseHash("#/branding/deep").kind).toBe("none");
  });
});

describe("isActive: a nav entry stays lit while its sub-route is open", () => {
  it("matches exactly, and by prefix for a child path", () => {
    expect(isActive("/m/order", "/m/order")).toBe(true);
    expect(isActive("/m/order/7", "/m/order")).toBe(true);
    expect(isActive("/m/product", "/m/order")).toBe(false);
    expect(isActive("/m/orderx", "/m/order")).toBe(false);
  });

  it("the root entry is lit only on the root path", () => {
    // the naive startsWith("/") would light Dashboard on every route
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/about", "/")).toBe(false);
    expect(isActive("/m/order/7", "/")).toBe(false);
  });
});

describe("matchPath: the pure pattern matcher", () => {
  it("matches segment shapes", () => {
    const { segments } = compilePattern("/a/:b/:c?");
    expect(matchPath(segments, ["a", "b1"])).toEqual({ b: "b1" });
    expect(matchPath(segments, ["a", "b1", "c1"])).toEqual({ b: "b1", c: "c1" });
    expect(matchPath(segments, ["a"])).toBeNull();
    expect(matchPath(segments, ["a", "b1", "c1", "d1"])).toBeNull();
    expect(matchPath(segments, ["x", "b1"])).toBeNull();
  });

  it("an empty pattern only matches an empty path", () => {
    const { segments } = compilePattern("/");
    expect(matchPath(segments, [])).toEqual({});
    expect(matchPath(segments, ["about"])).toBeNull();
  });
});
