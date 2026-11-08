/** onboarding.ts — first-run + replayable "Take a tour" state machine.
 *
 *  Owner order 2026-11-08: onboarding/"Take a tour" in the admin apps besides
 *  docs; a GENERIC tour (spotlight walkthrough) AND an AGENTIC tour (the AI
 *  agent drives the app, narrates each feature and the user can chat with it
 *  mid-tour); the first screen offers the AI vs non-AI choice.
 *
 *  Design laws kept:
 *  - Pure state machine + localStorage persistence, no component imports —
 *    everything here is unit-testable without a DOM.
 *  - Steps never hard-fail: a step whose CSS selector matches nothing is
 *    skipped by the component (schema-dependent surfaces may be absent).
 *  - Nothing in the tour writes data; the agentic mode reuses the SAME
 *    confirm-gated agent as the chat panel (reads run free, writes ask).
 */

export type TourMode = "ai" | "classic";

export interface TourStep {
  id: string;
  title: string;
  body: string;
  /** CSS selector of the element to spotlight. Missing element = skip step. */
  selector?: string;
  /** Agentic mode: prompt seed the tour-guide agent narrates from. */
  agentPrompt?: string;
}

/** The generic tour — every admin app built from this framework. */
export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Welcome",
    body: "A 60-second walk through your admin. Use Next/Back any time, Esc quits.",
  },
  {
    id: "sidebar",
    title: "Sidebar — your modules",
    body: "Every module of your backend shows up here automatically, straight from the live API schema. Nothing to register by hand.",
    selector: "aside, [data-tour='sidebar'], nav",
    agentPrompt:
      "Point the user to the sidebar. Explain that the module list is generated from their live API schema — new backend models appear here automatically.",
  },
  {
    id: "dashboard",
    title: "Dashboard — widgets",
    body: "Live stat cards and charts. Add your own in Widget Studio; widgets can watch an endpoint and alert you on thresholds.",
    selector: "[data-tour='dashboard'], main",
    agentPrompt:
      "Introduce the dashboard widgets: live stats from their data, user-buildable instances in Widget Studio, threshold alerts through the notification bell.",
  },
  {
    id: "modules",
    title: "Data tables",
    body: "Open any module for a searchable, paginated table: edit inline, run bulk actions, export CSV, and every change lands in history.",
    agentPrompt:
      "Walk the user into one data table: search, pagination, inline edit, bulk actions, dual-layer CSV export. Offer to open a specific model for them.",
  },
  {
    id: "assistant",
    title: "AI assistant — Ctrl+K",
    body: "Your AI agent: ask about your data in plain words, and let it run admin actions — it can look up, create, update and transition records. Writes always ask before they land.",
    agentPrompt:
      "Demonstrate the AI assistant: it answers questions about their data and PERFORMS admin actions with their own login, every write gated by a Confirm card. Show a read example.",
  },
  {
    id: "notifications",
    title: "Notifications & activity",
    body: "The bell collects alerts (widget thresholds, releases). The Activity screen is the full audit trail of who changed what.",
    selector: "[data-tour='notifications']",
    agentPrompt:
      "Explain notifications (bell, thresholds) and the Activity audit trail (who changed what, when).",
  },
  {
    id: "branding",
    title: "Make it yours",
    body: "Colors, logo, font — rebrand the whole app live from the Branding screen, no rebuild needed.",
    selector: "[data-tour='branding']",
    agentPrompt: "Show the Branding screen: live rebranding (colors, logo, font) without a rebuild.",
  },
  {
    id: "docs",
    title: "Docs & tour",
    body: "The full user guide lives in Docs. Re-run this tour any time from the sidebar — Take a tour.",
  },
];

export interface OnboardingState {
  /** true once the choice screen has been answered (tour done or skipped). */
  done: boolean;
  mode?: TourMode;
  /** index into TOUR_STEPS while a tour is running; absent otherwise. */
  step?: number;
  startedAt?: number;
}

const KEY = "dad.onboarding.v1";

export function loadOnboarding(): OnboardingState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { done: false };
    const parsed = JSON.parse(raw) as OnboardingState;
    if (typeof parsed !== "object" || parsed === null) return { done: false };
    return { done: Boolean(parsed.done), mode: parsed.mode, step: parsed.step };
  } catch {
    return { done: false };
  }
}

export function saveOnboarding(state: OnboardingState): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable (private mode) — tour still works in-memory */
  }
}

/** Pure reducer — the component drives it, tests pin it. */
export function reduce(
  state: OnboardingState,
  action:
    | { type: "choose"; mode: TourMode }
    | { type: "next" }
    | { type: "back" }
    | { type: "goto"; step: number }
    | { type: "finish" }
    | { type: "reset" },
): OnboardingState {
  switch (action.type) {
    case "choose":
      return { ...state, mode: action.mode, step: 0, startedAt: Date.now() };
    case "next": {
      if (state.step === undefined) return state;
      const next = state.step + 1;
      return next >= TOUR_STEPS.length ? { ...state, done: true, step: undefined } : { ...state, step: next };
    }
    case "back": {
      if (state.step === undefined) return state;
      return { ...state, step: Math.max(0, state.step - 1) };
    }
    case "goto":
      return { ...state, step: Math.min(Math.max(0, action.step), TOUR_STEPS.length - 1) };
    case "finish":
      return { ...state, done: true, step: undefined };
    case "reset":
      return { done: false };
  }
}

/** Steps the spotlight can actually target in THIS install: those whose
 *  selector matches a live element (or that declare no selector). */
export function resolvableSteps(steps: TourStep[], query: (sel: string) => unknown): TourStep[] {
  return steps.filter((s) => !s.selector || query(s.selector));
}

/** The agentic tour drives navigation: given the current step's agentPrompt
 *  (falls back to title+body), compose the user turn sent to the agent. */
export function stepAgentTurn(step: TourStep, appName: string): string {
  const seed = step.agentPrompt ?? `${step.title}: ${step.body}`;
  return `We are on the "${step.title}" stop of the guided tour of the ${appName} admin. ${seed} Narrate this stop in one short paragraph, then ask the user if they want to try anything.`;
}
