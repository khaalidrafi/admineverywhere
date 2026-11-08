<script lang="ts">
  /** Onboarding — "Take a tour" (owner order 2026-11-08).
   *
   *  Screen 1: the choice — AI-guided tour vs classic (no-AI) tour.
   *  Classic: spotlight steps over the real UI, Next/Back/Esc.
   *  AI: the SAME spotlight, but the AI agent narrates each stop in the
   *  chat panel, can open screens itself (navigate tool) and the user can
   *  chat with it mid-tour. The AI privacy disclaimer shows on the choice
   *  screen; in AI mode the panel shows its own disclaimer as well.
   *
   *  Mounted by Shell.svelte; re-runnable from the sidebar ("Take a tour").
   */
  import { onMount } from "svelte";
  import { app } from "../lib/stores";
  import {
    TOUR_STEPS,
    loadOnboarding,
    reduce,
    resolvableSteps,
    saveOnboarding,
    stepAgentTurn,
    type OnboardingState,
    type TourMode,
  } from "../lib/onboarding";
  import { onboardingAgent } from "../lib/tourBus";
  import Icon from "../components/Icon.svelte";
  import AiDisclaimer from "../ai/AiDisclaimer.svelte";

  let state = $state<OnboardingState>(loadOnboarding());
  let active = $state(false);
  let mode: TourMode | undefined = $state(undefined);
  let rect = $state<{ top: number; left: number; width: number; height: number } | null>(null);
  let cardPos = $state<{ top: number; left: number } | null>(null);

  const appName = $derived($app.brand.appName);
  const steps = $derived(active ? resolvableSteps(TOUR_STEPS, (sel) => document.querySelector(sel)) : []);
  const step = $derived(state.step !== undefined ? (steps[state.step] ?? null) : null);

  function persist(): void {
    saveOnboarding(state);
  }

  export function start(): void {
    state = { done: false };
    mode = undefined;
    rect = null;
    cardPos = null;
    active = true;
  }

  function choose(m: TourMode): void {
    mode = m;
    state = reduce(state, { type: "choose", mode: m });
    persist();
    if (m === "ai") onboardingAgent.activate();
    positionSpotlight();
  }

  function next(): void {
    const current = step;
    if (mode === "ai" && current) onboardingAgent.requestNarration(current);
    state = reduce(state, { type: "next" });
    persist();
    if (state.done) finish();
    else positionSpotlight();
  }

  function back(): void {
    state = reduce(state, { type: "back" });
    persist();
    positionSpotlight();
  }

  function finish(): void {
    state = reduce({ ...state, step: state.step }, { type: "finish" });
    persist();
    onboardingAgent.deactivate();
    active = false;
    rect = null;
    cardPos = null;
  }

  function onKey(e: KeyboardEvent): void {
    if (!active || state.step === undefined) return;
    if (e.key === "Escape") finish();
    else if (e.key === "ArrowRight") next();
    else if (e.key === "ArrowLeft") back();
  }

  /** Spotlight the step's selector; steps whose element is absent are
   *  skipped automatically (schema-dependent surfaces may not exist). */
  function positionSpotlight(): void {
    let idx = state.step ?? 0;
    if (idx < 0 || idx >= steps.length) {
      rect = null;
      cardPos = null;
      return;
    }
    // skip steps whose target is missing (max one full lap, then land)
    for (let guard = 0; guard <= steps.length; guard++) {
      const s = steps[idx];
      if (!s?.selector || document.querySelector(s.selector)) break;
      idx = (idx + 1) % steps.length;
      state = { ...state, step: idx };
    }
    const s = steps[state.step ?? idx];
    const target = s?.selector ? document.querySelector(s.selector) : null;
    if (!target) {
      rect = null;
      cardPos = null;
      return;
    }
    const r = target.getBoundingClientRect();
    const pad = 8;
    rect = { top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2 };
    const spaceBelow = window.innerHeight - r.bottom;
    const cardW = Math.min(360, window.innerWidth - 24);
    cardPos = {
      top: spaceBelow > 240 ? r.bottom + 14 : Math.max(12, r.top - 250),
      left: Math.min(Math.max(12, r.left), window.innerWidth - cardW - 12),
    };
  }

  onMount(() => {
    window.addEventListener("resize", positionSpotlight);
    return () => window.removeEventListener("resize", positionSpotlight);
  });

  // let the sidebar's "Take a tour" entry re-open the overlay
  onboardingAgent.bindStarter(() => start());
  // first-run: open the choice screen automatically once the shell is up
  // (skipped under vitest — the overlay would leak into every shell-mount test)
  $effect(() => {
    if (active) return;
    if (import.meta.env.MODE === "test") return;
    if (!state.done && state.step === undefined && !$app.schemaLoading && $app.schema) {
      start();
    }
  });
