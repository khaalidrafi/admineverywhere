/** The demo flow's Ctrl+K step is graded by a SECOND SSE implementation nobody compared.
 *
 *  `scripts/mock_openai.js` is the rig the definition-of-done runs on ("Ctrl+K streams
 *  via scripts/mock_openai.js on :11435"), and it spells the SSE framing itself —
 *  `data: {json}\n\n` plus a bare `data: [DONE]` terminator — while `app/src/lib/chat.ts`
 *  is the only reader of it in the product. Both sides were green alone: the parser's
 *  unit tests feed it hand-written lines and the mock had no test at all, so a drift
 *  between the two (a changed terminator, a framing the parser drops, a payload the
 *  parser swallows) surfaced only as a live demo that silently printed nothing.
 *
 *  So this boots the REAL mock on a REAL socket and grades the client against the
 *  server's OWN other endpoint: `stream:false` on the same process returns the same
 *  answer as one JSON body. The oracle is that string, never a copy transcribed here —
 *  a hardcoded expectation would drift with the mock's prose and agree with nothing.
 */
// @vitest-environment node
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chatEndpoint, createSSEParser, streamChatCompletion, type ChatMessage } from "../chat";

// Shipped path, plus the override the control runs use to point this test at a
// MUTATED COPY of the rig (the team's control law: a harness proves its teeth on a
// copy, never by editing the file the tree ships).
const MOCK_SCRIPT =
  process.env.MOCK_OPENAI_SCRIPT ??
  fileURLToPath(new URL("../../../../scripts/mock_openai.js", import.meta.url));

type Mock = { baseUrl: string; stop: () => void };

let mock: Mock | null = null;

function startMock(): Promise<Mock> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [MOCK_SCRIPT], {
      // Port 0 = the kernel picks a free one, so this test neither collides with a
      // developer's running :11435 mock nor steals the port from it.
      env: { ...process.env, MOCK_OPENAI_PORT: "0" },
    });
    let out = "";
    const giveup = setTimeout(() => {
      child.kill();
      reject(new Error(`mock provider never reported its port; stdout was: ${out || "(empty)"}`));
    }, 15_000);
    child.on("error", (err) => {
      clearTimeout(giveup);
      child.kill();
      reject(err);
    });
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (piece: string) => {
      out += piece;
      const bound = /MOCK_OPENAI_LISTENING (\d+)/.exec(out);
      if (!bound) return;
      clearTimeout(giveup);
      resolve({ baseUrl: `http://127.0.0.1:${bound[1]}/v1`, stop: () => child.kill() });
    });
  });
}

function ask(baseUrl: string, body: Record<string, unknown>): Promise<Response> {
  return fetch(chatEndpoint(baseUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const messages: ChatMessage[] = [
  { role: "system", content: "You are a schema-aware assistant." },
  { role: "user", content: "Which models and fields does my API have?" },
];

describe("mock_openai.js <-> chat.ts over a real socket", () => {
  beforeAll(async () => {
    mock = await startMock();
  }, 20_000);

  afterAll(() => {
    mock?.stop();
  });

  it("streams the exact answer the same server returns unstreamed", async () => {
    const baseUrl = mock!.baseUrl;
    const model = "mock-gpt-4o-mini";
    const cfg = { baseUrl, apiKey: "", model };

    // The oracle: the non-streaming half of the same endpoint.
    const plain = await (await ask(baseUrl, { model, messages, stream: false })).json();
    const expected: string = plain?.choices?.[0]?.message?.content ?? "";
    expect(expected, "the mock must answer the prompt at all").not.toBe("");

    // The product path, over the network as the server delivers it.
    const deltas: string[] = [];
    const full = await streamChatCompletion(cfg, messages, (t) => deltas.push(t));
    expect(full).toBe(expected);
    expect(deltas.length, "a streamed answer must arrive in pieces, not one blob").toBeGreaterThan(1);

    // Adversarial chunking of the SAME wire bytes: the live socket hands the parser
    // whole `data:` lines, so it cannot see a split inside a line. A 7-byte stride
    // guaranteedly cuts through the JSON, and the assembly must not move.
    const resp = await ask(baseUrl, { model, messages, stream: true });
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let raw = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      raw += decoder.decode(value, { stream: true });
    }
    expect(raw, "the mock must answer as SSE, not as one JSON body").toContain("data: ");
    expect(raw).toContain("data: [DONE]");

    let replay = "";
    const feed = createSSEParser((payload) => {
      if (payload === "[DONE]") return;
      try {
        replay += JSON.parse(payload)?.choices?.[0]?.delta?.content ?? "";
      } catch {
        /* malformed keep-alive — the same rule the client applies */
      }
    });
    for (let i = 0; i < raw.length; i += 7) feed(raw.slice(i, i + 7));
    expect(replay, "7-byte network splits must not lose or duplicate a delta").toBe(expected);
  }, 30_000);
});
