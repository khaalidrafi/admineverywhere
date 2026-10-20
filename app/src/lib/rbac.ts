/** FR-R007 client side — role claims drive menu + action filtering.
 *
 *  Contract (docs/rbac.md):
 *  - the SERVER emits claims at a path the OpenAPI document advertises
 *    (GET, read-only; the normalizer records it as `schema.mePath`);
 *  - the client never guesses roles: no mePath in the schema, or a failed
 *    read, means `claims = null` and NO filtering at all — a plain DRF
 *    backend keeps the full menu (same graceful-degradation law as the
 *    static-brand fallback and the schema-gated export button);
 *  - `superuser` sees everything; otherwise a gated entry shows when the
 *    caller holds AT LEAST ONE of its required roles;
 *  - this is presentation only — the server stays the actual gate. A
 *    hidden button is UX, not security.
 *
 *  Pure module: parse + allow/filter decisions take data in and answer
 *  booleans, no store reads, no fetch (api.ts owns the transport).
 */
import type { AdminSchema, ModelSpec } from "./types";

export interface RoleClaims {
  username: string;
  isStaff: boolean;
  isSuperuser: boolean;
  roles: string[];
}

/** Tolerant parse of the /me/ body. Anything that is not recognisably a
 *  claims object answers null (→ no filtering), never a throw. */
export function parseClaims(raw: unknown): RoleClaims | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.username !== "string" || o.username === "") return null;
  return {
    username: o.username,
    isStaff: o.is_staff === true,
    isSuperuser: o.is_superuser === true,
    roles: Array.isArray(o.roles) ? o.roles.filter((r): r is string => typeof r === "string") : [],
  };
}

/** Can `claims` see something that requires `required` roles?
 *  Empty/undefined requirement → always yes. Null claims → yes (the
 *  server gave no role source, so the client applies no policy). */
export function roleAllows(required: string[] | undefined, claims: RoleClaims | null): boolean {
  if (!required || required.length === 0) return true;
  if (!claims) return true;
  if (claims.isSuperuser) return true;
  return required.some((r) => claims.roles.includes(r));
}

/** The audit model (FR-R003) behind the activity screen — resolved from
 *  the schema, never from a hand-written URL: byId first, then a path
 *  ending /audit/ for backends that rename the registration. */
export function findAuditModel(schema: AdminSchema | null): ModelSpec | null {
  if (!schema) return null;
  const direct = schema.byId["audit"] ?? schema.byId["audits"];
  if (direct) return direct;
  return schema.models.find((m) => /\/audit(s)?\/$/.test(m.listPath)) ?? null;
}
