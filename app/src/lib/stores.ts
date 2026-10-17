/** Global stores — svelte/store writables (battle-tested cross-module
 *  reactivity; immune to rune-export compiler changes).
 *
 *  One store per concern: app (config/brand/auth/schema/connection),
 *  ai (chat provider settings), toasts. Components read via $store
 *  auto-subscription; logic reads via get(store).
 */
import { get, writable } from "svelte/store";
import {
  ApiError,
  fetchBranding as apiFetchBranding,
  fetchSchema as apiFetchSchema,
  login as apiLogin,
  resolveApiUrl,
  saveBranding as apiSaveBranding,
} from "./api";
import { injectBrandCss } from "./branding";
import { loadSecret, saveSecret } from "./secrets";
import type { AdminSchema, AppConfig, Brand } from "./types";

export interface AppState {
  booted: boolean;
  config: AppConfig | null;
  brand: Brand;
  token: string;
  username: string;
  apiUrlOverride: string;
  schema: AdminSchema | null;
  schemaLoading: boolean;
  backendDown: boolean;
}

const DEFAULT_BRAND: Brand = {
  appName: "Admincraft",
  tagline: "Django-powered admin",
  colors: {},
  radius: "0.75rem",
  font: "Inter",
};

export const app = writable<AppState>({
  booted: false,
  config: null,
  brand: DEFAULT_BRAND,
  token: typeof localStorage !== "undefined" ? localStorage.getItem("dad.token") ?? "" : "",
  username: typeof localStorage !== "undefined" ? localStorage.getItem("dad.username") ?? "" : "",
  apiUrlOverride:
    typeof localStorage !== "undefined" ? localStorage.getItem("dad.apiUrl") ?? "" : "",
  schema: null,
  schemaLoading: false,
  backendDown: false,
});

export function effectiveConfig(): AppConfig {
  const a = get(app);
  const base = a.config ?? { apiUrl: "", authPath: "/api/auth/token/", schemaPath: "/api/schema/" };
  return { ...base, apiUrl: a.apiUrlOverride || base.apiUrl };
}

async function fetchJson(url: string): Promise<any | null> {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

export async function initApp(): Promise<void> {
  const [config, brand] = await Promise.all([fetchJson("config.json"), fetchJson("brand.json")]);
  app.update((a) => ({
    ...a,
    config: config ?? null,
    brand: brand?.appName ? brand : a.brand,
    booted: true,
  }));
  applyBrand(get(app).brand);
  // Backend branding (when the API runs the admincraft plugin): the
  // server brand wins over the bundled static one — this is the
  // rebrand-from-inside-the-app path. A backend without the plugin
  // (plain DRF) silently keeps the static brand; network failures are
  // already surfaced by the schema flow, not here.
  const cfg = effectiveConfig();
  if (cfg.apiUrl) {
    const data = await apiFetchBranding(cfg);
    if (data?.brand?.appName) {
      applyBrand(brandWithResolvedAssets(cfg, data.brand));
    }
  }
}

function brandWithResolvedAssets(cfg: AppConfig, brand: Brand): Brand {
  return {
    ...brand,
    logo: resolveApiUrl(cfg, brand.logo),
    favicon: resolveApiUrl(cfg, brand.favicon),
  };
}

/** Apply a brand everywhere it lives: store (UI text/logos), tab title,
 *  favicon, runtime CSS variables, and the native window title in Tauri.
 *  Launcher/dock names are baked at build time (see the branding skill). */
export function applyBrand(brand: Brand): void {
  app.update((a) => ({ ...a, brand }));
  document.title = brand.appName;
  const favicon = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (favicon && brand.favicon) favicon.href = brand.favicon;
  injectBrandCss(brand);
  void setNativeWindowTitle(brand.appName);
}

async function setNativeWindowTitle(title: string): Promise<void> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setTitle(title);
  } catch {
    // non-fatal: window title falls back to the build-time productName
  }
}

/** Persist a new brand through the backend plugin (staff token), then
 *  apply it live. Throws ApiError (400 detail = {errors: [...]}) upward —
 *  the editor renders the field problems. */
export async function saveBrand(brand: Brand): Promise<Brand> {
  const cfg = effectiveConfig();
  const data = await apiSaveBranding(cfg, get(app).token || null, brand);
  const resolved = brandWithResolvedAssets(cfg, data.brand);
  applyBrand(resolved);
  return resolved;
}

export async function login(username: string, password: string): Promise<void> {
  const token = await apiLogin(effectiveConfig(), username, password);
  app.update((a) => ({ ...a, token, username, backendDown: false }));
  localStorage.setItem("dad.token", token);
  localStorage.setItem("dad.username", username);
}

export function logout(): void {
  app.update((a) => ({ ...a, token: "", username: "", schema: null }));
  localStorage.removeItem("dad.token");
  localStorage.removeItem("dad.username");
}

export async function loadSchema(): Promise<void> {
  const a0 = get(app);
  if (a0.schemaLoading) return;
  app.update((a) => ({ ...a, schemaLoading: true }));
  try {
    const schema = await apiFetchSchema(effectiveConfig(), get(app).token || null);
    app.update((a) => ({ ...a, schema, backendDown: false }));
  } finally {
    app.update((a) => ({ ...a, schemaLoading: false }));
  }
}

/** Central error policy: network -> banner, 401 -> logout, else toast. */
export function handleApiError(err: unknown): void {
  if (err instanceof ApiError) {
    if (err.network) {
      app.update((a) => ({ ...a, backendDown: true }));
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
export const toasts = writable<Toast[]>([]);

export function toast(kind: Toast["kind"], text: string): void {
  const id = ++toastId;
  toasts.update((list) => [...list, { id, kind, text }]);
  setTimeout(() => {
    toasts.update((list) => list.filter((t) => t.id !== id));
  }, 4000);
}

/* ---- AI chat settings (OpenAI-compatible provider) ---- */

export interface AiState {
  baseUrl: string;
  apiKey: string;
  model: string;
}

export const ai = writable<AiState>({ baseUrl: "", apiKey: "", model: "" });

export async function loadAiSettings(): Promise<void> {
  ai.set({
    baseUrl: localStorage.getItem("dad.ai.baseUrl") ?? "",
    model: localStorage.getItem("dad.ai.model") ?? "",
    apiKey: (await loadSecret("ai.apiKey")) ?? "",
  });
}

export async function saveAiSettings(baseUrl: string, apiKey: string, model: string): Promise<void> {
  ai.set({ baseUrl: baseUrl.trim(), apiKey: apiKey.trim(), model: model.trim() });
  localStorage.setItem("dad.ai.baseUrl", baseUrl.trim());
  localStorage.setItem("dad.ai.model", model.trim());
  if (apiKey.trim()) {
    await saveSecret("ai.apiKey", apiKey.trim());
  }
}
