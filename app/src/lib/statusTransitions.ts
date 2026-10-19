/** Status transition registry — per-model state machines for lifecycle-governed records.
 *
 * Models without an entry here render exactly as before (no transition buttons).
 * Models with an entry get:
 *   - A status column showing the current state
 *   - Transition buttons for legal next states (disabled when unavailable)
 *   - 409 Conflict errors surface via the existing error banner/toast
 *
 * The registry is the single source of truth for client-side transition logic.
 * The backend validates independently; this is the UI affordance layer.
 */

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


/** Get all states for a model in lifecycle order. */
export function getStates(modelId: string): string[] {
  return statusTransitions[modelId]?.states ?? [];
}
