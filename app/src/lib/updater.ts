/** updater.ts — self-updater for the admin apps (owner order 2026-11-08).
 *
 *  Source of truth: GitHub Releases of the app's repository. The shipping
 *  repos are PRIVATE, so reads go through GitHub auth, in three modes that
 *  degrade gracefully:
 *
 *    1. stored token   — a fine-grained PAT with `Contents: read` for the
 *       release repo, saved via the same keyring path as the AI key
 *       (`saveSecret("updates.token", …)`). Works today, no setup ceremony.
 *    2. OAuth device flow — the owner's OAuth app client id arrives through
 *       AppConfig (`githubClientId`, inlined by build_admin like apiUrl).
 *       The user opens github.com/login/device, types the code, the app
 *       polls until GitHub grants a token; it is held in memory only and
 *       used solely for release reads of this one repo.
 *    3. anonymous      — works when the release repo is public.
 *
 *  The token NEVER leaves this module except to GitHub; it is not logged,
 *  not stored in localStorage, not echoed in errors.
 *
 *  Applying an update: the desktop bundles are installers — the module
 *  downloads the newest installer asset and hands it to the OS via the
 *  anchor-download path (browser + Tauri webview). Production CSP must
 *  allow the release host: build_admin --csp-connect-origin (added in the
 *  same change) appends validated origins at build time.
 */

export const GITHUB_API = "https://api.github.com";
export const DEVICE_CODE_ENDPOINT = "https://github.com/login/device/code";
export const DEVICE_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token";

export interface ReleaseInfo {
  tagName: string;
  name: string;
  notes: string;
  htmlUrl: string;
  /** First installer-looking asset (exe/msi/dmg/apk/AppImage/deb). */
  downloadUrl: string | null;
  downloadName: string | null;
  publishedAt: string | null;
}

export interface UpdateCheck {
  upToDate: boolean;
  current: string;
  latest: string | null;
  release: ReleaseInfo | null;
  /** How the release was read (for the UI to explain failures honestly). */
  via: "token" | "oauth" | "anonymous" | "none";
  error?: string;
}

/* ---- semver-ish comparison (v-prefix tolerant, prerelease-aware) ---- */

export function parseVersion(v: string): number[] {
  const core = (v ?? "").trim().replace(/^v/i, "").split("-")[0];
  const parts = core.split(".").map((p) => parseInt(p, 10));
  return parts.map((n) => (Number.isFinite(n) ? n : 0));
}

export function isNewer(latest: string, current: string): boolean {
  const a = parseVersion(latest);
  const b = parseVersion(current);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (x !== y) return x > y;
  }
  // equal core: a plain release supersedes its own prerelease (0.1.4 > 0.1.4-rc1)
  const latPre = /-/.test((latest ?? "").trim());
  const curPre = /-/.test((current ?? "").trim());
  return curPre && !latPre;
}

/* ---- release reading ---- */

const INSTALLER_RE = /\.(exe|msi|dmg|apk|appimage|deb|rpm)$/i;

export function pickInstallerAsset(assets: Array<{ name?: string; browser_download_url?: string }>): {
  url: string;
  name: string;
} | null {
  for (const a of assets ?? []) {
    if (a?.name && INSTALLER_RE.test(a.name) && a.browser_download_url) {
      return { url: a.browser_download_url, name: a.name };
    }
  }
  return null;
}

export function releaseFromApi(data: any): ReleaseInfo | null {
  if (!data || typeof data !== "object" || !data.tag_name) return null;
  const asset = pickInstallerAsset(data.assets ?? []);
  return {
    tagName: String(data.tag_name),
    name: String(data.name ?? data.tag_name),
    notes: String(data.body ?? ""),
    htmlUrl: String(data.html_url ?? ""),
    downloadUrl: asset?.url ?? null,
    downloadName: asset?.name ?? null,
    publishedAt: data.published_at ? String(data.published_at) : null,
  };
}

async function ghFetch(url: string, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(url, { headers });
}

/** Read the newest release of `repo` ("owner/name"). Tries the stored token
 *  first, then an OAuth token if given, then anonymous. */
