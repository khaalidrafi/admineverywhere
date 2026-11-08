/** tourBus.ts — the tiny channel between the Onboarding overlay and the AI
 *  chat panel (owner order 2026-11-08: the AI agent drives the app and the
 *  user can chat with it WHILE onboarding).
 *
 *  - `tourActive` is read by ChatPanel: while true it adds the navigate tool
 *    to the agent toolset, appends the tour-guide persona and keeps the
 *    privacy disclaimer visible.
 *  - `requestNarration` is how the overlay asks the panel to narrate a stop;
 *    the panel registers its sender via `bindNarrationSender`.
 *  - `bindStarter` lets the sidebar's "Take a tour" entry re-open the tour
 *    without prop drilling through the shell.
 *
 *  No Svelte store imports needed — plain callbacks keep this module
 *  import-order-safe for unit tests.
 */

import { writable } from "svelte/store";
import type { TourStep } from "./onboarding";

export const tourActive = writable(false);

type NarrationSender = ((step: TourStep) => void) | null;
type TourStarter = (() => void) | null;

let narrationSender: NarrationSender = null;
let tourStarter: TourStarter = null;

export const onboardingAgent = {
  /** Called by Onboarding.svelte when the AI tour mode is chosen. */
  activate(): void {
    tourActive.set(true);
  },
  deactivate(): void {
    tourActive.set(false);
  },
  bindNarrationSender(fn: NarrationSender): void {
    narrationSender = fn;
  },
  requestNarration(step: TourStep): void {
    narrationSender?.(step);
  },
  bindStarter(fn: TourStarter): void {
    tourStarter = fn;
  },
  startTour(): void {
    tourStarter?.();
  },
};
