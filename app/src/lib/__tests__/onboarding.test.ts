/** onboarding.ts tests — the tour state machine (owner order 2026-11-08).
 *
 *  Pins: the AI-vs-classic choice enters step 0 with the mode recorded,
 *  next/back/finish transitions, the reducer never escapes the step range,
 *  resolvableSteps drops steps whose selector matches nothing, and the
 *  agentic turn composer produces a schema-free instruction the panel can
 *  send as a user turn.
 */
import { describe, expect, it } from "vitest";
import {
  TOUR_STEPS,
  reduce,
  resolvableSteps,
  stepAgentTurn,
  type OnboardingState,
} from "../onboarding";

const FRESH: OnboardingState = { done: false };

describe("onboarding reducer", () => {
  it("choosing a mode starts the tour at step 0 and records it", () => {
    const ai = reduce(FRESH, { type: "choose", mode: "ai" });
    expect(ai.mode).toBe("ai");
    expect(ai.step).toBe(0);
    expect(ai.done).toBe(false);
    const classic = reduce(FRESH, { type: "choose", mode: "classic" });
    expect(classic.mode).toBe("classic");
  });

  it("next walks forward and finishes past the last step", () => {
    let s = reduce(FRESH, { type: "choose", mode: "classic" });
    for (let i = 0; i < TOUR_STEPS.length - 1; i++) {
      s = reduce(s, { type: "next" });
      expect(s.step).toBe(i + 1);
    }
    s = reduce(s, { type: "next" });
    expect(s.done).toBe(true);
    expect(s.step).toBeUndefined();
  });

  it("back clamps at the first step", () => {
    let s = reduce(FRESH, { type: "choose", mode: "classic" });
    s = reduce(s, { type: "back" });
    expect(s.step).toBe(0);
  });

  it("finish marks done from any step", () => {
    let s = reduce(FRESH, { type: "choose", mode: "ai" });
    s = reduce(s, { type: "goto", step: 3 });
    s = reduce(s, { type: "finish" });
    expect(s.done).toBe(true);
    expect(s.step).toBeUndefined();
  });

  it("goto clamps to the valid range", () => {
    let s = reduce(FRESH, { type: "choose", mode: "ai" });
    s = reduce(s, { type: "goto", step: 999 });
    expect(s.step).toBe(TOUR_STEPS.length - 1);
    s = reduce(s, { type: "goto", step: -5 });
    expect(s.step).toBe(0);
  });

  it("reset clears everything", () => {
    const s = reduce({ done: true, mode: "ai", step: 2 }, { type: "reset" });
    expect(s).toEqual({ done: false });
  });

  it("the tour covers the directive's stops (sidebar, tables, assistant, tour re-entry)", () => {
    const ids = TOUR_STEPS.map((s) => s.id);
    for (const want of ["sidebar", "dashboard", "modules", "assistant", "notifications", "docs"]) {
      expect(ids, want).toContain(want);
    }
    expect(TOUR_STEPS.length).toBeGreaterThanOrEqual(7);
  });
});

describe("resolvableSteps", () => {
  it("keeps selector-less steps and drops steps whose selector misses", () => {
    const steps = [
      { id: "a", title: "A", body: "no selector" },
      { id: "b", title: "B", body: "hits", selector: "body" },
      { id: "c", title: "C", body: "misses", selector: "[data-tour='does-not-exist']" },
    ];
    const kept = resolvableSteps(steps, (sel) => document.querySelector(sel));
    expect(kept.map((s) => s.id)).toEqual(["a", "b"]);
  });
});

describe("stepAgentTurn", () => {
  it("composes a narration turn from the agent prompt seed", () => {
    const step = { id: "x", title: "Data tables", body: "Search and edit.", agentPrompt: "Explain CRUD." };
    const turn = stepAgentTurn(step, "Freshorama Admin");
    expect(turn).toContain("Data tables");
    expect(turn).toContain("Explain CRUD.");
    expect(turn).toContain("Freshorama Admin");
  });

  it("falls back to title+body without an agent prompt", () => {
    const turn = stepAgentTurn({ id: "y", title: "T", body: "B" }, "App");
    expect(turn).toContain("T");
    expect(turn).toContain("B");
  });
});
