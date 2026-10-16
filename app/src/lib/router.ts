/** Hash router — bulletproof in web mode, Tauri, and packaged file builds.

Routes:
  #/login
  #/                dashboard
  #/m/<modelId>     model table
  #/m/<modelId>/<recordId>  open record for editing
*/
import { writable } from "svelte/store";

export type Route =
  | { name: "login" }
  | { name: "dashboard" }
  | { name: "model"; id: string; recordId?: string };

export function parseHash(hash: string = location.hash): Route {
  const h = (hash || "#/").replace(/^#/, "");
  const parts = h.split("/").filter(Boolean);
  if (parts[0] === "login") return { name: "login" };
  if (parts[0] === "m" && parts[1]) {
    return { name: "model", id: decodeURIComponent(parts[1]), recordId: parts[2] };
  }
  return { name: "dashboard" };
}

export const route = writable<Route>(parseHash());

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
