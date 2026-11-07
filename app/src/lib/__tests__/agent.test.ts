/** agent.ts tests — the assistant's hands, graded at every joint.
 *
 *  The chat panel used to be talk-only; agent.ts is the "perform any admin
 *  action" half (owner order). These tests pin: the toolset shape, model
 *  resolution, write-data hygiene (no readOnly, no hallucinated fields),
 *  destructive classification, human summaries, the executor's URL/method
 *  behavior against a stubbed fetch, and the wire layer's streamed tool-call
 *  assembly including the unstreamed-400 fallback.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  agentSystemAddendum,
  buildAgentTools,
  executeTool,
  humanSummary,
  isDestructive,
  resolveModel,
  sanitizeWriteData,
  toolResultMessage,
  type ToolCall,
} from "../agent";
import {
  assembleToolCalls,
  streamAssistantTurn,
  type ToolCallDelta,
} from "../chat";
import { normalizeOpenAPI } from "../openapi";
import type { AdminSchema, AppConfig } from "../types";
import fixture from "./fixtures/openapi.json";

const schema: AdminSchema = normalizeOpenAPI(fixture);
const cfg: AppConfig = { apiUrl: "https://x.test", authPath: "/api/auth/token/", schemaPath: "/api/schema/" };
const ctx = { cfg, token: "op-token", schema };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/* ---- toolset ---- */

describe("buildAgentTools", () => {
  it("exposes the seven schema-driven tools", () => {
    const tools = buildAgentTools(schema);
    expect(tools.map((t) => t.function.name)).toEqual([
      "list_records",
      "get_record",
      "create_record",
      "update_record",
      "delete_record",
      "transition_record",
      "read_audit",
    ]);
    for (const t of tools) {
      expect(t.type).toBe("function");
      expect(t.function.parameters.type).toBe("object");
    }
  });

  it("works with a null schema (prompt says schema unavailable)", () => {
    const tools = buildAgentTools(null);
    expect(tools).toHaveLength(7);
    expect(tools[0].function.description).toContain("schema is not loaded");
  });

  it("the addendum orders lookups before writes and id-citing after", () => {
    const add = agentSystemAddendum();
    expect(add).toContain("never invent rows");
    expect(add).toContain("confirm");
    expect(add).toContain("record id");
  });
});

/* ---- resolution + hygiene ---- */

describe("resolveModel", () => {
  it("matches id, singular and display name case-insensitively", () => {
    const byId = resolveModel(schema, "orders");
    expect(byId?.id).toBe("orders");
    expect(resolveModel(schema, "Orders")?.id).toBe("orders");
    expect(resolveModel(schema, "ORDER")?.id).toBe("orders");
  });

  it("returns null for unknown or empty ids", () => {
    expect(resolveModel(schema, "ufo")).toBeNull();
    expect(resolveModel(schema, "")).toBeNull();
    expect(resolveModel(null, "orders")).toBeNull();
  });
});

describe("sanitizeWriteData", () => {
  const model = resolveModel(schema, "products")!;

  it("drops readOnly and schema-unknown fields, keeps writable ones", () => {
    const { clean, dropped } = sanitizeWriteData(model, {
      name: "Seven-grain chatu",
      price: 120,
      id: 999, // readOnly
      made_up_field: true, // hallucinated
    });
    expect(clean).toEqual({ name: "Seven-grain chatu", price: 120 });
    expect(dropped.sort()).toEqual(["id", "made_up_field"]);
  });

  it("never emits fields for non-object data", () => {
    expect(sanitizeWriteData(model, "nuke everything").clean).toEqual({});
    expect(sanitizeWriteData(model, ["a", "b"]).clean).toEqual({});
  });
});

describe("isDestructive", () => {
  it("reads run free, every write waits for Confirm", () => {
    expect(isDestructive("list_records")).toBe(false);
    expect(isDestructive("get_record")).toBe(false);
    expect(isDestructive("read_audit")).toBe(false);
    expect(isDestructive("create_record")).toBe(true);
    expect(isDestructive("update_record")).toBe(true);
    expect(isDestructive("delete_record")).toBe(true);
    expect(isDestructive("transition_record")).toBe(true);
  });
});

