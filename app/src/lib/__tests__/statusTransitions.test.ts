/** statusTransitions registry tests — pure logic, no fetch.
 *
 *  OWNER DIRECTIVE 2026-11-04 (#freshorama): "we won't approve/deny orders.
 *  So, nothing like pending orders." The registry ships EMPTY: the Freshorama
 *  admin renders orders as plain records — no transition buttons, no status
 *  board — even when the schema documents a transition endpoint. The tests
 *  pin that law from both sides. */
import { describe, expect, it } from "vitest";
import {
  getLegalTransitions,
  getStatusField,
  hasLifecycle,
  isTransitionLegal,
  lifecycleAvailable,
  lifecycleProblem,
  statusTransitions,
} from "../statusTransitions";
import { normalizeOpenAPI } from "../openapi";
import fixture from "./fixtures/openapi.json";
import type { ModelSpec } from "../types";

describe("statusTransitions registry — the no-approve/deny law", () => {
  it("ships empty: no model carries a client-side machine", () => {
    expect(Object.keys(statusTransitions)).toEqual([]);
  });

  it("orders have NO lifecycle — every transition answer is [] / false", () => {
    expect(hasLifecycle("orders")).toBe(false);
    expect(getStatusField("orders")).toBeNull();
    expect(getLegalTransitions("orders", "pending")).toEqual([]);
    expect(isTransitionLegal("orders", "pending", "confirmed")).toBe(false);
    expect(isTransitionLegal("orders", "pending", "cancelled")).toBe(false);
  });

  it("models without lifecycle stay without one", () => {
    expect(getLegalTransitions("products", "pending")).toEqual([]);
    expect(isTransitionLegal("products", "pending", "paid")).toBe(false);
    expect(getStatusField("products")).toBeNull();
    expect(getStatusField("categories")).toBeNull();
    expect(hasLifecycle("products")).toBe(false);
    expect(hasLifecycle("categories")).toBe(false);
  });
});

describe("lifecycleProblem — declared here AND documented there", () => {
  const LIVE = normalizeOpenAPI(fixture);

  it("is silent for a model the registry does not govern", () => {
    expect(lifecycleProblem(LIVE.byId.products)).toBeNull();
    expect(lifecycleAvailable(LIVE.byId.products)).toBe(false); // no affordance either way
  });

  it("orders get no affordance EVEN THOUGH the captured rig documents both actions — owner law", () => {
    expect(lifecycleProblem(LIVE.byId.orders)).toBeNull(); // ungoverned is not a defect
    expect(lifecycleAvailable(LIVE.byId.orders)).toBe(false); // and still no buttons
  });

  it("an ungoverned model missing the endpoints is still not a defect", () => {
    const { transitionPath, historyPath, ...bare } = LIVE.byId.orders;
    expect(lifecycleProblem(bare as ModelSpec)).toBeNull();
    expect(lifecycleAvailable(bare as ModelSpec)).toBe(false);
  });

  it("names 'no model' rather than guessing an affordance", () => {
    expect(lifecycleProblem(null)).toBe("no model");
    expect(lifecycleAvailable(undefined)).toBe(false);
  });
});
