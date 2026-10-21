/** statusTransitions registry tests — pure logic, no fetch. */
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

describe("statusTransitions registry", () => {
  it("has orders configured", () => {
    expect(statusTransitions.orders).toBeDefined();
    expect(statusTransitions.orders.statusField).toBe("status");
    expect(statusTransitions.orders.states).toEqual(["pending", "paid", "shipped", "refunded"]);
  });

  it("maps pending -> [paid]", () => {
    expect(getLegalTransitions("orders", "pending")).toEqual(["paid"]);
    expect(isTransitionLegal("orders", "pending", "paid")).toBe(true);
    expect(isTransitionLegal("orders", "pending", "shipped")).toBe(false);
    expect(isTransitionLegal("orders", "pending", "refunded")).toBe(false);
  });

  it("maps paid -> [shipped, refunded]", () => {
    expect(getLegalTransitions("orders", "paid")).toEqual(["shipped", "refunded"]);
    expect(isTransitionLegal("orders", "paid", "shipped")).toBe(true);
    expect(isTransitionLegal("orders", "paid", "refunded")).toBe(true);
    expect(isTransitionLegal("orders", "paid", "pending")).toBe(false);
  });

  it("maps shipped -> [refunded]", () => {
    expect(getLegalTransitions("orders", "shipped")).toEqual(["refunded"]);
    expect(isTransitionLegal("orders", "shipped", "refunded")).toBe(true);
    expect(isTransitionLegal("orders", "shipped", "paid")).toBe(false);
  });

  it("maps refunded -> [] (terminal)", () => {
    expect(getLegalTransitions("orders", "refunded")).toEqual([]);
    expect(isTransitionLegal("orders", "refunded", "pending")).toBe(false);
    expect(isTransitionLegal("orders", "refunded", "paid")).toBe(false);
  });

  it("returns [] for unknown states", () => {
    expect(getLegalTransitions("orders", "unknown")).toEqual([]);
    expect(isTransitionLegal("orders", "unknown", "paid")).toBe(false);
  });

  it("returns [] for models without lifecycle", () => {
    expect(getLegalTransitions("products", "pending")).toEqual([]);
    expect(isTransitionLegal("products", "pending", "paid")).toBe(false);
  });
});

describe("getStatusField", () => {
  it("returns field name for models with lifecycle", () => {
    expect(getStatusField("orders")).toBe("status");
  });

  it("returns null for models without lifecycle", () => {
    expect(getStatusField("products")).toBeNull();
    expect(getStatusField("categories")).toBeNull();
  });
});

describe("hasLifecycle", () => {
  it("returns true for orders", () => {
    expect(hasLifecycle("orders")).toBe(true);
  });

  it("returns false for other models", () => {
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

  it("is silent for orders against the captured rig, which documents both actions", () => {
    expect(lifecycleProblem(LIVE.byId.orders)).toBeNull();
    expect(lifecycleAvailable(LIVE.byId.orders)).toBe(true);
  });

  it("refuses a machine whose transition endpoint the API does not document", () => {
    const { transitionPath, historyPath, ...bare } = LIVE.byId.orders;
    const reason = lifecycleProblem(bare as ModelSpec);
    expect(reason).toMatch(/does not document POST \/api\/orders\/\{id\}\/transition\//);
    expect(lifecycleAvailable(bare as ModelSpec)).toBe(false);
  });

  it("names 'no model' rather than guessing an affordance", () => {
    expect(lifecycleProblem(null)).toBe("no model");
    expect(lifecycleAvailable(undefined)).toBe(false);
  });
});
