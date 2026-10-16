/** Global stores (Svelte 5 runes in .svelte.ts = shared reactive state).

One store object per concern: app (config/brand/auth/schema/connection),
ai (chat settings), toasts. Everything downstream imports from here.
*/
import {
  fetchSchema as apiFetchSchema,
  login as apiLogin,
  ApiError,
} from "./api";
import { loadSecret, saveSecret } from "./secrets";
import type { AdminSchema, AppConfig, Brand } from "./types";

const DEFAULT_BRAND: Brand = {
  appName: "AI Dashboard",
  tagline: "Django-powered admin",
  colors: {},
  radius: "0.75rem",
  font: "Inter",
};

async function fetchJson(url: string): Promise<any | null> {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

export const app = $state({
  booted: false,
  config: null as AppConfig | null,
  brand: DEFAULT_BRAND,
  token: typeof localStorage !== "undefined" ? localStorage.getItem("dad.token") ?? "" : "",
  username: typeof localStorage !== "undefined" ? localStorage.getItem("dad.username") ?? "" : "",
  apiUrlOverride:
    typeof localStorage !== "undefined" ? localStorage.getItem("dad.apiUrl") ?? "" : "",
  schema: null as AdminSchema | null,
  schemaLoading: false,
  backendDown: false,
});

export function effectiveConfig(): AppConfig {
  const base = app.config ?? { apiUrl: "", authPath: "/api/auth/token/", schemaPath: "/api/schema/" };
  return { ...base, apiUrl: app.apiUrlOverride || base.apiUrl };
}

export async function initApp(): Promise<void> {
  const [config, brand] = await Promise.all([
    fetchJson("config.json"),
    fetchJson("brand.json"),
  ]);
  app.config = config ?? null;
  if (brand?.appName) app.brand = brand;
  document.title = app.brand.appName;
  const favicon = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (favicon && app.brand.favicon) favicon.href = app.brand.favicon;
  app.booted = true;
}

export async function login(username: string, password: string): Promise<void> {
  const token = await apiLogin(effectiveConfig(), username, password);
  app.token = token;
  app.username = username;
  localStorage.setItem("dad.token", token);
  localStorage.setItem("dad.username", username);
  app.backendDown = false;
}

export function logout(): void {
  app.token = "";
  app.username = "";
  app.schema = null;
  localStorage.removeItem("dad.token");
  localStorage.removeItem("dad.username");
}

export async function loadSchema(): Promise<void> {
  if (app.schemaLoading) return;
  app.schemaLoading = true;
  try {
    app.schema = await apiFetchSchema(effectiveConfig(), app.token || null);
    app.backendDown = false;
  } finally {
    app.schemaLoading = false;
  }
}

/** Central error policy: network -> banner, 401 -> logout, else toast. */
export function handleApiError(err: unknown): void {
  if (err instanceof ApiError) {
    if (err.network) {
      app.backendDown = true;
    } else if (err.status === 401) {
      logout();
      toast("error", "Session expired — please sign in again");
    } else {
      const detail = typeof err.detail === "string" ? `: ${err.detail}` : "";
      toast("error", `${err.message}${detail}`);
    }
  } else {
    toast("error", String((err as Error)?.message ?? err));
  }
}

export interface Toast {
  id: number;
  kind: "success" | "error" | "info";
  text: string;
}

let toastId = 0;
export const toasts = $state<Toast[]>([]);

export function toast(kind: Toast["kind"], text: string): void {
  const id = ++toastId;
  toasts.push({ id, kind, text });
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id);
    if (i >= 0) toasts.splice(i, 1);
  }, 4000);
}

/* ---- AI chat settings (OpenAI-compatible provider) ---- */

export const ai = $state({
  baseUrl: "",
  apiKey: "",
  model: "",
  ready: false,
});

export async function loadAiSettings(): Promise<void> {
  ai.baseUrl = localStorage.getItem("dad.ai.baseUrl") ?? "";
  ai.model = localStorage.getItem("dad.ai.model") ?? "";
  ai.apiKey = (await loadSecret("ai.apiKey")) ?? "";
  ai.ready = true;
}

export async function saveAiSettings(baseUrl: string, apiKey: string, model: string): Promise<void> {
  ai.baseUrl = baseUrl.trim();
  ai.apiKey = apiKey.trim();
  ai.model = model.trim();
  localStorage.setItem("dad.ai.baseUrl", ai.baseUrl);
  localStorage.setItem("dad.ai.model", ai.model);
  if (ai.apiKey) {
    await saveSecret("ai.apiKey", ai.apiKey);
  }
}
