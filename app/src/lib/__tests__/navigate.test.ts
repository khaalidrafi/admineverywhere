/** navigate tool tests — the agentic onboarding driver (owner order
 *  2026-11-08: "the AI Agent will drive the app").
 *
 *  Pins: the navigate tool is offered separately from buildAgentTools,
 *  classified NON-destructive (navigation is a read-only surface change),
 *  executed only when the panel injected navigateTo, refuses non-'/' paths,
 *  and the tour-guide addendum exists.
 */
import { describe, expect, it } from "vitest";
import {
  buildAgentTools,
  executeTool,
  isDestructive,
  navigateTool,
  tourGuideAddendum,
  type ToolCtx,
} from "../agent";
import type { AppConfig } from "../types";

const CFG: AppConfig = { apiUrl: "https://api.example.com", authPath: "/a", schemaPath: "/s" };

function ctx(navigateTo?: (path: string) => void): ToolCtx {
  return { cfg: CFG, token: null, schema: null, navigateTo };
}

describe("navigate tool", () => {
  it("is offered as a separate tool, not part of the generic toolset", () => {
    expect(buildAgentTools(null).map((t) => t.function.name)).not.toContain("navigate");
    expect(navigateTool().function.name).toBe("navigate");
  });

  it("is classified non-destructive — no Confirm card for navigation", () => {
    expect(isDestructive("navigate")).toBe(false);
  });

  it("executes through the injected navigator and reports the path", async () => {
    const seen: string[] = [];
    const res = await executeTool(
      { id: "1", name: "navigate", args: { path: "/m/orders" } },
      ctx((p) => seen.push(p)),
    );
    expect(res.ok).toBe(true);
    expect(res.result).toEqual({ navigatedTo: "/m/orders" });
    expect(seen).toEqual(["/m/orders"]);
  });

  it("refuses to run without the tour context", async () => {
    const res = await executeTool({ id: "2", name: "navigate", args: { path: "/x" } }, ctx());
    expect(res.ok).toBe(false);
    expect(String(res.result.error)).toContain("guided tour");
  });

  it("refuses paths that do not start with '/'", async () => {
    const res = await executeTool(
      { id: "3", name: "navigate", args: { path: "https://evil.example" } },
      ctx(() => {}),
    );
    expect(res.ok).toBe(false);
  });

  it("the tour-guide addendum exists and mentions navigation", () => {
    const addendum = tourGuideAddendum();
    expect(addendum).toContain("TOUR GUIDE MODE");
    expect(addendum).toContain("navigate");
  });
});
