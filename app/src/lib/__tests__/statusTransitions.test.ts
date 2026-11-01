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
    expect(statusTransitions.orders.states).toEqual([
      "pending",
      "confirmed",
      "processing",
      "ready_to_ship",
      "shipped",
      "in_transit",
      "delivered",
      "delivery_failed",
      "returned",
      "on_hold",
      "cancelled",
    ]);
  });

  it("maps pending -> [confirmed, on_hold, cancelled]", () => {
    expect(getLegalTransitions("orders", "pending")).toEqual([
      "confirmed",
      "on_hold",
      "cancelled",
    ]);
    expect(isTransitionLegal("orders", "pending", "confirmed")).toBe(true);
    expect(isTransitionLegal("orders", "pending", "processing")).toBe(false);
    expect(isTransitionLegal("orders", "pending", "shipped")).toBe(false);
    expect(isTransitionLegal("orders", "pending", "returned")).toBe(false);
  });

  it("maps the forward main line: confirmed -> processing -> ready_to_ship -> shipped", () => {
    expect(getLegalTransitions("orders", "confirmed")).toEqual([
      "processing",
      "ready_to_ship",
      "on_hold",
      "cancelled",
    ]);
    expect(getLegalTransitions("orders", "processing")).toEqual([
      "ready_to_ship",
      "on_hold",
      "cancelled",
    ]);
    expect(getLegalTransitions("orders", "ready_to_ship")).toEqual([
      "shipped",
      "on_hold",
      "cancelled",
    ]);
    expect(isTransitionLegal("orders", "processing", "shipped")).toBe(false);
  });

  it("maps shipped -> [in_transit, delivered, delivery_failed, on_hold, cancelled]", () => {
    expect(getLegalTransitions("orders", "shipped")).toEqual([
      "in_transit",
      "delivered",
      "delivery_failed",
      "on_hold",
      "cancelled",
    ]);
    expect(isTransitionLegal("orders", "shipped", "delivered")).toBe(true);
    expect(isTransitionLegal("orders", "shipped", "returned")).toBe(false);
  });

  it("maps the delivery_failed recovery path", () => {
    expect(getLegalTransitions("orders", "delivery_failed")).toEqual([
      "shipped",
      "returned",
      "cancelled",
    ]);
    expect(isTransitionLegal("orders", "delivery_failed", "shipped")).toBe(true);
    expect(isTransitionLegal("orders", "delivery_failed", "delivered")).toBe(false);
  });

  it("delivered exits only into returned; on_hold re-enters the line", () => {
    expect(getLegalTransitions("orders", "delivered")).toEqual(["returned"]);
    expect(getLegalTransitions("orders", "on_hold")).toEqual([
      "confirmed",
      "processing",
      "cancelled",
    ]);
  });

  it("maps returned and cancelled to [] (terminal)", () => {
    expect(getLegalTransitions("orders", "returned")).toEqual([]);
    expect(getLegalTransitions("orders", "cancelled")).toEqual([]);
    expect(isTransitionLegal("orders", "returned", "pending")).toBe(false);
    expect(isTransitionLegal("orders", "cancelled", "confirmed")).toBe(false);
  });

  it("returns [] for unknown states", () => {
    expect(getLegalTransitions("orders", "unknown")).toEqual([]);
    expect(isTransitionLegal("orders", "unknown", "confirmed")).toBe(false);
  });

  it("returns [] for models without lifecycle", () => {
    expect(getLegalTransitions("products", "pending")).toEqual([]);
    expect(isTransitionLegal("products", "pending", "confirmed")).toBe(false);
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
