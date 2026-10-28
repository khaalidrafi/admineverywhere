/** CHAT-SEND-BACK-2 live-path proof (née COOL-CHAT-SEND-BACK-2) — the system prompt that ACTUALLY
 *  leaves the panel, not a hand-written string fed to systemPrompt().
 *
 *  chat.test.ts unit-tests buildSchemaPrompt and systemPrompt in isolation;
 *  that is exactly how a disconnected builder stayed green before. This file
 *  mounts the real ChatPanel, drives it as a user would (open → type → send)
 *  and asserts on the captured fetch request body, built from the REAL
 *  normalized fixture schema. Same harness as widgetMount/shell/rbac. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import ChatPanel from "../../ai/ChatPanel.svelte";
import { ai, app } from "../stores";
import { normalizeOpenAPI } from "../openapi";
import type { AdminSchema } from "../types";
import fixture from "./fixtures/openapi.json";

const LEGEND = "Available models (fields in parentheses; fk = foreign key to that model):";
const schema = normalizeOpenAPI(fixture);

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const hosts: HTMLElement[] = [];
let instance: Record<string, any> | null = null;

afterEach(() => {
  if (instance) unmount(instance);
  instance = null;
  while (hosts.length) hosts.pop()!.remove();
  ai.set({ baseUrl: "", apiKey: "", model: "" });
  mockFetch.mockReset();
});

function sseReply(...texts: string[]) {
  const payload = [...texts.map((t) => `data: ${JSON.stringify({ choices: [{ delta: { content: t } }] })}\n\n`), "data: [DONE]\n\n"];
  let i = 0;
  return {
    ok: true,
    status: 200,
    text: async () => "",
    body: {
      getReader() {
        return {
          read: async () =>
            i < payload.length
              ? { done: false, value: new TextEncoder().encode(payload[i++]) }
              : { done: true, value: undefined as never },
        };
      },
    },
  };
}

async function openAndSend(text: string, liveSchema: AdminSchema | null = schema) {
  app.update((a) => ({ ...a, schema: liveSchema }));
  ai.set({ baseUrl: "http://provider.test/v1", apiKey: "sk-test", model: "test-model" });
  const host = document.createElement("div");
  document.body.append(host);
  hosts.push(host);
  flushSync(() => {
    instance = mount(ChatPanel, { target: host });
  });

  // launcher button opens the panel
  const launcher = host.querySelector("button")!;
  flushSync(() => launcher.dispatchEvent(new MouseEvent("click", { bubbles: true })));

  const input = host.querySelector<HTMLInputElement>('input[placeholder="Ask about your data…"]')!;
  flushSync(() => {
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  const form = input.closest("form")!;
  flushSync(() => form.dispatchEvent(new Event("submit", { bubbles: false, cancelable: true })));
  await vi.waitFor(() => expect(mockFetch).toHaveBeenCalled());
  return host;
}

function sentMessages(): Array<{ role: string; content: string }> {
  const init = mockFetch.mock.calls[0][1];
  return JSON.parse(init.body).messages;
}

describe("mounted ChatPanel prompt path", () => {
  it("streams and posts a system prompt built from the live schema, legend intact", async () => {
    mockFetch.mockResolvedValue(sseReply("Hi", " there"));
    const host = await openAndSend("which models exist?");

    expect(mockFetch.mock.calls[0][0]).toBe("http://provider.test/v1/chat/completions");
    const messages = sentMessages();
    expect(messages[0].role).toBe("system");
    // the legend the send-back restored — first line of the prompt body
    expect(messages[0].content).toContain(LEGEND);
    // and it is the REAL normalized schema, not a fixture-shaped guess
    expect(messages[0].content).toContain("- Product [/api/products/]:");
    expect(messages[0].content).toContain("category(fk->categories)");
    expect(messages[0].content).toContain("You are the assistant inside the Admineverywhere admin dashboard.");
    expect(messages[1]).toEqual({ role: "user", content: "which models exist?" });

    await vi.waitFor(() => {
      flushSync(() => {});
      expect(host.textContent).toContain("Hi there");
    });
  });

  it("says so plainly when the schema never loaded, instead of sending an empty model list", async () => {
    mockFetch.mockResolvedValue(sseReply("ok"));
    await openAndSend("hello?", null);

    const messages = sentMessages();
    expect(messages[0].content).toContain("no schema loaded");
    expect(messages[0].content).not.toContain(LEGEND);
  });

  it("stays a friendly setup panel and sends nothing while unconfigured", async () => {
    ai.set({ baseUrl: "", apiKey: "", model: "" });
    const host = document.createElement("div");
    document.body.append(host);
    hosts.push(host);
    flushSync(() => {
      instance = mount(ChatPanel, { target: host });
    });
    flushSync(() => host.querySelector("button")!.dispatchEvent(new MouseEvent("click", { bubbles: true })));

    // the three-input setup surface, not an error state (chat panel spec)
    expect(host.textContent).toContain("Works with OpenAI, Groq, Ollama");
    expect(host.querySelector('input[type="url"]')).not.toBeNull();
    expect(host.querySelector('input[placeholder="Ask about your data…"]')).toBeNull();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
