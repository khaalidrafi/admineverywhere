/** FR-R007 — role claims: discovery, parsing, gating, and the Activity
 *  screen mounted for real. Same harness as widgetMount/shell (browser
 *  resolve condition + manual flushSync + fetch stubbed). */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import { findAuditModel, parseClaims, roleAllows, type RoleClaims } from "../rbac";
import { normalizeOpenAPI } from "../openapi";
import { collectPages, navPages, pages } from "../pages/index";
import { app, claims } from "../stores";
import { actions, actionsFor, type RegisteredAction } from "../actions/index";
import Activity from "../../pages/Activity.svelte";
import Modules from "../../pages/Modules.svelte";
import Sidebar from "../../components/Sidebar.svelte";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

/** Mount any component through the same manual-flush harness as renderActivity. */
function mountComponent(component: any): HTMLElement {
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push(mount(component, { target: host }));
  });
  return host;
}

const buttonLabels = (host: HTMLElement) =>
  [...host.querySelectorAll("button")].map((b) => (b.textContent ?? "").replace(/\s+/g, " ").trim());

/** The sidebar's two declared groups, exactly as navMount reads them: the
 *  `<nav>` holds the main entries (plus schema Models, and no schema is
 *  mounted here), and the settings block exists only when something declares it. */
function navGroups(host: HTMLElement): { main: string[]; settings: string[] } {
  const nav = host.querySelector("nav");
  if (!nav) throw new Error("the sidebar rendered no <nav> group");
  const label = (el: Element) => (el.textContent ?? "").replace(/\s+/g, " ").trim();
  const blocks = [...host.querySelectorAll("div")].filter((d) =>
    [...d.children].some((c) => label(c) === "Settings"),
  );
  return {
    main: buttonLabels(nav),
    settings: blocks.length ? buttonLabels(blocks[0]) : [],
  };
}

// ---------------------------------------------------------------------------
// pure decisions
// ---------------------------------------------------------------------------

describe("parseClaims", () => {
  it("accepts the /me/ shape", () => {
    const c = parseClaims({ username: "admin", is_staff: true, is_superuser: false, roles: ["auditors"] });
    expect(c).toEqual({ username: "admin", isStaff: true, isSuperuser: false, roles: ["auditors"] });
  });
  it("tolerates missing/garbage fields instead of throwing", () => {
    expect(parseClaims({ username: "x" })).toEqual({ username: "x", isStaff: false, isSuperuser: false, roles: [] });
    expect(parseClaims({ username: "x", roles: ["ok", 7, null] })).toEqual({ username: "x", isStaff: false, isSuperuser: false, roles: ["ok"] });
  });
  it("answers null for anything not a claims object", () => {
    for (const junk of [null, undefined, 42, "me", [], {}, { username: "" }, { roles: ["a"] }]) {
      expect(parseClaims(junk), String(junk)).toBeNull();
    }
  });
});

