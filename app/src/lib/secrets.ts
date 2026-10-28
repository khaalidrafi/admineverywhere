/** Secrets: OS keychain under Tauri, localStorage in plain browser mode.
 *
 *  In the packaged Tauri app the key goes to the OS credential store
 *  (Windows Credential Manager / macOS Keychain / Secret Service) via the
 *  keyring Rust commands in src-tauri/src/lib.rs. When running as a plain
 *  web app (vite dev / browser), we degrade to localStorage and say so.
 */
export const SERVICE = "admineverywhere";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** true = secrets currently live in browser localStorage (dev mode) */
export function isWebStorage(): boolean {
  return !isTauri();
}

let webWarned = false;
function warnWebFallback() {
  if (!webWarned) {
    console.warn(
      "SECURITY WARNING: Tauri keyring not available. Falling back to plain-text localStorage for secrets. " +
      "Do not use sensitive keys in web mode!"
    );
    webWarned = true;
  }
}

export async function saveSecret(key: string, value: string): Promise<void> {
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("save_secret", { service: SERVICE, key, value });
    return;
  }
  warnWebFallback();
  localStorage.setItem(`dad.secret.${key}`, value);
}

export async function loadSecret(key: string): Promise<string | null> {
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    try {
      return await invoke<string | null>("load_secret", { service: SERVICE, key });
    } catch {
      return null; // missing entry or keychain unavailable
    }
  }
  warnWebFallback();
  return localStorage.getItem(`dad.secret.${key}`);
}

export async function deleteSecret(key: string): Promise<void> {
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    try {
      await invoke("delete_secret", { service: SERVICE, key });
    } catch { /* already gone */ }
    return;
  }
  warnWebFallback();
  localStorage.removeItem(`dad.secret.${key}`);
}
