/** agent.ts — the AI assistant's hands. The panel could only ever CHAT;
 *  this module turns the same OpenAI-compatible provider into an operator
 *  that can actually run the admin: list, inspect, create, update, delete,
 *  transition and read the audit log — through the SAME api.ts calls and the
 *  SAME operator token the rest of the app uses.
 *
 *  Law of this file:
 *  - The agent never speaks to the backend directly. Every action goes
 *    through api.ts, so auth headers, error normalization and secret
 *    redaction behave identically for a human click and an agent call.
 *  - The server stays the gate. The agent inherits exactly the operator's
 *    RBAC — it cannot out-privilege the human who is logged in, because it
 *    IS that human's session.
 *  - Every write is destructive-gated in the UI (isDestructive): the panel
 *    renders a Confirm/Deny card and executes only on approval. Reads run
 *    without asking.
 *  - Paths are never guessed: model paths come from the live OpenAPI schema,
 *    the same evidence law as the rest of the client.
 */
import type { AdminSchema, AppConfig, ModelSpec } from "./types";
import {
  createRecord,
  deleteRecord,
  fetchAudit,
  listRecords,
  patchRecord,
  retrieveRecord,
  transitionRecord,
} from "./api";
import { findAuditModel } from "./rbac";

/* ---- wire types (OpenAI tool-calling shape) ---- */

export interface ToolDef {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: {
      type: "object";
      properties: Record<string, any>;
      required?: string[];
    };
  };
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
}

export interface ToolResult {
  ok: boolean;
  result: any;
}

export interface ToolCtx {
  cfg: AppConfig;
  token: string | null;
  schema: AdminSchema | null;
  /** Agentic onboarding only (owner order 2026-11-08): lets the agent drive
   *  the app by navigating the shell (hash router). Read-only, never moves
   *  data — injected by the panel ONLY while the tour is active. */
  navigateTo?: (path: string) => void;
}

/* ---- tool catalog ---- */

const PAGE_CAP = 50;
const PAGE_MAX = 20;

/** The generic, schema-driven toolset. One set covers every model the live
 *  OpenAPI document advertises — the model id is a parameter, not per-model
 *  tool spam that would blow the provider context on big schemas. */
