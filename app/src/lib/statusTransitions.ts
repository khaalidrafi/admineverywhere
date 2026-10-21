/** Status transition registry — per-model state machines for lifecycle-governed records.
 *
 * Models without an entry here render exactly as before (no transition buttons).
 * Models with an entry get:
 *   - A status column showing the current state
 *   - Transition buttons for legal next states (disabled when unavailable)
 *   - 409 Conflict errors surface via the existing error banner/toast
 *
 * The entry alone is not enough: the affordance also requires the server to
 * document the endpoints (see lifecycleProblem below).
 *
 * The registry is the single source of truth for client-side transition logic.
 * The backend validates independently; this is the UI affordance layer.
 */
import type { ModelSpec } from "./types";

export interface TransitionConfig {
  /** The field name that holds the status (usually "status") */
  statusField: string;
  /** Map from current state to array of legal target states */
  transitions: Record<string, string[]>;
  /** States in lifecycle order (first is entry, last is terminal) */
  states: string[];
}

/** Registry of models with lifecycle-governed status fields. */
export const statusTransitions: Record<string, TransitionConfig> = {
  orders: {
    statusField: "status",
    states: ["pending", "paid", "shipped", "refunded"],
    transitions: {
      pending: ["paid"],
      paid: ["shipped", "refunded"],
      shipped: ["refunded"],
      refunded: [], // terminal
    },
  },
};

/** Get the legal transitions from a given state for a model. */
export function getLegalTransitions(modelId: string, currentState: string): string[] {
  const config = statusTransitions[modelId];
  if (!config) return [];
  return config.transitions[currentState] ?? [];
}

/** Check if a transition is legal. */
export function isTransitionLegal(modelId: string, fromState: string, toState: string): boolean {
  const legal = getLegalTransitions(modelId, fromState);
  return legal.includes(toState);
}

/** Get the status field name for a model (if it has lifecycle governance). */
export function getStatusField(modelId: string): string | null {
  return statusTransitions[modelId]?.statusField ?? null;
}

/** Check if a model has lifecycle governance. */
export function hasLifecycle(modelId: string): boolean {
  return modelId in statusTransitions;
}

/** Why a model's declared state machine cannot be offered in this UI, or null
 *  when it can. The registry declares the machine client-side; the SERVER
 *  documents the endpoints. A machine whose POST …/transition/ is missing from
 *  the schema is REFUSED rather than rendered — a button that 404s on every
 *  click is worse than no button, and it is the same "bind it only when the
 *  document proves it" law that governs exportPath (FR-R005) and mePath
 *  (FR-R007). Callers render the returned reason instead of the affordance. */
export function lifecycleProblem(model: ModelSpec | null | undefined): string | null {
  if (!model) return "no model";
  if (!hasLifecycle(model.id)) return null; // not governed is not a defect
  if (model.transitionPath) return null;
  return `"${model.id}" has a client-side lifecycle but its API does not document POST ${model.detailPath}transition/ — transitions are not offered`;
}

/** The lifecycle affordance is available: declared here AND documented there. */
export function lifecycleAvailable(model: ModelSpec | null | undefined): boolean {
  return hasLifecycle(model?.id ?? "") && !lifecycleProblem(model);
}
