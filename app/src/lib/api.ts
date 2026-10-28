/** api.ts — thin DRF client. Token auth, pagination, search.

Every failure is normalized to ApiError so the UI can react:
- network:true  -> backend unreachable (banner)
- status:401     -> session expired (logout)
- status:400     -> validation errors (field-level display)
*/
import { normalizeOpenAPI } from "./openapi";
import { exportFileName } from "./csv";
import { parseClaims, type RoleClaims } from "./rbac";
import type { AdminSchema, AppConfig, AuditEntry, Brand, ModelSpec, Page, RecordRow } from "./types";

export class ApiError extends Error {
  status?: number;
  network?: boolean;
  detail?: any;
  constructor(message: string, opts: { status?: number; network?: boolean; detail?: any } = {}) {
    super(message);
    this.status = opts.status;
    this.network = opts.network;
    this.detail = opts.detail;
  }
}

/** Redact tokens/passwords from error details to prevent leakage in logs. */
function redactSecrets(obj: any): any {
  if (!obj || typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map(redactSecrets);
  const out: any = {};
  for (const [k, v] of Object.entries(obj)) {
    if (/^(token|password|api_?key|secret|authorization)$/i.test(k)) {
      out[k] = "********";
    } else {
      out[k] = redactSecrets(v);
    }
  }
  return out;
}

/** The API origin used for every call: no trailing slash, credentials gone
 *  (a token never travels inside a URL where proxies and logs can see it). */
function baseUrl(cfg: AppConfig): string {
  let url = cfg.apiUrl.replace(/\/+$/, "");
  try {
    const u = new URL(url);
    if (u.username || u.password) {
      u.username = "";
      u.password = "";
      url = u.toString().replace(/\/$/, "");
    }
  } catch {}
  return url;
}

async function request<T>(cfg: AppConfig, token: string | null, path: string,
                          init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Token ${token}` } : {}),
  };

  const url = baseUrl(cfg);
  let resp: Response;
  try {
    resp = await fetch(url + path, { ...init, headers });
  } catch (err: any) {
    throw new ApiError(`Cannot reach backend at ${url}`, { network: true, detail: redactSecrets(err) });
  }
  if (resp.status === 204) return undefined as T;
  const text = await resp.text();
  let data: any = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch { /* non-JSON body (proxy html error page) */ }
  if (!resp.ok) {
    throw new ApiError(`API ${resp.status} on ${path}`, {
      status: resp.status,
      detail: redactSecrets(data),
    });
  }
  return data as T;
}

export async function login(cfg: AppConfig, username: string, password: string): Promise<string> {
  const data = await request<any>(cfg, null, cfg.authPath, {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  const token = data?.token;
  if (!token) throw new ApiError("Login succeeded but no token in response", { detail: redactSecrets(data) });
  return String(token);
}

export async function fetchSchema(cfg: AppConfig, token: string | null): Promise<AdminSchema> {
  const doc = await request<any>(cfg, token, cfg.schemaPath);
  return normalizeOpenAPI(doc);
}

/* ---- runtime branding (backends running the admineverywhere plugin) ---- */

export interface BrandingResponse {
  brand: Brand;
  rev: number;
}

/** Resolve an API-relative path (e.g. "/admineverywhere/branding/asset/logo.png")
 *  against the configured API base. Absolute/data URLs pass through. */
export function resolveApiUrl(cfg: AppConfig, path: string | undefined): string | undefined {
  if (!path) return undefined;
  if (/^(https?:|data:|blob:)/i.test(path)) return path;
  return cfg.apiUrl.replace(/\/+$/, "") + path;
}

/** Public brand read; null = backend has no admineverywhere branding configured
 *  (or is unreachable) — caller keeps the bundled static brand. */
export async function fetchBranding(cfg: AppConfig): Promise<BrandingResponse | null> {
  try {
    const resp = await fetch(resolveApiUrl(cfg, "/admineverywhere/branding/")!, {
      headers: { Accept: "application/json" },
    });
    if (!resp.ok) return null;
    return (await resp.json()) as BrandingResponse;
  } catch {
    return null;
  }
}

/** Replace the server-side brand (staff token required). Throws ApiError
 *  with a 400 `detail` = {errors: [...]} on validation problems. */
export async function saveBranding(
  cfg: AppConfig, token: string | null, brand: Brand,
): Promise<BrandingResponse> {
  return request<BrandingResponse>(cfg, token, "/admineverywhere/branding/", {
    method: "PUT",
    body: JSON.stringify(brand),
  });
}

function toPage<T = RecordRow>(data: any): Page<T> {
  if (Array.isArray(data)) return { count: data.length, results: data, next: null, previous: null };
  return {
    count: data?.count ?? data?.results?.length ?? 0,
    results: data?.results ?? [],
    next: data?.next ?? null,
    previous: data?.previous ?? null,
  };
}

export async function listRecords(
  cfg: AppConfig, token: string | null, model: ModelSpec,
  opts: { page?: number; search?: string; pageSize?: number } = {},
): Promise<Page<RecordRow>> {
  const params = new URLSearchParams();
  if (opts.page) params.set("page", String(opts.page));
  if (opts.search) params.set("search", opts.search);
  if (opts.pageSize) params.set("page_size", String(opts.pageSize));
  const qs = params.toString();
  const data = await request<any>(cfg, token, `${model.listPath}${qs ? `?${qs}` : ""}`);
  return toPage(data);
}

/** Page through the whole collection (FK dropdown options). Capped hard. */
export async function fetchAllRecords(
  cfg: AppConfig, token: string | null, model: ModelSpec, cap = 300,
): Promise<RecordRow[]> {
  const rows: RecordRow[] = [];
  let page = 1;
  while (rows.length < cap) {
    const p = await listRecords(cfg, token, model, { page, pageSize: 100 });
    rows.push(...p.results);
    if (!p.next) break;
    page++;
  }
  return rows.slice(0, cap);
}

export async function retrieveRecord(
  cfg: AppConfig, token: string | null, model: ModelSpec, id: string | number,
): Promise<RecordRow> {
  return request<RecordRow>(cfg, token, model.detailPath.replace("{id}", encodeURIComponent(String(id))));
}

export async function createRecord(
  cfg: AppConfig, token: string | null, model: ModelSpec, data: Record<string, any>,
): Promise<RecordRow> {
  return request<RecordRow>(cfg, token, model.listPath, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateRecord(
  cfg: AppConfig, token: string | null, model: ModelSpec, id: string | number,
  data: Record<string, any>,
): Promise<RecordRow> {
  return request<RecordRow>(cfg, token, model.detailPath.replace("{id}", encodeURIComponent(String(id))), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/** Partial update — sends exactly the keys given (a kanban drop on a free enum
 *  must touch one field and nothing else, which a PUT of the whole row cannot
 *  promise). DRF answers with the full updated record. */
export async function patchRecord(
  cfg: AppConfig, token: string | null, model: ModelSpec, id: string | number,
  data: Record<string, any>,
): Promise<RecordRow> {
  return request<RecordRow>(cfg, token, model.detailPath.replace("{id}", encodeURIComponent(String(id))), {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteRecord(
  cfg: AppConfig, token: string | null, model: ModelSpec, id: string | number,
): Promise<void> {
  await request<void>(cfg, token, model.detailPath.replace("{id}", encodeURIComponent(String(id))), {
    method: "DELETE",
  });
}

/** Field-level error extraction from DRF 400 responses: {field: ["msg", ...]} */
export function fieldErrors(detail: any): Record<string, string> {
  const out: Record<string, string> = {};
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    for (const [k, v] of Object.entries(detail)) {
      if (Array.isArray(v)) out[k] = v.map(String).join(" ");
      else if (typeof v === "string") out[k] = v;
      else if (typeof v === "object") out[k] = JSON.stringify(v);
    }
  } else if (typeof detail === "string") {
    out._ = detail;
  }
  return out;
}


/** Build the URL of a DRF router `@action` from a schema-discovered list path.
 *  detail=True  -> <listPath><id>/<slug>/
 *  detail=False -> <listPath><slug>/
 *  Paths come from the OpenAPI document (model.listPath), never from string
 *  guesses at the url segment — apiUrl is only ever the base origin. */
export function actionPath(model: ModelSpec, slug: string, recordId?: string | number): string {
  const base = model.listPath.replace(/\/+$/, "") + "/";
  if (recordId === undefined || recordId === null || recordId === "") return `${base}${slug}/`;
  return `${base}${encodeURIComponent(String(recordId))}/${slug}/`;
}

/** POST <transitionPath> — perform a lifecycle transition (FR-R001).
 *  Returns the updated record on 200; on 409 throws ApiError whose
 *  detail carries the guard `reason` (R-001 error shape). The URL is the
 *  schema-discovered POST …/transition/, never a re-guess of it: a backend that
 *  does not document the action must not be offered in the UI either
 *  (statusTransitions.lifecycleProblem). */
export async function transitionRecord(
  cfg: AppConfig,
  token: string | null,
  model: ModelSpec,
  recordId: string | number,
  targetStatus: string,
): Promise<RecordRow> {
  if (!model.transitionPath) {
    throw new ApiError(`"${model.id}" documents no lifecycle transition endpoint`);
  }
  return request<RecordRow>(
    cfg,
    token,
    model.transitionPath.replace("{id}", encodeURIComponent(String(recordId))),
    { method: "POST", body: JSON.stringify({ transition: targetStatus }) },
  );
}

/** GET <historyPath> — lifecycle history (append-only, oldest first). */
export async function fetchHistory(
  cfg: AppConfig,
  token: string | null,
  model: ModelSpec,
  recordId: string | number,
): Promise<Array<{ id: number; from_status: string; to_status: string; actor: string | null; created_at: string }>> {
  if (!model.historyPath) {
    throw new ApiError(`"${model.id}" documents no lifecycle history endpoint`);
  }
  const data = await request<any>(
    cfg,
    token,
    model.historyPath.replace("{id}", encodeURIComponent(String(recordId))),
  );
  return Array.isArray(data) ? data : data?.results ?? [];
}

/** POST a record-scope custom action (FR-R003): <listPath><id>/<slug>/.
 *  Reference shape — flag: body {reason} -> 201 with one audit entry;
 *  guard failures -> 400 with {reason}. The response may be a single entry
 *  or a list; both normalize to an array. */
export async function callRecordAction(
  cfg: AppConfig,
  token: string | null,
  model: ModelSpec,
  recordId: string | number,
  slug: string,
  body: Record<string, any> = {},
): Promise<AuditEntry[]> {
  const data = await request<any>(cfg, token, actionPath(model, slug, recordId), {
    method: "POST",
    body: JSON.stringify(body),
  });
  return toEntries(data);
}

/** POST a bulk-scope custom action (FR-R003): <listPath><slug>/.
 *  Reference shape — bulk_flag: body {ids, reason} -> 201 with one audit
 *  entry per targeted record; unknown ids -> 400 {reason}, nothing written. */
export async function callBulkAction(
  cfg: AppConfig,
  token: string | null,
  model: ModelSpec,
  slug: string,
  body: Record<string, any> = {},
): Promise<AuditEntry[]> {
  const data = await request<any>(cfg, token, actionPath(model, slug), {
    method: "POST",
    body: JSON.stringify(body),
  });
  return toEntries(data);
}

function toEntries(data: any): AuditEntry[] {
  if (Array.isArray(data)) return data as AuditEntry[];
  if (data && typeof data === "object") return [data as AuditEntry];
  return [];
}

/** GET <discovered audit listPath> — the append-only log, newest first (the
 *  R-003 ordering ruling: triage wants the latest event on top). Filters back
 *  the record sub-view and the R-007 activity screen; object_type is the
 *  model's singular name, object_id the record pk.
 *
 *  `opts.path` is the schema-discovered listPath (FR-R007 law, same evidence
 *  rule as transitionRecord/fetchHistory): a backend whose document carries
 *  no audit model has no log to read, so this throws rather than guessing
 *  "/api/audit/" — a segment some other app may own. */
export async function fetchAudit(
  cfg: AppConfig,
  token: string | null,
  opts: { objectType?: string; objectId?: string | number; page?: number; path?: string } = {},
): Promise<Page<AuditEntry>> {
  if (!opts.path) {
    throw new ApiError("the API documents no audit log endpoint — refusing to guess its path");
  }
  const params = new URLSearchParams();
  if (opts.objectType) params.set("object_type", opts.objectType);
  if (opts.objectId !== undefined && opts.objectId !== null && opts.objectId !== "") {
    params.set("object_id", String(opts.objectId));
  }
  if (opts.page) params.set("page", String(opts.page));
  const qs = params.toString();
  return toPage<AuditEntry>(await request<any>(cfg, token, `${opts.path}${qs ? `?${qs}` : ""}`));
}

/** GET the schema-discovered role-claims path (FR-R007 phase a). Answers
 *  the parsed claims or null — a backend without the endpoint, an
 *  unauthenticated refusal, any failure is "no claims", which the client
 *  reads as "apply no filtering". Never throws: claims are UX, the server
 *  stays the gate, and a broken read must not break the shell. */
export async function fetchMe(cfg: AppConfig, token: string | null, mePath: string): Promise<RoleClaims | null> {
  if (!token) return null;
  try {
    return parseClaims(await request<any>(cfg, token, mePath));
  } catch {
    return null;
  }
}

/** GET a schema-discovered line-level CSV export (FR-R005 layer 2 — the
 *  `exportPath` the normalizer found, never a guessed path). The body is text
 *  not JSON so it cannot share request(), but auth, error shape and base-URL
 *  rules are identical: a 401 still logs the user out, a 500 still surfaces. */
export async function fetchCsv(
  cfg: AppConfig,
  token: string | null,
  path: string,
  fallbackFilename: string,
): Promise<{ text: string; filename: string }> {
  const url = baseUrl(cfg);
  let resp: Response;
  try {
    resp = await fetch(url + path, {
      headers: { Accept: "text/csv, */*;q=0.8", ...(token ? { Authorization: `Token ${token}` } : {}) },
    });
  } catch (err: any) {
    throw new ApiError(`Cannot reach backend at ${url}`, { network: true, detail: redactSecrets(err) });
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    let detail: any = text;
    try { detail = text ? JSON.parse(text) : null; } catch { /* proxy html error page */ }
    throw new ApiError(`API ${resp.status} on ${path}`, { status: resp.status, detail: redactSecrets(detail) });
  }
  const disposition = resp.headers.get("Content-Disposition") ?? "";
  const quoted = /filename=\s*"([^"]+)"/i.exec(disposition)?.[1];
  const bare = /filename=\s*([^;"\s]+)/i.exec(disposition)?.[1];
  // Whatever the server named it goes through the same slugifier as a
  // client-generated name: a header is data, not a save path.
  return {
    text: await resp.text(),
    filename: exportFileName((quoted ?? bare ?? "").trim() || fallbackFilename),
  };
}