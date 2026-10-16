/** api.ts — thin DRF client. Token auth, pagination, search.

Every failure is normalized to ApiError so the UI can react:
- network:true  -> backend unreachable (banner)
- status:401     -> session expired (logout)
- status:400     -> validation errors (field-level display)
*/
import { normalizeOpenAPI } from "./openapi";
import type { AdminSchema, AppConfig, ModelSpec, Page, RecordRow } from "./types";

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

async function request<T>(cfg: AppConfig, token: string | null, path: string,
                          init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Token ${token}` } : {}),
  };
  
  // Strip credentials from URL if present (secrets never in URLs)
  let url = cfg.apiUrl.replace(/\/+$/, "");
  try {
    const u = new URL(url);
    if (u.username || u.password) {
      u.username = "";
      u.password = "";
      url = u.toString().replace(/\/$/, "");
    }
  } catch {}
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
): Promise<Page> {
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
