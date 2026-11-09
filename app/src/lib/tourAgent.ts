/** tourAgent.ts — the agentic tour's OWN runner (owner order 2026-11-09:
 *  "The chat window still shows up. It should stay hidden, and the tour
 *  should show what the agent says at each step with a speech bubble and
 *  all other options for next/prev and asking ofc given").
 *
 *  What changed vs the first tour build: the ChatPanel no longer narrates.
 *  The tour bubble owns the whole conversation — the agent's narration
 *  streams INTO the bubble, the user asks from an input in the same bubble,
 *  and the floating chat window stays closed (and is not auto-opened) for
 *  the whole tour.
 *
 *  Law of this file:
 *  - The tour agent has EXACTLY one tool: navigate (read-only, tour-only).
 *    No write tool exists in the tour toolset, so no tour turn can move
 *    data even if the model hallucinates one — the executor answers
 *    "unknown tool" and the model corrects course.
 *  - Reuses the SAME streamAssistantTurn / executeTool / persona stack as
 *    the chat panel, so behavior and grounding stay identical.
 *  - History is a rolling wire (text bubbles + the current turn's tool
 *    traffic), capped so a long tour cannot blow the provider context.
 */
import type { AdminSchema, AppConfig } from "./types";
import {
  streamAssistantTurn,
  systemPrompt,
  buildSchemaPrompt,
  type ChatConfig,
  type WireMessage,
} from "./chat";
import {
  agentSystemAddendum,
  executeTool,
  navigateTool,
  toolResultMessage,
  tourGuideAddendum,
  type ToolCall,
  type ToolCtx,
  type ToolDef,
} from "./agent";
import { stepAgentTurn, type TourStep } from "./onboarding";

const MAX_ROUNDS = 4;
const HISTORY_CAP = 8;

export interface TourAgentDeps {
  /** The APP origin the navigate/data context runs against (effectiveConfig). */
  cfg: AppConfig;
  /** The AI PROVIDER settings the narration streams from. */
  aiCfg: ChatConfig;
  token: string | null;
  schema: AdminSchema | null;
  appName: string;
  /** App-start callback: streams each delta of the CURRENT assistant line. */
  onDelta: (text: string) => void;
  /** Called before a new assistant line starts (caller clears its buffer). */
  onTurnStart: () => void;
}

/** The tour toolset: drive the app, nothing else. */
export function tourTools(): ToolDef[] {
  return [navigateTool()];
}

export interface TourAgent {
  /** Narrate a tour stop (streams via deps callbacks). */
  narrate(step: TourStep): Promise<string>;
  /** Answer a free-text question mid-tour. */
  ask(text: string): Promise<string>;
  /** Abort the in-flight turn. */
  stop(): void;
  busy(): boolean;
}

export function createTourAgent(deps: TourAgentDeps): TourAgent {
  /** Rolling cross-turn memory: text bubbles only; tool traffic lives inside
   *  its own turn exactly like the chat panel's law. */
  let history: WireMessage[] = [];
  let busy = false;
  let abort: AbortController | null = null;

  const ctx: ToolCtx = {
    cfg: deps.cfg,
    token: deps.token,
    schema: deps.schema,
    // the tour drives the app through the same hash router the navigate
    // tool documents; read-only surface change, never data
    navigateTo: (path: string) => {
      window.location.hash = `#${path}`;
    },
  };

  const tools = tourTools();

  const wireFor = (userText: string): WireMessage[] => [
    {
      role: "system",
      content:
        systemPrompt(
          deps.appName,
          deps.schema ? buildSchemaPrompt(deps.schema) : "no schema loaded",
          "",
        ) + agentSystemAddendum() + tourGuideAddendum(),
    },
    ...history,
    { role: "user", content: userText },
  ];

  async function runTurn(userText: string): Promise<string> {
    if (busy) return "";
    const wire = wireFor(userText);
    busy = true;
    abort = new AbortController();
    let finalText = "";
    try {
      for (let round = 0; round < MAX_ROUNDS; round++) {
        deps.onTurnStart();
        const turn = await streamAssistantTurn(deps.aiCfg, wire,
          {
            tools,
            signal: abort.signal,
            onDelta: (delta) => {
              finalText += delta;
              deps.onDelta(delta);
            },
          },
        );
        if (!turn.toolCalls.length) {
          if (turn.text) history.push({ role: "assistant", content: turn.text });
          finalText = turn.text || finalText;
          return finalText;
        }
        if (turn.text) history.push({ role: "assistant", content: turn.text });
        wire.push({ role: "assistant", content: turn.text, tool_calls: turn.toolCalls.map(toWireCall) });
        for (const call of turn.toolCalls) {
          // HARD GUARD: the tour toolset is navigate-only. executeTool knows
          // the full write catalog, and the tour bubble has NO Confirm cards,
          // so a hallucinated write must be refused HERE — prompt-level
          // tool choice alone is not a gate.
          const res =
            call.name === "navigate"
              ? await executeTool(call, ctx)
              : { ok: false, result: { error: `tool "${call.name}" is not available during the tour (navigate only)` } };
          wire.push(toolResultMessage(call, res));
        }
      }
      return finalText;
    } finally {
      history = history.slice(-HISTORY_CAP);
      busy = false;
      abort = null;
    }
  }

  const toWireCall = (c: ToolCall) => ({
    id: c.id,
    type: "function" as const,
    function: { name: c.name, arguments: JSON.stringify(c.args) },
  });

  return {
    narrate(step: TourStep) {
      return runTurn(stepAgentTurn(step, deps.appName));
    },
    ask(text: string) {
      return runTurn(text);
    },
    stop() {
      abort?.abort();
    },
    busy() {
      return busy;
    },
  };
}

/** Provider readiness for the tour's in-bubble picker (owner order
 *  2026-11-09: "it should still let users choose the AI provider with kilo
 *  pre selected, and keyless ones suggested when choosing"). Pure helper —
 *  testable without a store. */
export function isProviderConfigured(baseUrl: string, model: string): boolean {
  return Boolean(baseUrl.trim() && model.trim());
}
