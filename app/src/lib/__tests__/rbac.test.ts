/** FR-R007 — role claims: discovery, parsing, gating, and the Activity
 *  screen mounted for real. Same harness as widgetMount/shell (browser
 *  resolve condition + manual flushSync + fetch stubbed). */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import { findAuditModel, parseClaims, roleAllows, type RoleClaims } from "../rbac";
import { normalizeOpenAPI } from "../openapi";
import { collectPages } from "../pages/index";
import { actionsFor, type RegisteredAction } from "../actions/index";
import { app } from "../stores";
import Activity from "../../pages/Activity.svelte";
import type { AdminSchema, FieldSpec, ModelSpec } from "../types";

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
