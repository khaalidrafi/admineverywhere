/** The splash IS the brand (deep branding, owner order): when the brand
 *  ships a loaderVideo it plays as THE loader — full-viewport, played ONCE
 *  through (the splash holds until its 'ended', QA 5-a D1) — and without
 *  one the pulsing gradient tile stays the fallback. Mounted through the
 *  real App.svelte so the branch structure is proven in the DOM, not by a
 *  code read.
 *
 *  Timing note: App's onMount kicks initApp (async) — the splash paints
 *  synchronously with the mount while `booted` is still false, which is
 *  exactly the state under test. The splash HOLD timing lives in
 *  splashHold.test.ts (fake timers); here only the painted structure
 *  matters, asserted synchronously before any release can happen.
 *  fetch is stubbed so the DEV override reads 404 and the boot completes
 *  with the bundled identity afterwards.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import App from "../../App.svelte";
import { app } from "../stores";

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
});

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!.instance);
  document.body.innerHTML = "";
  app.set(snapshot);
  document.title = "";
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

describe("App splash — the intro video is the loader", () => {
  it("a brand loaderVideo renders the full-viewport <video> and NO skeleton", () => {
    const host = renderSplash({ loaderVideo: "intro.mp4" });

    const video = host.querySelector("video");
    expect(video).not.toBeNull();
    // bundled assets are normalized to the public/ root by the stamp; the
    // bare name IS the app-relative URL
    expect(video!.getAttribute("src")).toBe("intro.mp4");
    expect(video!.hasAttribute("autoplay")).toBe(true);
    // NO loop: the intro is a one-shot loader — the splash releases on its
    // 'ended' event, which a looping clip would never fire
    expect(video!.hasAttribute("loop")).toBe(false);
    expect(video!.hasAttribute("playsinline")).toBe(true);
    // the intro plays full-viewport (QA 5-a D1: the video IS the loader)
    expect(video!.className).toContain("object-cover");
    expect(video!.className).toContain("size-full");

    // owner order: the splash carries no other loader — no skeleton bar,
    // no spinning icon, and the gradient tile is replaced, not stacked
    expect(host.querySelector(".skeleton")).toBeNull();
    expect(host.querySelector(".animate-spin")).toBeNull();
    expect(host.querySelector(".animate-pulse")).toBeNull();
    // the appName still rides the intro, overlaid at the bottom
    expect(host.textContent).toContain($appAppName());
  });

  it("a muted, PiC-free player: the intro must not hijack audio or the screen", () => {
    const host = renderSplash({ loaderVideo: "intro.mp4" });
    const video = host.querySelector("video")!;
    expect(
      video.hasAttribute("muted") || (video as HTMLVideoElement).muted === true,
    ).toBe(true);
    expect(video!.hasAttribute("disablepictureinpicture")).toBe(true);
  });

  it("without a loaderVideo the pulsing gradient tile remains the fallback loader — still no skeleton", () => {
    const host = renderSplash({ loaderVideo: undefined });

    expect(host.querySelector("video")).toBeNull();
    const tile = host.querySelector(".animate-pulse");
    expect(tile).not.toBeNull();
    expect(tile!.className).toContain("bg-gradient-to-br");
    expect(host.querySelector(".skeleton")).toBeNull();
    expect(host.querySelector(".animate-spin")).toBeNull();
    expect(host.textContent).toContain($appAppName());
  });
});

/** The splash appName comes from the live brand (bundled stock here). */
function $appAppName(): string {
  let value: any;
  const un = app.subscribe((v) => (value = v));
  un();
  return value.brand.appName;
}
