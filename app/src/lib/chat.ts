/** OpenAI-compatible chat with SSE streaming (works with OpenAI, Groq,
 *  Ollama, Mistral, LM Studio — anything speaking /chat/completions).
 *
 *  No provider SDK: raw fetch + SSE. Keeps the bundle tiny and universal.
 */
import type { AdminSchema, AppConfig } from "./types";
import { AGENT_IDENTITY } from "./agent";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatConfig {
  baseUrl: string;
  apiKey: string;
  model: string;
}

/** Feed network chunks in, get SSE `data:` payloads out.
 *  Handles: partial lines across chunks, CRLF, comment lines, keep-alives. */
export function createSSEParser(onData: (payload: string) => void) {
  let buffer = "";
  const MAX_LINE = 1024 * 1024;
  return (chunk: string) => {
    buffer += chunk;
    if (buffer.length > MAX_LINE && !buffer.includes("\n")) {
      console.warn(`[chat] Dropping oversized SSE line fragment (>${MAX_LINE} bytes)`);
      buffer = "";
    }
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? ""; // incomplete tail stays buffered
    for (const raw of lines) {
      const line = raw.replace(/\r$/, "");
      if (!line || line.startsWith(":")) continue; // comment / keep-alive
      if (line.startsWith("data:")) {
        onData(line.slice(5).trim());
      }
    }
  };
}

export function chatEndpoint(baseUrl: string): string {
  const base = baseUrl.replace(/\/+$/, "");
  return `${base}/chat/completions`;
}

/** Build schema-aware system prompt from live AdminSchema. */
export function buildSchemaPrompt(schema: AdminSchema): string {
  const legend = "Available models (fields in parentheses; fk = foreign key to that model):";
  const lines = schema.models.map((m) => {
    const fields = m.fields
      .map((f) => (f.type === "fk" ? `${f.name}(fk->${f.fkModel})` : `${f.name}(${f.type})`))
      .join(", ");
    return `- ${m.name} [${m.listPath}]: ${fields}`;
  });
  return `${legend}
${lines.join("\n")}`;
}

/** Build the schema-aware system prompt. */
/** A non-empty `custom` (owner order 2026-11-09: system prompt setting)
 *  replaces the default persona lines but keeps the schema model-list and the
 *  behavior rules — the agent can never lose its grounding, whatever the
 *  persona says. Wording law (owner 2026-11-09): the assistant belongs to the
 *  ADMIN, never to a "dashboard". */
export function systemPrompt(appName: string, modelLines: string, custom = ""): string {
  const persona = custom.trim()
    ? custom.trim()
    : [
        `You are ${AGENT_IDENTITY.name}, the ${AGENT_IDENTITY.role} inside the ${appName} admin.`,
        "You help the operator understand and manage their data.",
      ].join("\n");
  return [
    persona,
    modelLines,
    "",
    "Answer concisely. When asked about data structure, refer to the models above.",
    "Never invent fields or endpoints that are not listed.",
  ].join("\n");
}

/** Stream a completion. onDelta receives each text chunk as it arrives.
 *  Returns the full assistant text. Throws ChatError with friendly messages. */
export async function streamChatCompletion(
  cfg: ChatConfig,
  messages: ChatMessage[],
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (cfg.apiKey) headers.Authorization = `Bearer ${cfg.apiKey}`;

  let resp: Response;
  try {
    resp = await fetch(chatEndpoint(cfg.baseUrl), {
      method: "POST",
      headers,
      signal,
      body: JSON.stringify({ model: cfg.model, messages, stream: true }),
    });
  } catch (err: any) {
    if (err?.name === "AbortError") throw err;
    throw new ChatError(
      `Could not reach ${cfg.baseUrl} — is the provider running? (${err?.message ?? err})`,
    );
  }

  if (!resp.ok) {
    let detail = await resp.text().catch(() => "");
    try {
      const parsed = JSON.parse(detail);
      detail = parsed?.error?.message ?? parsed?.detail ?? detail;
    } catch { /* plain text body */ }
    throw new ChatError(`Provider error ${resp.status}: ${String(detail).slice(0, 300)}`);
  }

  if (!resp.body) throw new ChatError("Provider returned an empty response body");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  const feed = createSSEParser((payload) => {
    if (payload === "[DONE]") return;
    try {
      const evt = JSON.parse(payload);
      const delta = evt?.choices?.[0]?.delta?.content ?? evt?.choices?.[0]?.text ?? "";
      if (delta) {
        full += delta;
        onDelta(delta);
      }
    } catch {
      // ignore malformed keep-alive payloads
    }
  });

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    feed(decoder.decode(value, { stream: true }));
  }
  return full;
}

export class ChatError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

/* ---- tool-calling turn (agentic mode) ---- */

/** Provider wire shape for one streamed tool-call fragment. */
export interface ToolCallDelta {
  index?: number;
  id?: string;
  type?: string;
  function?: { name?: string; arguments?: string };
}

/** A chat message on the wire: content-only like ChatMessage, plus the
 *  tool-calling extras (assistant tool_calls, tool results). */
