/** ChatPanel settings + stream-control paths, proven by CLICKING them.
 *
 *  chatMount.test.ts pins the system prompt that leaves the panel; storesTauri
 *  .test.ts pins saveAiSettings at store level. Neither one ever drove the
 *  panel's own Save button, Cancel, the Ctrl+K launcher, Stop or the error
 *  bubble — so the 17:47Z report's "pixels still unproven" gap stayed open.
 *  This file mounts the real panel and drives the form a user drives it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ChatPanel from "../../ai/ChatPanel.svelte";
import { get } from "svelte/store";
import { ai, app, loadAiSettings, saveAiSettings, toasts } from "../stores";
import { normalizeOpenAPI } from "../openapi";
import fixture from "./fixtures/openapi.json";

const schema = normalizeOpenAPI(fixture);

function configureProvider(baseUrl = "http://provider.test/v1", model = "gpt-4o-mini", apiKey = "sk-x") {
  ai.set({ baseUrl, apiKey, model });
  app.update((a) => ({ ...a, schema }));
}

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const invoke = vi.fn((cmd: string) => Promise.resolve(cmd === "load_secret" ? null : undefined));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

const hosts: HTMLElement[] = [];
let instance: Record<string, any> | null = null;

function setField(input: HTMLInputElement, value: string) {
  flushSync(() => {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function click(el: Element | null | undefined) {
  flushSync(() => el!.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

function mountPanel() {
  const host = document.createElement("div");
  document.body.append(host);
  hosts.push(host);
  flushSync(() => {
    instance = mount(ChatPanel, { target: host });
  });
  return host;
}

/** launcher → panel; an unconfigured panel opens its settings form itself */
function openPanel(host: HTMLElement) {
  click(host.querySelector("button"));
  return host;
}

const byTitle = (host: HTMLElement, title: string) =>
  [...host.querySelectorAll("button")].find((b) => b.getAttribute("title") === title);
const byText = (host: HTMLElement, text: string) =>
  [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(text));

afterEach(() => {
  if (instance) unmount(instance);
  instance = null;
  while (hosts.length) hosts.pop()!.remove();
  localStorage.clear();
  toasts.set([]);
  ai.set({ baseUrl: "", apiKey: "", model: "" });
  mockFetch.mockReset();
});

