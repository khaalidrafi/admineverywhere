/** Splash minimum hold (QA 5-a / D1) — the brand intro must actually paint.
 *
 *  QA measured the splash DOM committing for only ~22-42ms: initApp flips
 *  `booted` synchronously after boot, so the login replaced the splash
 *  BEFORE the first paint. The splash now holds a brand-controlled minimum
 *  while boot continues underneath — video mode holds until the clip's
 *  'ended' (or a tap-to-skip armed after 600ms) and >=800ms elapsed; the
 *  pulsing accent tile holds >=600ms. Fake timers drive the hold so the
 *  suite stays instant; boot still completes underneath (fetch stubbed to
 *  404, the DEV override keeps the bundled identity).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { flushSync, mount, unmount } from "svelte";
import App from "../../App.svelte";
import { app } from "../stores";

// The bundled brand the way `build_admin --brand` ships a video brand:
// brand.gen.ts INLINES loaderVideo, so boot keeps the intro instead of
// swapping to the stock identity (the committed stock brand.gen has none —
// a swap like that mid-hold is exactly what the release valve handles).
vi.mock("../brand.gen", () => ({
  BUNDLED_BRAND: {
    appName: "Freshorama Admin",
    tagline: "Manage everything, beautifully",
    loaderVideo: "intro.mp4",
    colors: {
      primary: "#006e33",
      accent: "#22be6f",
      bg: "#f6faf6",
      surface: "#ffffff",
      text: "#14301f",
    },
    radius: "0.75rem",
    font: "Inter",
  },
  BUNDLED_CONFIG: { apiUrl: "", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
}));

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mounted: Array<Record<string, any>> = [];
let snapshot: any;

beforeEach(() => {
  let value: any;
  const un = app.subscribe((v) => (value = v));
  un();
  snapshot = { ...value };
  mockFetch.mockReset();
  mockFetch.mockImplementation(async () => new Response("", { status: 404 }));
  localStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!.instance);
  document.body.innerHTML = "";
  app.set(snapshot);
  document.title = "";
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function renderSplash(brandOverride: Record<string, unknown>): HTMLElement {
  localStorage.removeItem("dad.token");
  app.update((a) => ({
    ...a,
    token: "",
    booted: false,
    brand: { ...a.brand, ...brandOverride },
  }));
  const host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    mounted.push({ instance: mount(App, { target: host }) });
  });
  return host;
}

/** Drain boot's microtasks so initApp completes WHILE the splash holds. */
async function bootUnderneath(): Promise<void> {
  for (let i = 0; i < 10 && !get(app).booted; i++) {
    await vi.advanceTimersByTimeAsync(0);
  }
  expect(get(app).booted).toBe(true); // the boot itself was never delayed
}

describe("App splash hold — the handover waits, the boot does not", () => {
  it("the pulsing tile holds >=600ms even though boot finished underneath", async () => {
    const host = renderSplash({ loaderVideo: undefined });
    expect(host.querySelector(".animate-pulse")).not.toBeNull();

    await bootUnderneath();
    await vi.advanceTimersByTimeAsync(599);
    // boot IS done, the hold is not: still the splash, never the login
    expect(host.querySelector(".animate-pulse")).not.toBeNull();
    expect(document.querySelector("aside")).toBeNull();

    await vi.advanceTimersByTimeAsync(1);
    flushSync(() => {});
    expect(host.querySelector(".animate-pulse")).toBeNull(); // released
  });

  it("the intro video IS the loader: boot finishing early never cuts it — release waits for 'ended'", async () => {
    const host = renderSplash({ loaderVideo: "intro.mp4" });
    const video = host.querySelector("video");
    expect(video).not.toBeNull();

    await bootUnderneath();
    // boot finished with the bundled (stamped) brand — the intro keeps
    // playing: the video IS the loader, boot may never cut it short
    await vi.advanceTimersByTimeAsync(2000); // far past the 800ms minimum
    expect(host.querySelector("video")).not.toBeNull(); // still held

    video!.dispatchEvent(new Event("ended"));
    flushSync(() => {});
    expect(host.querySelector("video")).toBeNull(); // released on 'ended'
  });

  it("a broken intro cannot trap the user: 'error' ends the video phase", async () => {
    const host = renderSplash({ loaderVideo: "intro.mp4" });
    await bootUnderneath();
    await vi.advanceTimersByTimeAsync(800);

    host.querySelector("video")!.dispatchEvent(new Event("error"));
    flushSync(() => {});
    expect(host.querySelector("video")).toBeNull();
  });

  it("tap-to-skip: clicks before 600ms are ignored, the armed affordance skips", async () => {
    const host = renderSplash({ loaderVideo: "intro.mp4" });
    await bootUnderneath();

    await vi.advanceTimersByTimeAsync(599);
    window.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    flushSync(() => {});
    await vi.advanceTimersByTimeAsync(400); // 999ms — past the minimum, unskipped
    expect(host.querySelector("video")).not.toBeNull(); // pre-arm click did nothing

    await vi.advanceTimersByTimeAsync(1); // 600ms -> skip armed
    const skip = host.querySelector("button");
    expect(skip).not.toBeNull();
    expect(skip!.textContent).toContain("Tap to skip");
    skip!.click();
    flushSync(() => {});
    expect(host.querySelector("video")).toBeNull(); // armed tap skips
  });

  it("no animate-spin spinner survives anywhere in the splash tree", async () => {
    const videoHost = renderSplash({ loaderVideo: "intro.mp4" });
    expect(videoHost.querySelector(".animate-spin")).toBeNull();
    await bootUnderneath();
    await vi.advanceTimersByTimeAsync(100); // mid-hold, boot already done
    expect(videoHost.querySelector(".animate-spin")).toBeNull();

    const tileHost = renderSplash({ loaderVideo: undefined });
    expect(tileHost.querySelector(".animate-spin")).toBeNull();
    await vi.advanceTimersByTimeAsync(100);
    expect(tileHost.querySelector(".animate-spin")).toBeNull();
  });
});