export function buildAgentTools(schema: AdminSchema | null): ToolDef[] {
  const hasModels = Boolean(schema?.models?.length);
  const modelHint = hasModels
    ? "Use EXACT model ids from the system prompt's model list."
    : "The schema is not loaded yet; if the operator asks about data, say the backend schema is unavailable.";
  return [
    {
      type: "function",
      function: {
        name: "list_records",
        description: `List rows of an admin model with optional server-side search. ${modelHint}`,
        parameters: {
          type: "object",
          properties: {
            model: { type: "string", description: "Model id, e.g. 'products'" },
            search: { type: "string", description: "Server-side search text" },
            page: { type: "number", description: "1-based page number (default 1)" },
            page_size: { type: "number", description: `Rows per page, max ${PAGE_CAP}` },
          },
          required: ["model"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "get_record",
        description: `Fetch one row by id with every field. ${modelHint}`,
        parameters: {
          type: "object",
          properties: {
            model: { type: "string", description: "Model id" },
            id: { type: "string", description: "Record primary key" },
          },
          required: ["model", "id"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "create_record",
        description: `Create a new row. Only fields the schema lists, none that are readOnly. ${modelHint}`,
        parameters: {
          type: "object",
          properties: {
            model: { type: "string", description: "Model id" },
            data: { type: "object", description: "Field:value map for the new row" },
          },
          required: ["model", "data"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "update_record",
        description: `Patch selected fields of one row — send only the fields that change. ${modelHint}`,
        parameters: {
          type: "object",
          properties: {
            model: { type: "string", description: "Model id" },
            id: { type: "string", description: "Record primary key" },
            data: { type: "object", description: "Field:value map of the changes" },
          },
          required: ["model", "id", "data"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "delete_record",
        description: `Permanently delete one row. Destructive — the operator confirms before it runs. ${modelHint}`,
        parameters: {
          type: "object",
          properties: {
            model: { type: "string", description: "Model id" },
            id: { type: "string", description: "Record primary key" },
          },
          required: ["model", "id"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "transition_record",
        description: `Move a row through its lifecycle (e.g. an order to 'paid'). Only models whose schema documents a transition endpoint accept it. ${modelHint}`,
        parameters: {
          type: "object",
          properties: {
            model: { type: "string", description: "Model id" },
            id: { type: "string", description: "Record primary key" },
            to_status: { type: "string", description: "Target status value" },
          },
          required: ["model", "id", "to_status"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "read_audit",
        description: "Read the append-only audit log (newest first), optionally filtered by object type and record id.",
        parameters: {
          type: "object",
          properties: {
            object_type: { type: "string", description: "Model singular name, e.g. 'product'" },
            object_id: { type: "string", description: "Record primary key" },
            page: { type: "number", description: "1-based page number (default 1)" },
          },
          required: [],
        },
      },
    },
  ];
}

/** Agentic-onboarding extra (owner order 2026-11-08): the tour-guide agent
 *  can DRIVE the app — open the module it is narrating. Added on top of
 *  buildAgentTools() only while a tour runs; the executor accepts it only
 *  when the panel injected navigateTo into the context. Navigation is a
 *  read-only surface change, so it is classified non-destructive. */
export function navigateTool(): ToolDef {
  return {
    type: "function",
    function: {
      name: "navigate",
      description:
        "Open a screen of the admin app by route path (hash routing). Use it to SHOW the feature you are narrating, e.g. '/m/orders' for a model table, '/widget-studio' or '/activity'.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Route path starting with '/', e.g. '/m/orders'" },
        },
        required: ["path"],
      },
    },
  };
}

/* ---- classification + summaries ---- */

const READ_TOOLS = new Set(["list_records", "get_record", "read_audit", "navigate"]);

/** Writes always wait for the operator's Confirm; reads never do. */
export function isDestructive(name: string): boolean {
  return !READ_TOOLS.has(name);
}

/** One human line per tool call for the confirmation card. */
export function humanSummary(call: ToolCall, schema: AdminSchema | null): string {
  const model = resolveModel(schema, String(call.args?.model ?? ""));
  const label = model ? model.name : String(call.args?.model ?? "?");
  const id = call.args?.id !== undefined ? ` #${call.args.id}` : "";
  switch (call.name) {
    case "list_records":
      return `List ${label}${call.args?.search ? ` matching “${call.args.search}”` : ""}`;
    case "get_record":
      return `Show ${label}${id}`;
    case "create_record":
      return `Create ${label}`;
    case "update_record":
      return `Update ${label}${id}`;
    case "delete_record":
      return `Delete ${label}${id}`;
    case "transition_record":
      return `Move ${label}${id} to “${call.args?.to_status ?? "?"}”`;
    case "read_audit":
      return `Read audit log${call.args?.object_type ? ` for ${call.args.object_type}` : ""}`;
    case "navigate":
      return `Open screen ${call.args?.path ?? "?"}`;
    default:
      return call.name;
  }
}

/* ---- model resolution + data hygiene ---- */

/** Resolve a model by id, singular or display name, case-insensitively —
 *  the provider sometimes paraphrases the id it was told to use verbatim. */
export function resolveModel(schema: AdminSchema | null, modelId: string): ModelSpec | null {
  if (!schema?.models?.length || !modelId) return null;
  const needle = modelId.trim().toLowerCase();
  return (
    schema.models.find((m) => m.id.toLowerCase() === needle) ??
    schema.models.find((m) => m.singular.toLowerCase() === needle) ??
    schema.models.find((m) => m.name.toLowerCase() === needle) ??
    null
  );
}

/** Strip readOnly and schema-unknown fields from a write payload, so a
 *  hallucinated field never reaches the server and `id` never travels as
 *  data. Returns the cleaned payload plus what was dropped (for the tool
 *  answer, so the model can correct itself on the next round). */
export function sanitizeWriteData(
  model: ModelSpec,
  data: unknown,
): { clean: Record<string, any>; dropped: string[] } {
  const clean: Record<string, any> = {};
  const dropped: string[] = [];
  if (data && typeof data === "object" && !Array.isArray(data)) {
    for (const [k, v] of Object.entries(data as Record<string, any>)) {
      const field = model.byName?.[k];
      if (!field) {
        dropped.push(k);
        continue;
      }
      if (field.readOnly) {
        dropped.push(k);
        continue;
      }
      clean[k] = v;
    }
  }
  return { clean, dropped };
}

function fail(message: string): ToolResult {
  return { ok: false, result: { error: message } };
}

/* ---- executor ---- */

/** Run one tool call against the backend. Never throws: every failure —
 *  unknown model, bad args, API error — comes back as an {error} payload the
 *  loop feeds to the provider as the tool result, so it can retry or explain. */
export async function executeTool(call: ToolCall, ctx: ToolCtx): Promise<ToolResult> {
  const { cfg, token, schema } = ctx;
  if (!cfg?.apiUrl) return fail("no backend is configured");

  try {
    switch (call.name) {
      case "list_records": {
        const model = resolveModel(schema, String(call.args?.model ?? ""));
        if (!model) return fail(`unknown model "${call.args?.model}"`);
        const pageSize = Math.min(Number(call.args?.page_size) || 25, PAGE_CAP);
        const page = Math.min(Number(call.args?.page) || 1, PAGE_MAX);
        const data = await listRecords(cfg, token, model, {
          page,
          pageSize,
          search: call.args?.search ? String(call.args.search) : undefined,
        });
        return {
          ok: true,
          result: {
            model: model.id,
            count: data.count,
            page,
            rows: data.results.map((r) => ({
              id: r.id,
              label: r[model.labelField] ?? null,
              row: r,
            })),
          },
        };
      }

      case "get_record": {
        const model = resolveModel(schema, String(call.args?.model ?? ""));
        if (!model) return fail(`unknown model "${call.args?.model}"`);
        if (call.args?.id === undefined || call.args?.id === null || call.args?.id === "")
          return fail("missing record id");
        const row = await retrieveRecord(cfg, token, model, call.args.id);
        return { ok: true, result: { model: model.id, record: row } };
      }

      case "create_record": {
        const model = resolveModel(schema, String(call.args?.model ?? ""));
        if (!model) return fail(`unknown model "${call.args?.model}"`);
        const { clean, dropped } = sanitizeWriteData(model, call.args?.data);
        if (!Object.keys(clean).length) return fail("no writable fields in data");
        const row = await createRecord(cfg, token, model, clean);
        return { ok: true, result: { model: model.id, created: row, droppedFields: dropped } };
      }

      case "update_record": {
        const model = resolveModel(schema, String(call.args?.model ?? ""));
        if (!model) return fail(`unknown model "${call.args?.model}"`);
        if (call.args?.id === undefined || call.args?.id === null || call.args?.id === "")
          return fail("missing record id");
        const { clean, dropped } = sanitizeWriteData(model, call.args?.data);
        if (!Object.keys(clean).length) return fail("no writable fields in data");
        const row = await patchRecord(cfg, token, model, call.args.id, clean);
        return { ok: true, result: { model: model.id, updated: row, droppedFields: dropped } };
      }

      case "delete_record": {
        const model = resolveModel(schema, String(call.args?.model ?? ""));
        if (!model) return fail(`unknown model "${call.args?.model}"`);
        if (call.args?.id === undefined || call.args?.id === null || call.args?.id === "")
          return fail("missing record id");
        await deleteRecord(cfg, token, model, call.args.id);
        return { ok: true, result: { model: model.id, deleted: String(call.args.id) } };
      }

      case "transition_record": {
        const model = resolveModel(schema, String(call.args?.model ?? ""));
        if (!model) return fail(`unknown model "${call.args?.model}"`);
        if (call.args?.id === undefined || call.args?.id === null || call.args?.id === "")
          return fail("missing record id");
        if (!call.args?.to_status) return fail("missing to_status");
        const row = await transitionRecord(cfg, token, model, call.args.id, String(call.args.to_status));
        return { ok: true, result: { model: model.id, transitioned: row } };
      }

      case "read_audit": {
        const audit = findAuditModel(schema);
        if (!audit) return fail("the API documents no audit log endpoint");
        const data = await fetchAudit(cfg, token, {
          path: audit.listPath,
          objectType: call.args?.object_type ? String(call.args.object_type) : undefined,
          objectId: call.args?.object_id !== undefined ? String(call.args.object_id) : undefined,
          page: Math.min(Number(call.args?.page) || 1, PAGE_MAX),
        });
        return { ok: true, result: { count: data.count, entries: data.results } };
      }

      case "navigate": {
        if (!ctx.navigateTo) return fail("navigation is only available during the guided tour");
        const path = String(call.args?.path ?? "").trim();
        if (!path.startsWith("/")) return fail("path must start with '/'");
        ctx.navigateTo(path);
        return { ok: true, result: { navigatedTo: path } };
      }

      default:
        return fail(`unknown tool "${call.name}"`);
    }
  } catch (err: any) {
    let detail = err?.detail ?? err?.message ?? String(err);
    if (typeof detail !== "string") {
      detail = JSON.stringify(detail);
    }
    if (!detail || detail === "{}" || detail === "[]") detail = err?.message ?? "request failed";
    return fail(detail);
  }
}

/** Tool result → provider wire message. */
export function toolResultMessage(call: ToolCall, res: ToolResult): any {
  return {
    role: "tool",
    tool_call_id: call.id,
    content: JSON.stringify(res.ok ? res.result : { error: res.result?.error ?? "failed" }),
  };
}

/* ---- system-prompt addendum ---- */

/** Appended to the schema-aware base prompt whenever tools are active. */
export function agentSystemAddendum(): string {
  return [
    "",
    "You CAN act on the data through tools. Rules:",
    "- For any question about rows, call list_records or get_record — never invent rows, ids or numbers.",
    "- For any change (create/update/delete/transition) call the matching tool in the SAME turn; the UI asks the operator to confirm before anything destructive runs.",
    "- Use only model ids, field names and status values that appear in the model list above. If a value is unknown, look it up first.",
    "- After an action, report what happened with the record id from the tool result. If a tool returns {error}, say so and fix the request before retrying once.",
    "- Batch independent reads; never batch a write with anything that depends on it.",
  ].join("\n");
}

/** Tour-guide persona for the agentic onboarding (owner order 2026-11-08:
 *  "the AI Agent will drive the app, show its features, and the user can
 *  chat with the AI while onboarding"). Appended ON TOP of the standard
 *  addendum while the guided tour is active. */
export function tourGuideAddendum(): string {
  return [
    "",
    "TOUR GUIDE MODE: you are walking the operator through this admin app, stop by stop.",
    "- You can open screens with the navigate tool — do it when you narrate a feature, seeing beats telling.",
    "- Keep each narration to one short paragraph, then hand the turn back with one question at most.",
    "- Reads (list/get) are free to run as demonstrations; still never write without the operator asking.",
  ].join("\n");
}