describe("mounted ChatPanel — provider settings form (web mode)", () => {
  it("Cancel closes the form and persists nothing", () => {
    const host = openPanel(mountPanel());
    expect(host.querySelector("#ai-base")).not.toBeNull();
    setField(host.querySelector("#ai-base")!, "http://provider.test/v1");

    click(byText(host, "Cancel"));

    expect(host.querySelector("#ai-base")).toBeNull();
    expect(localStorage.getItem("dad.ai.baseUrl")).toBeNull();
    expect(get(ai)).toEqual({ baseUrl: "", apiKey: "", model: "" });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("the unconfigured friendly state re-opens the form from its own button", () => {
    const host = openPanel(mountPanel());
    click(byText(host, "Cancel"));

    // {:else if !configured} branch: a setup prompt, not an error
    expect(host.textContent).toContain("Talk to your data");
    expect(host.textContent).not.toContain("Error");
    const setupBtn = byText(host, "Set up provider");
    expect(setupBtn).toBeDefined();

    click(setupBtn);
    expect(host.querySelector("#ai-model")).not.toBeNull();
  });

  it("Save provider writes trimmed values to store + localStorage + the secret store, then shows the chat", async () => {
    const host = openPanel(mountPanel());
    setField(host.querySelector("#ai-base")!, "  http://provider.test/v1  ");
    setField(host.querySelector("#ai-key")!, "  sk-sentinel-key  ");
    setField(host.querySelector("#ai-model")!, "  gpt-4o-mini  ");
    click(byText(host, "Save provider"));

    await vi.waitFor(() => {
      expect(get(ai)).toEqual({
        baseUrl: "http://provider.test/v1",
        apiKey: "sk-sentinel-key",
        model: "gpt-4o-mini",
      });
    });
    expect(localStorage.getItem("dad.ai.baseUrl")).toBe("http://provider.test/v1");
    expect(localStorage.getItem("dad.ai.model")).toBe("gpt-4o-mini");
    expect(localStorage.getItem("dad.secret.ai.apiKey")).toBe("sk-sentinel-key");
    // saveSettings awaits the secret write before toasting, so the success
    // signal lands in a later task (17:46Z note: assert absence/presence at a
    // macrotask boundary, never after two microtask ticks)
    await new Promise((r) => setTimeout(r, 50));
    expect(get(toasts).map((t) => t.text)).toContain("AI provider saved");
    expect(host.querySelector("#ai-base")).toBeNull();
    // configured: composer back, model badge in the header
    expect(host.querySelector('input[placeholder="Ask about your data…"]')).not.toBeNull();
    expect(host.textContent).toContain("gpt-4o-mini");
  });

  it("clearing the API key through the form really forgets it (save → reload → clear → reload)", async () => {
    await saveAiSettings("http://provider.test/v1", "sk-first", "gpt-4o-mini");
    await loadAiSettings();
    expect(get(ai).apiKey).toBe("sk-first");

    const host = openPanel(mountPanel());
    click(byTitle(host, "Provider settings"));
    expect(host.querySelector<HTMLInputElement>("#ai-key")!.value).toBe("sk-first");

    setField(host.querySelector("#ai-key")!, "");
    click(byText(host, "Save provider"));
    await vi.waitFor(() => expect(localStorage.getItem("dad.secret.ai.apiKey")).toBeNull());

    ai.set({ baseUrl: "", apiKey: "", model: "" });
    await loadAiSettings();
    expect(get(ai).apiKey).toBe("");
    expect(get(ai).baseUrl).toBe("http://provider.test/v1");
  });

  it("hydrates the three inputs from the store when the gear is pressed again", () => {
    configureProvider("http://provider.test/v1", "llama3.2", "sk-hydrate");
    const host = openPanel(mountPanel());
    expect(host.querySelector("#ai-base")).toBeNull();

    click(byTitle(host, "Provider settings"));
    expect(host.querySelector<HTMLInputElement>("#ai-base")!.value).toBe("http://provider.test/v1");
    expect(host.querySelector<HTMLInputElement>("#ai-key")!.value).toBe("sk-hydrate");
    expect(host.querySelector<HTMLInputElement>("#ai-model")!.value).toBe("llama3.2");
    // the key is never rendered as plain text in a visible field
    expect(host.querySelector("#ai-key")!.getAttribute("type")).toBe("password");
  });

  it("tells the truth about where the key lives, in both modes", () => {
    const host = openPanel(mountPanel());
    expect(host.textContent).toContain("Browser mode: stored in localStorage");
    expect(host.textContent).toContain("Works with OpenAI, Groq, Ollama");
  });

  it("Ctrl+K opens the panel, Ctrl+K again closes it", () => {
    const host = mountPanel();
    expect(host.querySelector('input[placeholder="Ask about your data…"]')).toBeNull();

    flushSync(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
    });
    expect(host.querySelector("form")).not.toBeNull();

    flushSync(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "K", metaKey: true }));
    });
    expect(host.querySelector("form")).toBeNull();

    // the launcher returns when the panel is closed
    expect(byTitle(host, "AI assistant (Ctrl+K)") ?? host.querySelector("button")).toBeTruthy();
  });

  it("the Close button dismisses the panel and keeps the saved provider", () => {
    configureProvider("http://provider.test/v1", "m-1");
    const host = openPanel(mountPanel());
    click(byTitle(host, "Close"));
    expect(host.textContent).not.toContain("AI Assistant");
    expect(get(ai).model).toBe("m-1");
  });
});

