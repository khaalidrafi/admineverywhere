#!/usr/bin/env node
/** Mock OpenAI-compatible server for local dev/demo (no deps, node http).

Endpoints:
  GET  /v1/models
  POST /v1/chat/completions   (stream: true -> SSE deltas)

Run: node scripts/mock_openai.js  (port 11435)
Point the chat panel Base URL at http://localhost:11435/v1
*/
const http = require("http");

const PORT = 11435;

const MODELS = [
  { id: "mock-gpt-4o-mini", object: "model" },
  { id: "mock-llama-3.2", object: "model" },
];

function replyText(res, status, body) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  });
  res.end(JSON.stringify(body));
}

function replyFor(messages) {
  const last = [...messages].reverse().find((m) => m.role === "user")?.content ?? "";
  const lower = last.toLowerCase();
  if (lower.includes("model") || lower.includes("field")) {
    return (
      "Your backend exposes 4 models: Category, Customer, Order and Product.\n\n" +
      "Order is the one with an enum status (pending / paid / shipped / refunded) " +
      "and FKs to Customer and Product. Product carries name, description, price " +
      "(decimal), stock, is_active, launch_date and a category FK."
    );
  }
  if (lower.includes("price") || lower.includes("product")) {
    return "Products carry a decimal price with 2 decimal places and an integer stock count. The price field is required, along with name and category.";
  }
  return (
    "I'm the mock provider — I stream like the real thing so you can feel the UX. " +
    `You said: "${last.slice(0, 120)}". Connect OpenAI, Groq or Ollama for real answers.`
  );
}

const server = http.createServer((req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    });
    return res.end();
  }

  const url = req.url ?? "";

  if (req.method === "GET" && url.startsWith("/v1/models")) {
    return replyText(res, 200, { object: "list", data: MODELS });
  }

  if (req.method === "POST" && url.startsWith("/v1/chat/completions")) {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      let payload = {};
      try { payload = JSON.parse(body); } catch { /* ignore */ }

      if (!payload.model) {
        return replyText(res, 400, { error: { message: "missing model" } });
      }

      const answer = replyFor(payload.messages ?? []);
      const created = Math.floor(Date.now() / 1000);
      const id = "chatcmpl-mock-" + created;

      if (!payload.stream) {
        return replyText(res, 200, {
          id, object: "chat.completion", created,
          model: payload.model,
          choices: [{ index: 0, message: { role: "assistant", content: answer }, finish_reason: "stop" }],
        });
      }

      // SSE stream: split the answer into word chunks for a live feel
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
      });

      const words = answer.split(/(\s+)/);
      let i = 0;
      const timer = setInterval(() => {
        if (i >= words.length) {
          clearInterval(timer);
          res.write("data: [DONE]\n\n");
          return res.end();
        }
        const chunk = words.slice(i, i + 2).join(""); // ~2 tokens per tick
        i += 2;
        const evt = {
          id, object: "chat.completion.chunk", created, model: payload.model,
          choices: [{ index: 0, delta: { content: chunk }, finish_reason: null }],
        };
        res.write(`data: ${JSON.stringify(evt)}\n\n`);
      }, 45);
      res.on("close", () => clearInterval(timer)); // client disconnected
    });
    return;
  }

  replyText(res, 404, { error: { message: `no route: ${req.method} ${url}` } });
});

server.listen(PORT, () => {
  console.log(`mock OpenAI-compatible server on http://localhost:${PORT}/v1`);
  console.log("chat panel Base URL -> http://localhost:11434-style: http://localhost:11435/v1");
});
