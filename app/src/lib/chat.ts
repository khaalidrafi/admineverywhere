/** OpenAI-compatible chat with SSE streaming (works with OpenAI, Groq,
 *  Ollama, Mistral, LM Studio — anything speaking /chat/completions).
 *
 *  No provider SDK: raw fetch + SSE. Keeps the bundle tiny and universal.
 */
import type { AdminSchema, AppConfig } from "./types";

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
${lines.join("
")}`;
}

/** Build the schema-aware system prompt. */
export function systemPrompt(appName: string, modelLines: string): string {
  return [
    `You are the assistant inside the ${appName} admin dashboard.`,
    "You help the operator understand and manage their data.",
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

export class ChatError extends Error {}