describe("humanSummary", () => {
  const call = (name: string, args: any): ToolCall => ({ id: "t1", name, args });

  it("names model and record for each verb", () => {
    expect(humanSummary(call("delete_record", { model: "orders", id: 7 }), schema)).toContain("Delete Order #7");
    expect(humanSummary(call("update_record", { model: "orders", id: 7, data: { status: "paid" } }), schema)).toContain(
      "Update Order #7",
    );
    expect(humanSummary(call("transition_record", { model: "orders", id: 7, to_status: "paid" }), schema)).toContain(
      "paid",
    );
    expect(humanSummary(call("list_records", { model: "products", search: "tea" }), schema)).toContain("tea");
    expect(humanSummary(call("read_audit", { object_type: "product" }), schema)).toContain("audit");
  });

  it("falls back to the raw model id when the schema lacks it", () => {
    expect(humanSummary(call("delete_record", { model: "ufo", id: 1 }), schema)).toContain("ufo");
  });
});

/* ---- executor ---- */

describe("executeTool", () => {
  function jsonFetch(responder: (url: string, init: RequestInit) => any) {
    const mock = vi.fn(async (url: string, init: RequestInit = {} as RequestInit) => {
      const handled = responder(url, init);
      if (handled) return handled;
      return { ok: true, status: 200, text: async () => "{}" };
    });
    vi.stubGlobal("fetch", mock);
    return mock;
  }

  it("list_records hits the schema listPath with capped pagination + search", async () => {
    const mock = jsonFetch((_url) => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ count: 1, results: [{ id: 3, name: "Tea" }] }),
    }));
    const res = await executeTool(
      { id: "c1", name: "list_records", args: { model: "products", search: "tea", page: 2, page_size: 500 } },
      ctx,
    );
    expect(res.ok).toBe(true);
    const url = new URL(mock.mock.calls[0][0] as string);
    expect(url.origin + url.pathname).toBe("https://x.test/api/products/");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("50"); // cap applied, 500 refused
    expect(url.searchParams.get("search")).toBe("tea");
    expect((res.result.rows[0] as any).row).toEqual({ id: 3, name: "Tea" });
    expect((mock.mock.calls[0][1] as RequestInit).headers).toMatchObject({ Authorization: "Token op-token" });
  });

  it("create_record POSTs sanitized data only", async () => {
    const mock = jsonFetch((_url) => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ id: 11, name: "New" }),
    }));
    const res = await executeTool(
      { id: "c2", name: "create_record", args: { model: "products", data: { name: "New", price: 5, id: 1, junk: 2 } } },
      ctx,
    );
    expect(res.ok).toBe(true);
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://x.test/api/products/");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ name: "New", price: 5 });
    expect((res.result as any).droppedFields.sort()).toEqual(["id", "junk"]);
  });

  it("update_record PATCHes the detail path", async () => {
    const mock = jsonFetch(() => ({ ok: true, status: 200, text: async () => JSON.stringify({ id: 7 }) }));
    const res = await executeTool(
      { id: "c3", name: "update_record", args: { model: "orders", id: 7, data: { status: "paid" } } },
      ctx,
    );
    expect(res.ok).toBe(true);
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://x.test/api/orders/7/");
    expect(init.method).toBe("PATCH");
  });

  it("delete_record issues DELETE and answers 204", async () => {
    const mock = jsonFetch(() => ({ ok: true, status: 204, text: async () => "" }));
    const res = await executeTool({ id: "c4", name: "delete_record", args: { model: "orders", id: 7 } }, ctx);
    expect(res.ok).toBe(true);
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://x.test/api/orders/7/");
    expect(init.method).toBe("DELETE");
  });

  it("transition_record uses the schema-discovered transition endpoint", async () => {
    const mock = jsonFetch(() => ({ ok: true, status: 200, text: async () => JSON.stringify({ id: 7, status: "paid" }) }));
    const res = await executeTool(
      { id: "c5", name: "transition_record", args: { model: "orders", id: 7, to_status: "paid" } },
      ctx,
    );
    expect(res.ok).toBe(true);
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://x.test/api/orders/7/transition/");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ transition: "paid" });
  });

  it("refuses to guess a transition endpoint the schema does not document", async () => {
    const mock = jsonFetch(() => null);
    const res = await executeTool(
      { id: "c6", name: "transition_record", args: { model: "products", id: 1, to_status: "active" } },
      ctx,
    );
    expect(res.ok).toBe(false);
    expect((res.result as any).error).toContain("documents no lifecycle transition endpoint");
    expect(mock).not.toHaveBeenCalled();
  });

  it("read_audit binds the schema-discovered audit path, never a guessed one", async () => {
    const mock = jsonFetch(() => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ count: 1, results: [{ id: 1, action: "flag" }] }),
    }));
    const res = await executeTool({ id: "c7", name: "read_audit", args: { object_type: "order" } }, ctx);
    expect(res.ok).toBe(true);
    expect(mock.mock.calls[0][0]).toContain("/api/audit/");
  });

  it("every failure mode is an {error} answer, never a throw", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("socket exploded");
      }),
    );
    const net = await executeTool({ id: "c8", name: "list_records", args: { model: "orders" } }, ctx);
    expect(net.ok).toBe(false);
    expect((net.result as any).error).toContain("Cannot reach backend");

    const unknown = await executeTool({ id: "c9", name: "delete_record", args: { model: "ufo", id: 1 } }, ctx);
    expect(unknown.ok).toBe(false);
    expect((unknown.result as any).error).toContain("unknown model");

    const noId = await executeTool({ id: "c10", name: "get_record", args: { model: "orders" } }, ctx);
    expect(noId.ok).toBe(false);
    expect((noId.result as any).error).toContain("missing record id");

    const noData = await executeTool(
      { id: "c11", name: "create_record", args: { model: "orders", data: { id: 1 } } },
      ctx,
    );
    expect(noData.ok).toBe(false);

    const noTool = await executeTool({ id: "c12", name: "launch_missiles", args: {} }, ctx);
    expect(noTool.ok).toBe(false);
    expect((noTool.result as any).error).toContain("unknown tool");
  });

  it("a 400 validation error surfaces its detail for the next round", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 400,
        text: async () => JSON.stringify({ price: ["A valid number is required."] }),
      })),
    );
    const res = await executeTool(
      { id: "c13", name: "create_record", args: { model: "products", data: { name: "x", price: "cheap" } } },
      ctx,
    );
    expect(res.ok).toBe(false);
    expect(JSON.stringify(res.result)).toContain("A valid number is required.");
  });
});