</script>

<svelte:window onkeydown={onKey} />

{#if active && state.step === undefined && !state.done}
  <!-- choice screen -->
  <div class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Take a tour">
    <div class="card w-full max-w-lg p-6">
      <h2 class="text-lg font-semibold">Welcome to {appName}</h2>
      <p class="mt-1 text-sm text-text/60">Take a 60-second tour? Pick how you'd like to see it.</p>

      <div class="mt-4 grid gap-3">
        <button class="flex items-start gap-3 rounded-xl border border-text/10 p-4 text-left transition-colors hover:border-accent/50"
                onclick={() => choose("ai")} data-tour="tour-choice-ai">
          <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <Icon name="chat" size={18} />
          </span>
          <span>
            <span class="block text-sm font-semibold">Guided by the AI agent</span>
            <span class="mt-0.5 block text-xs leading-relaxed text-text/50">
              The agent drives the app — it opens each feature, narrates it, and answers your
              questions while you look around.
            </span>
          </span>
        </button>
        <button class="flex items-start gap-3 rounded-xl border border-text/10 p-4 text-left transition-colors hover:border-accent/50"
                onclick={() => choose("classic")} data-tour="tour-choice-classic">
          <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-text/10 text-text/70">
            <Icon name="menu" size={18} />
          </span>
          <span>
            <span class="block text-sm font-semibold">Quick tour — no AI</span>
            <span class="mt-0.5 block text-xs leading-relaxed text-text/50">
              A classic spotlight walkthrough. Nothing is sent anywhere.
            </span>
          </span>
        </button>
      </div>

      <div class="mt-3">
        <AiDisclaimer />
      </div>

      <div class="mt-2 flex justify-end">
        <button class="btn btn-ghost text-xs" onclick={finish}>Skip</button>
      </div>
    </div>
  </div>
{:else if active && step}
  <!-- spotlight overlay: the ring div dims everything around it -->
  <div class="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label={step.title}>
    {#if rect}
      <div
        class="pointer-events-none absolute rounded-xl ring-2 ring-[var(--brand-accent)] transition-all duration-200"
        style="top:{rect.top}px; left:{rect.left}px; width:{rect.width}px; height:{rect.height}px;
               box-shadow: 0 0 0 100vmax rgba(0,0,0,0.6);"
      ></div>
    {:else}
      <div class="absolute inset-0 bg-black/60"></div>
    {/if}
    <div
      class="card absolute w-[min(92vw,340px)] p-4"
      style="top:{cardPos?.top ?? 96}px; left:{cardPos?.left ?? 16}px;"
    >
      <div class="flex items-center justify-between">
        <span class="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
          {mode === "ai" ? "AI tour" : "Tour"} · {(state.step ?? 0) + 1}/{steps.length}
        </span>
        {#if mode === "ai"}
          <span class="text-[10px] text-text/40">ask the agent anything in the chat</span>
        {/if}
      </div>
      <h3 class="mt-2 text-sm font-semibold">{step.title}</h3>
      <p class="mt-1 text-xs leading-relaxed text-text/60">{step.body}</p>
      <div class="mt-3 flex items-center justify-between">
        <button class="btn btn-ghost px-3 text-xs" onclick={finish}>End tour</button>
        <div class="flex items-center gap-2">
          <button class="btn btn-ghost px-3 text-xs" disabled={(state.step ?? 0) === 0} onclick={back}>
            <Icon name="left" size={13} /> Back
          </button>
          <button class="btn btn-primary px-3 text-xs" onclick={next}>
            {(state.step ?? 0) + 1 >= steps.length ? "Finish" : "Next"} <Icon name="right" size={13} />
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
