/** tourAgent tests — the tour's own runner (owner order 2026-11-09: the
 *  chat window stays hidden during the tour; the speech bubble carries the
 *  conversation).
 *
 *  Pinned here without a live provider:
 *  - the tour toolset is EXACTLY the navigate tool (no write tool can ever
 *    ride a tour turn),
 *  - provider-readiness helper (the in-bubble picker's gate),
 *  - the turn loop streams through the injected callbacks, feeds tool calls
 *    through executeTool, and grows the rolling history with text turns.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

// mock the wire BEFORE the module under test imports it
vi.mock("../chat", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../chat")>();
  return {
    ...actual,
    streamAssistantTurn: vi.fn(),
  };
});

import { streamAssistantTurn } from "../chat";
import { AGENT_IDENTITY } from "../agent";
import { createTourAgent, isProviderConfigured, tourTools } from "../tourAgent";
import type { TourStep } from "../onboarding";

const mockedStream = vi.mocked(streamAssistantTurn);

const CFG = { apiUrl: "https://api.example.com", authPath: "/a", schemaPath: "/s" };
const AI = { baseUrl: "http://provider.test/v1", apiKey: "k", model: "m-1" };

const STEP: TourStep = { id: "sidebar", title: "Sidebar", body: "Your modules.", agentPrompt: "Point at the sidebar." };

function deps(over: Partial<Parameters<typeof createTourAgent>[0]> = {}) {
  return {
    cfg: CFG,
    aiCfg: AI,
    token: null,
    schema: null,
    appName: "Freshorama Admin",
    onDelta: vi.fn(),
    onTurnStart: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  mockedStream.mockReset();
  window.location.hash = "";
});

describe("tour toolset", () => {
  it("is EXACTLY the navigate tool — no write tool can ride a tour turn", () => {
    expect(tourTools().map((t) => t.function.name)).toEqual(["navigate"]);
  });
});

describe("provider readiness (in-bubble picker gate)", () => {
  it("needs BOTH base url and model", () => {
    expect(isProviderConfigured("", "m")).toBe(false);
    expect(isProviderConfigured("http://x/v1", "")).toBe(false);
    expect(isProviderConfigured(" http://x/v1 ", " m ")).toBe(true);
  });
});

describe("turn loop", () => {
  it("streams the narration through the injected callbacks and answers", async () => {
    mockedStream.mockImplementation(async (_cfg, _wire, opts) => {
      opts?.onDelta?.("Welcome to the tour.");
      return { text: "Welcome to the tour.", toolCalls: [] };
    });
    const d = deps();
    const agent = createTourAgent(d);
    const out = await agent.narrate(STEP);
    expect(out).toBe("Welcome to the tour.");
    expect(d.onTurnStart).toHaveBeenCalled();
    expect(d.onDelta).toHaveBeenCalledWith("Welcome to the tour.");
    // the narration turn carries the tour-guide persona and the step seed
    const wire = mockedStream.mock.calls[0][1] as Array<{ role: string; content: string }>;
    expect(wire[0].role).toBe("system");
    expect(wire[0].content).toContain("TOUR GUIDE MODE");
    expect(wire.at(-1)).toMatchObject({ role: "user", content: expect.stringContaining("Sidebar") });
  });

  it("executes a navigate tool call through the hash router", async () => {
    mockedStream
      .mockImplementationOnce(async () => ({
        text: "Opening the orders table.",
        toolCalls: [{ id: "t1", name: "navigate", args: { path: "/m/orders" } }],
      }))
      .mockImplementationOnce(async (_cfg, wire) => {
        const toolMsg = wire.find((m) => (m as any).role === "tool") as any;
        // toolResultMessage serializes the RESULT payload only
        expect(JSON.parse(toolMsg.content)).toMatchObject({ navigatedTo: "/m/orders" });
        return { text: "Here are the orders.", toolCalls: [] };
      });
    const d = deps();
    const agent = createTourAgent(d);
    const out = await agent.ask("show me orders");
    expect(out).toBe("Here are the orders.");
    expect(window.location.hash).toBe("#/m/orders");
  });

  it("a hallucinated write tool is refused by the tour guard, never run", async () => {
    // the tour bubble has NO Confirm cards, so ANY non-navigate tool call is
    // refused at the runner (hard guard), not just discouraged by the prompt
    mockedStream
      .mockImplementationOnce(async () => ({
        text: "",
        toolCalls: [{ id: "t2", name: "delete_record", args: { model: "products", id: "3" } }],
      }))
      .mockImplementationOnce(async (_cfg, wire) => {
        const toolMsg = wire.find((m) => (m as any).role === "tool") as any;
        expect(JSON.parse(toolMsg.content).error).toContain("not available during the tour");
        return { text: "I cannot delete from the tour.", toolCalls: [] };
      });
    const agent = createTourAgent(deps());
    const out = await agent.ask("delete product 3");
    expect(out).toBe("I cannot delete from the tour.");
  });

  it("narrate() does nothing while a turn is already running (busy guard)", async () => {
    let release: (v: { text: string; toolCalls: never[] }) => void = () => {};
    mockedStream.mockImplementation(() => new Promise((r) => (release = r)));
    const agent = createTourAgent(deps());
    const first = agent.narrate(STEP);
    const second = await agent.ask("hello?");
    expect(second).toBe("");
    release({ text: "done", toolCalls: [] });
    await first;
    expect(agent.busy()).toBe(false);
  });
});

describe("agent identity (owner order 2026-11-09: a role like the team roster)", () => {
  it("has a name and a role", () => {
    expect(AGENT_IDENTITY.name).toBe("Ovi");
    expect(AGENT_IDENTITY.role).toBe("Admin Operations Assistant");
  });
});
