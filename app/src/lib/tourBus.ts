/** tourBus.ts — the tiny channel between the sidebar and the Onboarding
 *  overlay (owner order 2026-11-08: "Take a tour" re-runnable from the
 *  sidebar without prop drilling through the shell).
 *
 *  2026-11-09 rework (owner order: the tour bubble must speak with its own
 *  speech bubble and the chat window must stay hidden): the narration
 *  channel to ChatPanel is GONE — the tour runs its own agent
 *  (lib/tourAgent.ts) inside the bubble. This module now only carries the
 *  sidebar's start request.
 *
 *  Plain callbacks keep this module import-order-safe for unit tests.
 */

type TourStarter = (() => void) | null;

let tourStarter: TourStarter = null;

export const onboardingAgent = {
  bindStarter(fn: TourStarter): void {
    tourStarter = fn;
  },
  startTour(): void {
    tourStarter?.();
  },
};