describe("toolResultMessage", () => {
  it("wraps results as role:tool messages bound to the call id", () => {
    const call: ToolCall = { id: "abc", name: "list_records", args: {} };
    expect(toolResultMessage(call, { ok: true, result: { rows: [] } })).toEqual({
      role: "tool",
      tool_call_id: "abc",
      content: '{"rows":[]}',
    });
    expect(JSON.parse(toolResultMessage(call, { ok: false, result: { error: "boom" } }).content)).toEqual({
      error: "boom",
    });
  });
});

/* ---- wire layer ---- */

describe("assembleToolCalls", () => {
  it("reassembles fragments split across deltas, by index, concatenating arguments", () => {
    const fragments: ToolCallDelta[] = [
      { index: 0, id: "call_a", type: "function", function: { name: "update_record", arguments: '{"model":"orders"' } },
      { index: 0, function: { arguments: ',"id":7,"data":{"status":"paid"}}' } },
      { index: 1, id: "call_b", type: "function", function: { name: "list_records", arguments: '{"model":' } },
      { index: 1, function: { arguments: '"products"}' } },
    ];
    expect(assembleToolCalls(fragments)).toEqual([
      { id: "call_a", name: "update_record", args: { model: "orders", id: 7, data: { status: "paid" } } },
      { id: "call_b", name: "list_records", args: { model: "products" } },
    ]);
  });

  it("falls back to index-derived ids and flags unparsable arguments", () => {
    const calls = assembleToolCalls([{ function: { name: "x", arguments: "{broken" } }]);
    expect(calls[0].id).toBe("call_0");
    expect(calls[0].args).toEqual({ _unparsed: "{broken" });
  });
});

