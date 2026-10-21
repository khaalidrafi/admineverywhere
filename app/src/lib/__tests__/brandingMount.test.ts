/** The runtime-branding editor mounted for real — the wire-level proof the
 *  pure-module tests (branding.test.ts) cannot give: the form boots from the
 *  brand the BACKEND served, a save PUTs exactly the bytes the plugin's closed
 *  schema expects to <discovered>/admincraft/branding/, a 400 renders the
 *  server's own `errors` verbatim, and an already-uploaded asset travels as a
 *  filename instead of being re-encoded. Same law as chatMount.test.ts and
 *  lifecycleMount.test.ts: assert the request the component ACTUALLY makes,
 *  not the builder a unit test feeds itself.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import Branding from "../../pages/Branding.svelte";
import { app } from "../stores";
import { BRAND_DEFAULTS } from "../branding";
import type { Brand } from "../types";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

let host: HTMLElement | null = null;
let instance: Record<string, any> | null = null;

const SERVED: Brand = {
  appName: "Freshorama",
  tagline: "Wholesale, rebranded",
  colors: { primary: "#ff0000" },
  radius: "0.25rem",
  font: "Poppins",
};

function resetStore(brand: Brand) {
  app.set({
    booted: true,
    config: { apiUrl: "http://api.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" },
    brand: structuredClone(brand),
    token: "staff-token",
    username: "admin",
    apiUrlOverride: "",
    schema: null,
    schemaLoading: false,
    backendDown: false,
  });
}

function render(brand: Brand = SERVED): HTMLElement {
  resetStore(brand);
  host = document.createElement("div");
  document.body.append(host);
  flushSync(() => {
    instance = mount(Branding, { target: host! });
  });
  return host;
}

function jsonReply(status: number, data: any) {
  return {
    ok: status < 400,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

/** Only the branding PUT is expected; anything else fails the test loudly. */
function routePut(reply: { status: number; body: any }) {
  mockFetch.mockImplementation(async () => jsonReply(reply.status, reply.body));
}

const textInputs = (root: HTMLElement) =>
  [...root.querySelectorAll<HTMLInputElement>('input[type="text"]')];
const colorInputs = (root: HTMLElement) => [...root.querySelectorAll<HTMLInputElement>('input[type="color"]')];
const saveButton = (root: HTMLElement) =>
  [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => /Save brand/i.test(b.textContent ?? ""))!;