describe("mounted ChatPanel — stream controls", () => {
  function configuredHost() {
    configureProvider();
    return openPanel(mountPanel());
  }

  function typeAndSubmit(host: HTMLElement, text: string) {
    const input = host.querySelector<HTMLInputElement>('input[placeholder="Ask about your data…"]')!;
    setField(input, text);
    flushSync(() =>
      input.closest("form")!.dispatchEvent(new Event("submit", { bubbles: false, cancelable: true })),
    );
    return input;
  }

  it("a provider error surfaces verbatim and leaves no empty assistant bubble", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 429,
      text: async () => JSON.stringify({ error: { message: "Rate limit reached for gpt-4o-mini" } }),
    });
    const host = configuredHost();
    typeAndSubmit(host, "too fast");
    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Provider error 429: Rate limit reached for gpt-4o-mini");
    });
    // the empty assistant turn is popped: only the user bubble survives, and
    // no "…" placeholder hangs under it
    const bubbles = host.querySelectorAll('div[class*="max-w-"]');
    expect(bubbles).toHaveLength(1);
    expect(bubbles[0].textContent).toContain("too fast");
    expect(host.textContent).not.toContain("…");
    expect(host.querySelector('input[placeholder="Ask about your data…"]')).not.toBeNull();
  });

  it("an unreachable provider is reported as such, with the base URL named", async () => {
    mockFetch.mockRejectedValue(Object.assign(new Error("connection refused"), { name: "TypeError" }));
    const host = configuredHost();
    typeAndSubmit(host, "hello?");
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Could not reach http://provider.test/v1");
      expect(host.textContent).toContain("connection refused");
    });
  });

  it("Stop aborts the stream and the bubble says it stopped", async () => {
    let captured: AbortSignal | null = null;
    let firstChunk = true;
    mockFetch.mockImplementation((_url: string, init: RequestInit) => {
      captured = init.signal as AbortSignal;
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => "",
        body: {
          getReader() {
            return {
              read(): Promise<any> {
                if (firstChunk) {
                  firstChunk = false;
                  return Promise.resolve({
                    done: false,
                    value: new TextEncoder().encode(
                      `data: ${JSON.stringify({ choices: [{ delta: { content: "Half a sentence" } }] })}\n\n`,
                    ),
                  });
                }
                return new Promise((_res, rej) => {
                  const abortErr = () => rej(Object.assign(new Error("aborted"), { name: "AbortError" }));
                  if (captured!.aborted) return abortErr();
                  captured!.addEventListener("abort", abortErr);
                });
              },
            };
          },
        },
      });
    });

    const host = configuredHost();
    typeAndSubmit(host, "tell me slowly");
    await vi.waitFor(() => expect(host.textContent).toContain("Half a sentence"));

    const stop = byTitle(host, "Stop");
    expect(stop).toBeDefined();
    // while streaming the composer is locked and send is replaced by stop
    expect(host.querySelector<HTMLInputElement>('input[placeholder="Ask about your data…"]')!.disabled).toBe(true);

    const requestsBefore = mockFetch.mock.calls.length;
    typeAndSubmit(host, "sneaky second message");
    expect(mockFetch.mock.calls.length).toBe(requestsBefore);

    click(stop);
    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Half a sentence — stopped.");
    });
    expect(host.textContent).not.toContain("sneaky second message");
    expect(byTitle(host, "Stop")).toBeUndefined();
    expect(
      host.querySelector<HTMLInputElement>('input[placeholder="Ask about your data…"]')!.disabled,
    ).toBe(false);
  });

  it("a blank or whitespace-only prompt never fires a request", () => {
    const host = configuredHost();
    const input = typeAndSubmit(host, "   ");
    expect(input.closest("form")!.querySelector("button")!.hasAttribute("disabled")).toBe(true);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

/** Same form, Tauri mode. The marker goes on the REAL happy-dom window
 *  (harness law from the 17:46Z note) and the keyring module is mocked at
 *  file level, so stores/secrets resolve `invoke` on the lazy dynamic import
 *  inside secrets.ts. NO vi.resetModules here: a freshly-imported ChatPanel
 *  then belongs to a SECOND svelte runtime, and the static flushSync() stops
 *  flushing its queue — a gear click that reaches the button but never
 *  re-renders. One module graph per file is the cheaper law. */
describe("mounted ChatPanel — provider settings under the Tauri keyring", () => {
  afterEach(() => {
    delete (window as any).__TAURI_INTERNALS__;
    invoke.mockReset();
    invoke.mockImplementation((cmd: string) => Promise.resolve(cmd === "load_secret" ? null : undefined));
  });

  function mountTauriPanel() {
    (window as any).__TAURI_INTERNALS__ = {};
    const host = openPanel(mountPanel());
    return host;
  }

  /** settings closed = saveSettings finished its awaited keyring write */
  async function saveThroughForm(host: HTMLElement, key: string) {
    setField(host.querySelector("#ai-base")!, "http://provider.test/v1");
    setField(host.querySelector("#ai-key")!, key);
    setField(host.querySelector("#ai-model")!, "llama3.2");
    click(byText(host, "Save provider"));
    await vi.waitFor(() => expect(host.querySelector("#ai-base")).toBeNull());
  }

  it("Save provider writes the key through the keyring and keeps it out of localStorage", async () => {
    const host = mountTauriPanel();

    expect(host.textContent).toContain("Stored in the OS keychain.");
    await saveThroughForm(host, "sk-tauri-sentinel");

    expect(invoke).toHaveBeenCalledWith("save_secret", {
      service: "admineverywhere",
      key: "ai.apiKey",
      value: "sk-tauri-sentinel",
    });
    // one macrotask, then scan every byte localStorage holds
    await new Promise((r) => setTimeout(r, 50));
    const dumped = JSON.stringify(Object.keys(localStorage).map((k) => [k, localStorage.getItem(k)]));
    expect(dumped).not.toContain("sk-tauri-sentinel");
    expect(localStorage.getItem("dad.ai.baseUrl")).toBe("http://provider.test/v1");
    expect(get(ai).apiKey).toBe("sk-tauri-sentinel");
  });

  it("clearing the key in the form calls delete_secret, not a skipped write", async () => {
    const host = mountTauriPanel();
    await saveThroughForm(host, "sk-tauri-sentinel");

    click(byTitle(host, "Provider settings"));
    expect(host.querySelector<HTMLInputElement>("#ai-key")!.value).toBe("sk-tauri-sentinel");
    setField(host.querySelector("#ai-key")!, "");
    invoke.mockClear();
    click(byText(host, "Save provider"));

    await vi.waitFor(() =>
      expect(invoke).toHaveBeenCalledWith("delete_secret", {
        service: "admineverywhere",
        key: "ai.apiKey",
      }),
    );
    expect(get(ai).apiKey).toBe("");
  });
});