function sseResponse(events: string[]) {
  const encoder = new TextEncoder();
  let sent = false;
  return {
    ok: true,
    status: 200,
    body: {
      getReader() {
        return {
          read: async () => {
            if (sent) return { done: true, value: undefined };
            sent = true;
            return { done: false, value: encoder.encode(events.join("")) };
          },
        };
      },
    },
    text: async () => "",
  };
}

describe("streamAssistantTurn with tools", () => {
  const messages = [
    { role: "system", content: "sys" },
    { role: "user", content: "mark order 7 paid" },
  ];
  const tools = buildAgentTools(schema);

  it("streams text deltas AND assembles the tool call from streamed fragments", async () => {
    const sse = sseResponse([
      `data: ${JSON.stringify({ choices: [{ delta: { content: "On it." } }] })}\n\n`,
      `data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, id: "tc1", type: "function", function: { name: "transition_record", arguments: '{"model":' } }] } }] })}\n\n`,
      `data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, function: { arguments: '"orders","id":"7","to_status":"paid"}' } }] } }] })}\n\n`,
      "data: [DONE]\n\n",
    ]);
    const mock = vi.fn(async (_url: string, _init?: RequestInit) => sse);
    vi.stubGlobal("fetch", mock);

    const deltas: string[] = [];
    const turn = await streamAssistantTurn(
      { baseUrl: "http://p.test/v1", apiKey: "k", model: "m" },
      messages as any,
      { tools, onDelta: (t) => deltas.push(t) },
    );

    expect(deltas).toEqual(["On it."]);
    expect(turn.text).toBe("On it.");
    expect(turn.toolCalls).toEqual([
      { id: "tc1", name: "transition_record", args: { model: "orders", id: "7", to_status: "paid" } },
    ]);
    const body = JSON.parse((mock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.tools).toHaveLength(7);
    expect(body.stream).toBe(true);
  });

  it("retries non-streaming once when the provider 400s streamed tool calls", async () => {
    const mock = vi.fn(async (_url: string, init: RequestInit) => {
      if (JSON.parse(init.body as string).stream) {
        return {
          ok: false,
          status: 400,
          text: async () => JSON.stringify({ error: { message: "tools are not supported with stream=true" } }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          choices: [
            {
              message: {
                content: "",
                tool_calls: [
                  { id: "tc9", type: "function", function: { name: "list_records", arguments: '{"model":"orders"}' } },
                ],
              },
            },
          ],
        }),
      };
    });
    vi.stubGlobal("fetch", mock);

    const turn = await streamAssistantTurn(
      { baseUrl: "http://p.test/v1", apiKey: "k", model: "m" },
      messages as any,
      { tools },
    );
    expect(turn.text).toBe("");
    expect(turn.toolCalls).toEqual([{ id: "tc9", name: "list_records", args: { model: "orders" } }]);
    const secondBody = JSON.parse((mock.mock.calls[1][1] as RequestInit).body as string);
    expect(secondBody.stream).toBe(false);
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("passes tool results through the wire untouched", async () => {
    const mock = vi.fn(async (_url?: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ choices: [{ message: { content: "done" } }] }),
    }));
    vi.stubGlobal("fetch", mock);
    const withToolResult = [
      ...messages,
      { role: "assistant", content: "", tool_calls: [{ id: "t1", type: "function", function: { name: "list_records", arguments: "{}" } }] },
      { role: "tool", tool_call_id: "t1", content: '{"rows":[]}' },
    ] as any;
    const turn = await streamAssistantTurn({ baseUrl: "http://p.test/v1", apiKey: "", model: "m" }, withToolResult, {
      tools,
    });
    expect(turn.text).toBe("done");
    const body = JSON.parse((mock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.messages.at(-1).tool_call_id).toBe("t1");
  });
});