export interface WireMessage extends ChatMessage {
  tool_calls?: Array<{ id: string; type: "function"; function: { name: string; arguments: string } }>;
  tool_call_id?: string;
}

export interface ParsedToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
}

export interface TurnResult {
  text: string;
  toolCalls: ParsedToolCall[];
}

/** Assemble streamed `delta.tool_calls` fragments (OpenAI streaming spec:
 *  fragments arrive by index, id/name on the first, arguments concatenated). */
export function assembleToolCalls(fragments: ToolCallDelta[]): ParsedToolCall[] {
  const byIndex = new Map<number, { id: string; name: string; args: string }>();
  for (const frag of fragments) {
    const idx = typeof frag.index === "number" ? frag.index : byIndex.size;
    const slot = byIndex.get(idx) ?? { id: "", name: "", args: "" };
    if (frag.id) slot.id = frag.id;
    if (frag.function?.name) slot.name = frag.function.name;
    if (frag.function?.arguments) slot.args += frag.function.arguments;
    byIndex.set(idx, slot);
  }
  return [...byIndex.entries()]
    .sort(([a], [b]) => a - b)
    .map(([i, slot]) => {
      let args: Record<string, any> = {};
      if (slot.args) {
        try {
          args = JSON.parse(slot.args);
        } catch {
          args = { _unparsed: slot.args };
        }
      }
      return { id: slot.id || `call_${i}`, name: slot.name || "unknown", args };
    });
}

/** One assistant turn with tools attached. Streams text deltas as they come
 *  (same SSE path as chat-only mode), accumulates tool-call fragments, and
 *  answers both in `TurnResult`. A provider that rejects streamed tool calls
 *  (HTTP 400) is retried once non-streaming before giving up — small LLMs
 *  behind OpenAI-compatible proxies often accept tools only unstreamed. */
export async function streamAssistantTurn(
  cfg: ChatConfig,
  messages: WireMessage[],
  opts: {
    tools?: ToolDefLite[];
    onDelta?: (text: string) => void;
    signal?: AbortSignal;
  } = {},
): Promise<TurnResult> {
  if (opts.tools?.length) {
    try {
      return await runTurn(cfg, messages, opts, true);
    } catch (err: any) {
      if (err instanceof ChatError && err.status === 400 && !opts.signal?.aborted) {
        return await runTurn(cfg, messages, opts, false);
      }
      throw err;
    }
  }
  return runTurn(cfg, messages, opts, true);
}

/** Minimal tool definition the wire needs (structurally ToolDef from agent.ts;
 *  a local shape keeps chat.ts dependency-free). */
export interface ToolDefLite {
  type: "function";
  function: { name: string; description: string; parameters: Record<string, any> };
}

async function runTurn(
  cfg: ChatConfig,
  messages: WireMessage[],
  opts: { tools?: ToolDefLite[]; onDelta?: (text: string) => void; signal?: AbortSignal },
  stream: boolean,
): Promise<TurnResult> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (cfg.apiKey) headers.Authorization = `Bearer ${cfg.apiKey}`;

  const body: Record<string, any> = { model: cfg.model, messages, stream };
  if (opts.tools?.length) body.tools = opts.tools;

  let resp: Response;
  try {
    resp = await fetch(chatEndpoint(cfg.baseUrl), {
      method: "POST",
      headers,
      signal: opts.signal,
      body: JSON.stringify(body),
    });
  } catch (err: any) {
    if (err?.name === "AbortError") throw err;
    throw new ChatError(
      `Could not reach ${cfg.baseUrl} — is the provider running? (${err?.message ?? err})`,
    );
  }

  if (!resp.ok) {
    let detail = await resp.text().catch(() => "");
    try {
      const parsed = JSON.parse(detail);
      detail = parsed?.error?.message ?? parsed?.detail ?? detail;
    } catch { /* plain text body */ }
    throw new ChatError(`Provider error ${resp.status}: ${String(detail).slice(0, 300)}`, resp.status);
  }

  const fragments: ToolCallDelta[] = [];
  let full = "";

  if (stream && resp.body) {
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    const feed = createSSEParser((payload) => {
      if (payload === "[DONE]") return;
      try {
        const evt = JSON.parse(payload);
        const delta = evt?.choices?.[0]?.delta ?? {};
        const text = delta?.content ?? evt?.choices?.[0]?.text ?? "";
        if (text) {
          full += text;
          opts.onDelta?.(text);
        }
        if (delta?.tool_calls?.length) fragments.push(...delta.tool_calls);
        // non-stream-shaped answer smuggled through SSE (some proxies)
        const whole = evt?.choices?.[0]?.message;
        if (whole?.tool_calls?.length) fragments.push(...whole.tool_calls);
      } catch {
        // ignore malformed keep-alive payloads
      }
    });
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      feed(decoder.decode(value, { stream: true }));
    }
  } else {
    const data = await resp.json().catch(() => null);
    const msg = data?.choices?.[0]?.message;
    full = msg?.content ?? "";
    if (full) opts.onDelta?.(full);
    if (msg?.tool_calls?.length) fragments.push(...msg.tool_calls);
  }

  return { text: full, toolCalls: assembleToolCalls(fragments) };
}