describe("roleAllows", () => {
  const member: RoleClaims = { username: "m", isStaff: true, isSuperuser: false, roles: ["auditors"] };
  it("never gates an ungated entry", () => {
    expect(roleAllows(undefined, member)).toBe(true);
    expect(roleAllows([], member)).toBe(true);
    expect(roleAllows(["auditors"], null)).toBe(true); // no claims = no filtering
  });
  it("superusers see everything, holders see their roles, others do not", () => {
    const root: RoleClaims = { username: "r", isStaff: true, isSuperuser: true, roles: [] };
    expect(roleAllows(["managers"], root)).toBe(true);
    expect(roleAllows(["managers", "auditors"], member)).toBe(true);
    expect(roleAllows(["managers"], member)).toBe(false);
    expect(roleAllows(["managers"], { ...member, roles: [] })).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// schema discovery (the evidence law: paths come from the document)
// ---------------------------------------------------------------------------

function tinyDoc(withMe: boolean, meHasPost = false): any {
  const paths: Record<string, any> = {
    "/api/orders/": { get: {}, post: {} },
    "/api/audit/": { get: {}, post: {} },
  };
  if (withMe) paths["/api/me/"] = meHasPost ? { get: {}, post: {} } : { get: {} };
  return { openapi: "3.0.3", paths, components: { schemas: {} } };
}

describe("normalizeOpenAPI mePath", () => {
  it("binds GET …/me/ only when the document has get && !post", () => {
    expect(normalizeOpenAPI(tinyDoc(true)).mePath).toBe("/api/me/");
    expect(normalizeOpenAPI(tinyDoc(true, true)).mePath).toBeUndefined();
    expect(normalizeOpenAPI(tinyDoc(false)).mePath).toBeUndefined();
  });
  it("…/me/ is never a model (list discovery needs get && post)", () => {
    const schema = normalizeOpenAPI(tinyDoc(true));
    expect(schema.byId["me"]).toBeUndefined();
  });
});

describe("findAuditModel", () => {
  const f = (name: string): FieldSpec => ({ name, type: "text", required: false, readOnly: false });
  const audit: ModelSpec = {
    id: "audit", name: "Audit", singular: "audit", listPath: "/api/audit/",
    detailPath: "/api/audit/{id}/", fields: [f("summary")], byName: {}, labelField: "id",
  };
  const schema: AdminSchema = { models: [audit], byId: { audit } };
  it("resolves through the schema, renamed path included", () => {
    expect(findAuditModel(schema)?.listPath).toBe("/api/audit/");
    const renamed = {
      models: [audit],
      byId: {},
    };
    expect(findAuditModel(renamed)?.listPath).toBe("/api/audit/");
  });
  it("null for a schema with no audit model (friendly empty, never a guess)", () => {
    expect(findAuditModel(null)).toBeNull();
    expect(findAuditModel({ models: [], byId: {} })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// registries honour roles
// ---------------------------------------------------------------------------

describe("collectPages + roles", () => {
  const comp = (() => null) as any;
  it("keeps valid role declarations on the registered page", () => {
    const { pages, refused } = collectPages([
      ["/x/Gated.svelte", { default: comp, meta: { title: "G", path: "/g", roles: ["auditors"] } }],
    ]);
    expect(refused).toEqual([]);
    expect(pages[0].roles).toEqual(["auditors"]);
  });
  it("refuses a non-string roles list with a nameable reason", () => {
    const { refused } = collectPages([
      ["/x/Bad.svelte", { default: comp, meta: { title: "B", path: "/b", roles: ["ok", 7] as unknown as string[] } }],
    ]);
    expect(refused).toHaveLength(1);
    expect(refused[0].reason).toContain("roles must be a list");
  });
});

describe("actionsFor + claims", () => {
  const mk = (id: string, roles?: string[]): [string, RegisteredAction] => [
    id,
    { id, meta: { label: id, scope: "bulk", model: "orders", ...(roles ? { roles } : {}), handler: async () => [] } },
  ];
  const source = Object.fromEntries([mk("open"), mk("managed", ["managers"])]);
  const member: RoleClaims = { username: "m", isStaff: false, isSuperuser: false, roles: ["auditors"] };
  const manager: RoleClaims = { username: "q", isStaff: false, isSuperuser: false, roles: ["managers"] };
  it("shows gated actions only to holders, and everything when unclaimed", () => {
    expect(actionsFor("orders", "bulk", source, null).map((a) => a.id)).toEqual(["managed", "open"]);
    expect(actionsFor("orders", "bulk", source, member).map((a) => a.id)).toEqual(["open"]);
    expect(actionsFor("orders", "bulk", source, manager).map((a) => a.id)).toEqual(["managed", "open"]);
  });
});

describe("the seeded demo rig's live claims", () => {
  // Bodies captured verbatim from GET /api/me/ against a seeded, running
  // demo backend (manage.py runserver :8013), i.e. the two logins the
  // docs/rbac.md table advertises. The point is the REJECTION row: a rig
  // whose only user is a superuser can never show a hidden button, so the
  // single-role caller is what makes R-007's gate demonstrable end to end.
  const ADMIN_LIVE = { username: "admin", is_staff: true, is_superuser: true, roles: ["auditors", "managers"] };
  const AUDITOR_LIVE = { username: "auditor", is_staff: false, is_superuser: false, roles: ["auditors"] };

  it("parses both, and the real registry gates bulk_flag for one of them", () => {
    const admin = parseClaims(ADMIN_LIVE);
    const auditor = parseClaims(AUDITOR_LIVE);
    expect(admin?.isSuperuser).toBe(true);
    expect(auditor).toEqual({ username: "auditor", isStaff: false, isSuperuser: false, roles: ["auditors"] });
    // The DISCOVERED registry (app/src/actions/), not a hand-made source.
    expect(actionsFor("orders", "bulk", actions, admin).map((a) => a.id)).toContain("bulk_flag");
    expect(actionsFor("orders", "bulk", actions, auditor).map((a) => a.id)).not.toContain("bulk_flag");
  });

  it("leaves ungated actions visible to the single-role caller", () => {
    const auditor = parseClaims(AUDITOR_LIVE)!;
    expect(actionsFor("orders", "record", actions, auditor).map((a) => a.id)).toContain("flag");
  });

  // The NAV half of that live case, on the REAL glob. Until this fired the
  // reference app shipped NO page declaring `roles`, so the only demonstrable
  // rejection was an action button: docs/rbac.md advertised a gated nav entry
  // that no dropped-in file actually declared, and a seat could delete either
  // filtering leg of Sidebar.svelte with every suite green (measured — the
  // main-group mutant survived until each group was asserted as an exact set).
  describe("nav gating on the shipped registry", () => {
    const auditor = parseClaims(AUDITOR_LIVE)!;
    const admin = parseClaims(ADMIN_LIVE)!;
    const manager: RoleClaims = { username: "boss", isStaff: true, isSuperuser: false, roles: ["managers"] };
    const gated = pages.filter((p) => p.nav && p.roles && p.roles.length > 0);

    /** A page must be gated in EACH group, or the other leg is graded by
     *  vacuous truth — the shape that let the main-filter mutant survive. */
    it("the reference app gates at least one main entry and one settings entry", () => {
      for (const group of ["main", "settings"] as const) {
        const inGroup = gated.filter((p) => p.nav === group);
        expect(inGroup.length, `no ${group}-nav page declares meta.roles`).toBeGreaterThan(0);
        expect(
          inGroup.some((p) => !roleAllows(p.roles, auditor)),
          `every ${group} gate is a role the seeded auditor already holds: ${inGroup.map((p) => `${p.id}=${p.roles}`).join(", ")}`,
        ).toBe(true);
      }
    });

    it("each rendered group is exactly what roleAllows declares, for four claims states", () => {
      const expectGroup = (group: "main" | "settings", c: RoleClaims | null) =>
        navPages(group).filter((p) => roleAllows(p.roles, c)).map((p) => p.title);

      for (const [who, value] of [
        ["no claims (plain DRF: no filtering)", null],
        ["the seeded auditor (rejection case)", auditor],
        ["a managers holder (acceptance case)", manager],
        ["the seeded superuser (short-circuit)", admin],
      ] as Array<[string, RoleClaims | null]>) {
        claims.set(value);
        const host = mountComponent(Sidebar);
        const groups = navGroups(host);
        expect(groups.main, `${who}: main group`).toEqual(expectGroup("main", value));
        expect(groups.settings, `${who}: settings group`).toEqual(expectGroup("settings", value));
        unmount(mounted.pop()!);
      }
      claims.set(null);
      // sanity on the rejection row itself, so a vanished gate cannot hide
      // inside an equally-empty expectation on both sides of the compare
      const host = mountComponent(Sidebar);
      expect(navGroups(host).settings).toContain(gated.find((p) => p.nav === "settings")!.title);
      claims.set(auditor);
      flushSync(() => {});
      expect(navGroups(host).settings).not.toContain("Branding");
      expect(navGroups(host).main).not.toContain("Modules");
      expect(navGroups(host).main.length).toBeGreaterThan(0);
      unmount(mounted.pop()!);
      claims.set(null);
    });

    it("the Modules screen hides no row but withholds the Open click for the same caller", () => {
      claims.set(auditor);
      const host = mountComponent(Modules);
      const rows = [...host.querySelectorAll("tbody tr")];
      expect(rows.length, "a gated page vanished from the registry inspector").toBe(pages.length);
      const gatedRow = rows.find((r) => (r.textContent ?? "").includes(gated[0].title))!;
      expect(gatedRow.textContent).toContain(`gated · ${gated[0].roles!.join(" / ")}`);
      expect(gatedRow.querySelector("button")).toBeNull();
      unmount(mounted.pop()!);

      claims.set(null);
      const plainRow = [...mountComponent(Modules).querySelectorAll("tbody tr")].find((r) =>
        (r.textContent ?? "").includes(gated[0].title),
      )!;
      expect(plainRow.querySelector("button")?.textContent).toContain("Open");
      unmount(mounted.pop()!);
      claims.set(null);
    });
  });
});

// ---------------------------------------------------------------------------
// the Activity screen, mounted for real
// ---------------------------------------------------------------------------
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  mockFetch.mockReset();
});

function jsonReply(data: any) {
  return { ok: true, status: 200, json: async () => data, text: async () => JSON.stringify(data) };
}

const auditFields = (name: string, type: FieldSpec["type"], readOnly = false): FieldSpec =>
  ({ name, type, required: false, readOnly });
const AUDIT: ModelSpec = {
  id: "audit", name: "Audit", singular: "audit", listPath: "/api/audit/",
  detailPath: "/api/audit/{id}/",
  fields: [auditFields("summary", "text"), auditFields("created_at", "datetime", true)],
  byName: {}, labelField: "id",
};
AUDIT.byName = Object.fromEntries(AUDIT.fields.map((x) => [x.name, x]));

function renderActivity(schema: AdminSchema | null) {
  const host = document.createElement("div");
  document.body.append(host);
  app.update((a) => ({ ...a, schema, token: "tok", apiUrlOverride: "http://api.test", config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" }, booted: true }));
  flushSync(() => {
    mounted.push(mount(Activity, { target: host }));
  });
  return host;
}

describe("mounted Activity page", () => {
  it("feeds the table through the schema-discovered audit listPath", async () => {
    mockFetch.mockResolvedValue(
      jsonReply({
        count: 1,
        results: [{ id: 7, action: "order.flag", object_type: "order", object_id: "3", actor: "admin", summary: "Order flagged: twice", created_at: "2026-10-20T10:00:00Z" }],
      }),
    );
    const host = renderActivity({ models: [AUDIT], byId: { audit: AUDIT } });
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Order flagged: twice");
    });
    const url = String(mockFetch.mock.calls[0][0]);
    expect(url).toContain("/api/audit/");
    expect(host.textContent).toContain("admin");
    expect(host.textContent).toContain("order.flag");
  });

  it("renders a nameable refusal when the backend has no audit endpoint", async () => {
    const host = renderActivity({ models: [], byId: {} });
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("No audit endpoint");
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
