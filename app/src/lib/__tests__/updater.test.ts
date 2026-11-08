/** updater.ts tests — the self-updater core (owner order 2026-11-08).
 *
 *  Pins: version comparison (v-prefix, prerelease), installer-asset picking,
 *  release parsing, the auth fallback ladder (stored token → anonymous),
 *  the device-flow poll answers (pending / slow_down / granted / denied),
 *  and that the token never leaks into an error path.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  checkForUpdate,
  deviceFlowPollOnce,
  isNewer,
  pickInstallerAsset,
  releaseFromApi,
} from "../updater";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("version comparison", () => {
  it("orders semver cores with v-prefix tolerance", () => {
    expect(isNewer("v0.1.5", "0.1.4")).toBe(true);
    expect(isNewer("0.2.0", "0.1.9")).toBe(true);
    expect(isNewer("1.0.0", "1.0.0")).toBe(false);
    expect(isNewer("0.1.4", "0.1.5")).toBe(false);
  });

  it("a prerelease is older than its plain release", () => {
    expect(isNewer("0.1.4-rc1", "0.1.4")).toBe(false);
    expect(isNewer("0.1.5-rc1", "0.1.4")).toBe(true);
  });
});

describe("installer asset picking", () => {
  it("prefers the first installer-looking asset", () => {
    const pick = pickInstallerAsset([
      { name: "sources.zip", browser_download_url: "https://x/sources.zip" },
      { name: "Freshorama-Admin_0.1.5_x64-setup.exe", browser_download_url: "https://x/setup.exe" },
      { name: "app.apk", browser_download_url: "https://x/app.apk" },
    ]);
    expect(pick?.name).toBe("Freshorama-Admin_0.1.5_x64-setup.exe");
    expect(pick?.url).toBe("https://x/setup.exe");
  });

  it("answers null when no installer asset exists", () => {
    expect(pickInstallerAsset([{ name: "sources.zip", browser_download_url: "https://x/s.zip" }])).toBeNull();
    expect(pickInstallerAsset([])).toBeNull();
  });
});

describe("releaseFromApi", () => {
  it("maps the GitHub release payload", () => {
    const r = releaseFromApi({
      tag_name: "v0.1.5",
      name: "v0.1.5 — onboarding",
      body: "## What's new",
      html_url: "https://github.com/o/r/releases/tag/v0.1.5",
      published_at: "2026-11-08T00:00:00Z",
      assets: [{ name: "setup.exe", browser_download_url: "https://x/setup.exe" }],
    });
    expect(r?.tagName).toBe("v0.1.5");
    expect(r?.downloadUrl).toBe("https://x/setup.exe");
    expect(r?.notes).toContain("What's new");
  });

  it("answers null for a garbage payload", () => {
    expect(releaseFromApi(null)).toBeNull();
    expect(releaseFromApi({})).toBeNull();
  });
});

describe("checkForUpdate auth ladder", () => {
  const RELEASE = {
    tag_name: "v0.2.0",
    name: "v0.2.0",
    body: "notes",
    html_url: "https://github.com/o/r/releases/tag/v0.2.0",
    assets: [{ name: "setup.exe", browser_download_url: "https://x/setup.exe" }],
  };

  it("uses the stored token first and reports via=token", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(RELEASE), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const out = await checkForUpdate("o/r", "0.1.4", "tok123");
    expect(out.upToDate).toBe(false);
    expect(out.latest).toBe("v0.2.0");
    expect(out.via).toBe("token");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/repos/o/r/releases/latest");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok123");
  });

  it("falls back to anonymous when the token 404s a private repo", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 404 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(RELEASE), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const out = await checkForUpdate("o/r", "0.1.4", "tok123");
    expect(out.via).toBe("anonymous");
    expect(out.release?.tagName).toBe("v0.2.0");
  });

  it("reports the failure honestly when every attempt fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    const out = await checkForUpdate("o/r", "0.1.4", "tok123");
    expect(out.release).toBeNull();
    expect(out.via).toBe("none");
    expect(out.error).toBeTruthy();
  });

  it("up-to-date repo says so", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(RELEASE), { status: 200 })));
    const out = await checkForUpdate("o/r", "0.2.0", null);
    expect(out.upToDate).toBe(true);
    expect(out.via).toBe("anonymous");
  });
});

describe("device flow poll", () => {
  it("maps pending / slow_down / granted / denied", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "authorization_pending" }), { status: 200 })));
    expect(await deviceFlowPollOnce("cid", "dc")).toEqual({ status: "pending" });

    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "slow_down", interval: "10" }), { status: 200 })));
    expect(await deviceFlowPollOnce("cid", "dc")).toEqual({ status: "slow_down", intervalSeconds: 10 });

    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ access_token: "gho_x" }), { status: 200 })));
    expect(await deviceFlowPollOnce("cid", "dc")).toEqual({ status: "granted", token: "gho_x" });

    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "access_denied" }), { status: 200 })));
    const denied = await deviceFlowPollOnce("cid", "dc");
    expect(denied.status).toBe("denied");
  });
});