function setValue(el: HTMLInputElement, value: string) {
  el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

const runtimeCss = () => document.getElementById("brand-runtime")?.textContent ?? "";
const errorLines = (root: HTMLElement) =>
  [...root.querySelectorAll("li")].map((li) => li.textContent?.trim() ?? "");

/** The body the editor PUT, parsed off the recorded fetch call. */
function putCall(): { url: string; init: any; body: any } {
  const call = mockFetch.mock.calls.find(([, init]) => (init as any)?.method === "PUT");
  if (!call) throw new Error("no PUT was issued — calls: " + JSON.stringify(mockFetch.mock.calls.map((c) => c[0])));
  const [url, init] = call as [string, any];
  return { url: String(url), init, body: JSON.parse(init.body) };
}

async function clickSave(root: HTMLElement) {
  saveButton(root).click();
  await flushAsync();
}

async function flushAsync() {
  // the save chain crosses real macrotasks (FileReader.onload, blob()), so
  // microtask ticks alone leave it mid-flight — settle with timers instead
  for (let i = 0; i < 6; i++) {
    await new Promise((r) => setTimeout(r, 0));
    flushSync(() => {});
  }
}

afterEach(() => {
  if (instance) unmount(instance);
  instance = null;
  if (host) host.remove();
  host = null;
  document.getElementById("brand-runtime")?.remove();
  document.title = "";
  mockFetch.mockReset();
  app.set({} as any);
});

describe("Branding editor mounted (runtime branding API)", () => {
  it("boots the draft from the SERVED brand, filling only the missing colors", () => {
    const root = render();
    expect(textInputs(root)[0]?.value, "app name input != served brand").toBe("Freshorama");
    expect(textInputs(root)[1]?.value).toBe("Wholesale, rebranded");
    expect(textInputs(root).find((i) => i.placeholder === "Inter")?.value).toBe("Poppins");
    // primary comes from the server, accent from BRAND_DEFAULTS — the
    // {...BRAND_DEFAULTS, ...orig.colors} fill-in, asserted on the DOM
    const [primary, accent] = colorInputs(root);
    expect(primary?.value).toBe("#ff0000");
    expect(accent?.value).toBe(BRAND_DEFAULTS.accent.toLowerCase());
    expect(runtimeCss()).toContain("--brand-primary: #ff0000");
  });

  it("re-themes live on edit and restores the original on unmount", () => {
    const root = render();
    setValue(textInputs(root)[0], "Khaalid HQ");
    colorInputs(root)[0].value = "#00ff00";
    colorInputs(root)[0].dispatchEvent(new Event("input", { bubbles: true }));
    flushSync(() => {});

    expect(document.title).toBe("Khaalid HQ");
    expect(runtimeCss()).toContain("--brand-primary: #00ff00");

    unmount(instance!);
    instance = null;
    expect(document.title, "unmount must revert the live preview")
      .toBe("Freshorama");
    expect(runtimeCss()).toContain("--brand-primary: #ff0000");
  });

  it("Save PUTs the edited brand, with the staff token, to the plugin endpoint", async () => {
    routePut({ status: 200, body: { brand: { ...SERVED, appName: "Renamed" }, rev: 7 } });
    const root = render();
    setValue(textInputs(root)[0], "  Renamed  ");
    await clickSave(root);

    const { url, init, body } = putCall();
    expect(url).toBe("http://api.test/admincraft/branding/");
    expect(init.headers.Authorization).toBe("Token staff-token");
    // trimmed before it goes on the wire, and the served color survived the round trip
    expect(body.appName).toBe("Renamed");
    expect(body.colors.primary).toBe("#ff0000");
    expect(body.font).toBe("Poppins");
    expect(body.radius).toBe("0.25rem");
    // no asset was ever configured → the keys stay out of the payload entirely
    expect("logo" in body, "empty logo must not be sent as an empty string").toBe(false);
    expect("favicon" in body).toBe(false);
  });

  it("a backend rejection renders the server's `errors` verbatim and applies nothing", async () => {
    routePut({
      status: 400,
      body: { errors: ["colors.bg: '#nope' is not a valid hex color", "font: 'F@nt' has punctuation"] },
    });
    const root = render();
    await clickSave(root);

    expect(errorLines(root)).toEqual([
      "colors.bg: '#nope' is not a valid hex color",
      "font: 'F@nt' has punctuation",
    ]);
    expect(document.title, "a rejected brand never reaches the live theme").toBe("Freshorama");
    expect(runtimeCss()).toContain("--brand-primary: #ff0000");
  });

  it("an empty app name is refused client-side with zero requests", async () => {
    routePut({ status: 200, body: { brand: SERVED, rev: 1 } });
    const root = render();
    setValue(textInputs(root)[0], "   ");
    await clickSave(root);

    expect(errorLines(root)).toContain("appName: must not be empty");
    expect(mockFetch, "the guard must fire before the PUT").not.toHaveBeenCalled();
  });

  it("an already-uploaded asset travels as its filename — never re-encoded", async () => {
    routePut({ status: 200, body: { brand: SERVED, rev: 3 } });
    const root = render({ ...SERVED, logo: "http://api.test/admincraft/branding/asset/logo.png" });
    await clickSave(root);

    const { body } = putCall();
    expect(body.logo).toBe("logo.png");
    expect(mockFetch.mock.calls.length, "keeping a server asset must not fetch it").toBe(1);
  });

  it("a bundled static asset is re-uploaded as a data URL on the first save", async () => {
    routePut({ status: 200, body: { brand: SERVED, rev: 4 } });
    mockFetch.mockImplementation(async (url: string) => {
      if (String(url).includes("/admincraft/branding/")) return jsonReply(200, { brand: SERVED, rev: 4 });
      return {
        ok: true,
        status: 200,
        blob: async () => new Blob(["<svg xmlns='http://www.w3.org/2000/svg'/>"], { type: "image/svg+xml" }),
      };
    });
    const root = render({ ...SERVED, logo: "/logo.svg" });
    await clickSave(root);

    const { body } = putCall();
    expect(body.logo, "the shipped logo must survive the first save").toMatch(/^data:image\/svg\+xml;base64,/);
  });

  it("a fresh upload wins over both and clears after a successful save", async () => {
    routePut({ status: 200, body: { brand: SERVED, rev: 5 } });
    const root = render();
    const fileInput = host!.querySelector<HTMLInputElement>('input[type="file"]')!;
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);
    Object.defineProperty(fileInput, "files", { value: [new File([png], "logo.png", { type: "image/png" })] });
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    await flushAsync();

    expect([...host!.querySelectorAll("button")].some((b) => b.textContent?.trim() === "undo"),
      "the editor must acknowledge the pending upload").toBe(true);

    await clickSave(root);
    const { body } = putCall();
    expect(body.logo).toMatch(/^data:image\/png;base64,/);

    // after the save the upload is consumed: a second save sends nothing new
    mockFetch.mockClear();
    routePut({ status: 200, body: { brand: SERVED, rev: 6 } });
    await clickSave(root);
    expect(putCall().body.logo).toBeUndefined();
  });
});