export async function fetchLatestRelease(
  repo: string,
  token: string | null,
): Promise<{ release: ReleaseInfo | null; via: UpdateCheck["via"]; error?: string }> {
  const url = `${GITHUB_API}/repos/${repo}/releases/latest`;
  const attempts: Array<{ via: UpdateCheck["via"]; token: string | null }> = [
    { via: "token", token },
    { via: "anonymous", token: null },
  ];
  let lastError = "";
  for (const attempt of attempts) {
    if (attempt.via === "token" && !attempt.token) continue;
    try {
      const resp = await ghFetch(url, attempt.token);
      if (resp.ok) {
        return { release: releaseFromApi(await resp.json()), via: attempt.via };
      }
      if (resp.status === 404) {
        // 404 on a private repo without valid auth is GitHub's standard
        // answer; with the NEXT mode it may still succeed. Anonymous 404
        // on the last attempt means: repo invisible.
        lastError = "repository not visible without authorization (HTTP 404)";
        continue;
      }
      if (resp.status === 401) {
        lastError = "stored token rejected (HTTP 401) — renew it or use the device flow";
        continue;
      }
      lastError = `GitHub answered HTTP ${resp.status}`;
    } catch (err: any) {
      lastError = `network error: ${String(err?.message ?? err)}`;
    }
  }
  return { release: null, via: "none", error: lastError };
}

export async function checkForUpdate(
  repo: string,
  currentVersion: string,
  token: string | null,
): Promise<UpdateCheck> {
  const { release, via, error } = await fetchLatestRelease(repo, token);
  if (!release) return { upToDate: true, current: currentVersion, latest: null, release: null, via, error };
  const newer = isNewer(release.tagName, currentVersion);
  return { upToDate: !newer, current: currentVersion, latest: release.tagName, release, via };
}

/* ---- OAuth device flow (mode 2) ---- */

export interface DeviceFlowStart {
  deviceCode: string;
  userCode: string;
  verifyUri: string;
  intervalSeconds: number;
  expiresIn: number;
}

/** POST github.com/login/device/code — needs the app's public client id. */
export async function deviceFlowStart(clientId: string): Promise<DeviceFlowStart> {
  const resp = await fetch(DEVICE_CODE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ client_id: clientId, scope: "repo:read" }),
  });
  if (!resp.ok) throw new Error(`GitHub device flow start failed (HTTP ${resp.status})`);
  const data = await resp.json();
  if (data.error) throw new Error(`GitHub device flow: ${data.error_description ?? data.error}`);
  return {
    deviceCode: String(data.device_code),
    userCode: String(data.user_code),
    verifyUri: String(data.verification_uri ?? "https://github.com/login/device"),
    intervalSeconds: Number(data.interval ?? 5),
    expiresIn: Number(data.expires_in ?? 900),
  };
}

export type DeviceFlowPoll =
  | { status: "pending" }
  | { status: "slow_down"; intervalSeconds: number }
  | { status: "granted"; token: string }
  | { status: "denied"; reason: string };

/** One poll of the device-flow token endpoint. The CALLER owns the interval
 *  loop (so a component can cancel it); this answers exactly one probe. */
export async function deviceFlowPollOnce(
  clientId: string,
  deviceCode: string,
): Promise<DeviceFlowPoll> {
  const resp = await fetch(DEVICE_TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      client_id: clientId,
      device_code: deviceCode,
      grant_type: "urn:ietf:params:oauth:grant-type:device_code",
    }),
  });
  const data = await resp.json().catch(() => null);
  if (!data) return { status: "pending" };
  if (data.access_token) return { status: "granted", token: String(data.access_token) };
  const err = String(data.error ?? "");
  if (err === "authorization_pending") return { status: "pending" };
  if (err === "slow_down") return { status: "slow_down", intervalSeconds: Number(data.interval ?? 5) };
  if (err === "expired_token") return { status: "denied", reason: "the device code expired — start again" };
  if (err === "access_denied") return { status: "denied", reason: "authorization was denied on GitHub" };
  return { status: "denied", reason: data.error_description ?? err ?? "unknown device-flow error" };
}

/** Trigger the OS/browser download of the release asset. */
export async function downloadAsset(url: string, filename: string): Promise<void> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`download failed (HTTP ${resp.status})`);
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

/* ---- durable release-token storage (mode 1) ----
 *  Rides the SAME secret path as the AI provider key: OS keychain in the
 *  packaged app, localStorage in browser mode (secrets.ts decides). */

const TOKEN_KEY = "updates.token";

export async function loadStoredToken(): Promise<string | null> {
  try {
    const { loadSecret } = await import("./secrets");
    return (await loadSecret(TOKEN_KEY)) ?? null;
  } catch {
    return null;
  }
}

export async function saveStoredToken(token: string): Promise<void> {
  const { saveSecret, deleteSecret } = await import("./secrets");
  if (token) await saveSecret(TOKEN_KEY, token);
  else await deleteSecret(TOKEN_KEY);
}
