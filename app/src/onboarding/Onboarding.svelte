<script lang="ts">
  /** Onboarding — "Take a tour" (owner order 2026-11-08, reworked on the
   *  owner's UX verdict 2026-11-09: "AI tour is still cluttering the whole
   *  screen - a bad UI and UX! ... The chat window still shows up. It should
   *  stay hidden, and the tour should show what the agent says at each step
   *  with a speech bubble and all other options for next/prev and asking").
   *
   *  What the tour IS now:
   *  - Screen 1: the choice — AI-guided vs classic (no-AI) tour.
   *  - Both tours spotlight the real UI with a ring and speak from ONE
   *    compact speech bubble anchored to the target. NO full-screen dim:
   *    the rest of the app stays visible and interactive.
   *  - AI mode: the ChatPanel NEVER opens. The agent (Ovi, Admin Operations
   *    Assistant) narrates each stop INTO the bubble, can drive the app
   *    (read-only navigate tool), and an ask-box in the bubble takes
   *    questions mid-tour. Next/Prev stay on the bubble.
   *  - Provider choice (owner order 2026-11-09: "let users choose the AI
   *    provider with kilo pre selected, and keyless ones suggested"): if no
   *    AI provider is configured, the bubble offers the presets — Kilo
   *    Gateway pre-selected, keyless ones tagged "free". "Continue without
   *    AI" drops to the classic tour.
   *  - The AI privacy disclaimer shows on the choice screen and under the
   *    provider picker (cloud-data law).
   *
   *  Mounted by Shell.svelte; re-runnable from the sidebar ("Take a tour").
   */
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import { ai, app, effectiveConfig, saveAiSettings } from "../lib/stores";
  import {
    TOUR_STEPS,
    loadOnboarding,
    reduce,
    resolvableSteps,
    saveOnboarding,
    type OnboardingState,
    type TourMode,
  } from "../lib/onboarding";
  import { onboardingAgent } from "../lib/tourBus";
  import { createTourAgent, isProviderConfigured, type TourAgent } from "../lib/tourAgent";
  import { AI_PRESETS, KEYLESS_PRESETS, presetById, type ProviderPreset } from "../lib/aiProviders";
  import { AGENT_IDENTITY } from "../lib/agent";
  import Icon from "../components/Icon.svelte";
  import AiDisclaimer from "../ai/AiDisclaimer.svelte";

  interface BubbleLine {
    who: "agent" | "you";
    text: string;
  }

  let state = $state<OnboardingState>(loadOnboarding());
  let active = $state(false);
  let mode: TourMode | undefined = $state(undefined);
  let rect = $state<{ top: number; left: number; width: number; height: number } | null>(null);
  let cardPos = $state<{ top: number; left: number } | null>(null);
  /** Which edge of the bubble carries the speech tail (null = centered, no target). */
  let tail: "up" | "down" | null = $state(null);

  // in-bubble conversation (AI mode): narration streams into the last agent line
  let bubble = $state<BubbleLine[]>([]);
  let askText = $state("");
  let agentBusy = $state(false);
  /** Provider picker: Kilo Gateway PRE-SELECTED (owner order 2026-11-09). */
  let pickedPreset = $state("kilo-free");
  let savingProvider = $state(false);
  let agent: TourAgent | null = null;

  const appName = $derived($app.brand.appName);
  const aiReady = $derived(isProviderConfigured($ai.baseUrl, $ai.model));
  const showProviderPicker = $derived(mode === "ai" && !aiReady);
  const steps = $derived(active ? resolvableSteps(TOUR_STEPS, (sel) => document.querySelector(sel)) : []);
  const step = $derived(state.step !== undefined ? (steps[state.step] ?? null) : null);
  /** keyless first (suggested), paid last — Kilo leads by array order. */
  const pickerPresets = $derived([...KEYLESS_PRESETS, ...AI_PRESETS.filter((p) => !p.keyless)]);

  function persist(): void {
    saveOnboarding(state);
  }

  export function start(): void {
    state = { done: false };
    mode = undefined;
    rect = null;
    cardPos = null;
    tail = null;
    bubble = [];
    askText = "";
    agentBusy = false;
    pickedPreset = "kilo-free";
    active = true;
  }

  function choose(m: TourMode): void {
    mode = m;
    state = reduce(state, { type: "choose", mode: m });
    persist();
    positionSpotlight();
    if (m === "ai" && aiReady) narrateCurrent();
  }

  /* ---- tour agent (own runner; the ChatPanel stays closed) ---- */

  function ensureAgent(): TourAgent {
    const a = get(ai);
    const appl = get(app);
    agent = createTourAgent({
      cfg: effectiveConfig(),
      aiCfg: { baseUrl: a.baseUrl, apiKey: a.apiKey, model: a.model },
      token: appl.token || null,
      schema: appl.schema ?? null,
      appName,
      onTurnStart: () => {
        bubble.push({ who: "agent", text: "" });
      },
      onDelta: (delta) => {
        const last = bubble[bubble.length - 1];
        if (last && last.who === "agent") last.text += delta;
      },
    });
    return agent;
  }

  function narrateCurrent(): void {
    const s = step;
    if (!s || mode !== "ai" || !aiReady) return;
    bubble = [];
    agentBusy = true;
    const a = agent ?? ensureAgent();
    a.narrate(s)
      .catch(() => {
        /* stream error — the bubble keeps what streamed; next/prev still work */
      })
      .finally(() => {
        agentBusy = false;
      });
  }

  function ask(): void {
    const text = askText.trim();
    if (!text || agentBusy || !aiReady) return;
    if (showProviderPicker) return;
    bubble.push({ who: "you", text });
    askText = "";
    agentBusy = true;
    const a = agent ?? ensureAgent();
    a.ask(text)
      .catch(() => {})
      .finally(() => {
        agentBusy = false;
      });
  }

  function stopAgent(): void {
    agent?.stop();
    agentBusy = false;
  }

  /* ---- provider picker (in-bubble, Kilo pre-selected) ---- */

  async function applyPreset(): Promise<void> {
    const p = presetById(pickedPreset);
    if (!p || savingProvider) return;
    savingProvider = true;
    try {
      // keep any custom system prompt; fill the three provider fields
      await saveAiSettings(p.baseUrl, p.apiKey, p.model, get(ai).systemPrompt);
      agent = null; // recreate with the fresh provider config
      narrateCurrent();
    } finally {
      savingProvider = false;
    }
  }

  function continueWithoutAi(): void {
    stopAgent();
    bubble = [];
    mode = "classic";
  }

  /* ---- navigation ---- */

  function next(): void {
    stopAgent();
    state = reduce(state, { type: "next" });
    persist();
    if (state.done) finish();
    else {
      positionSpotlight();
      if (mode === "ai" && aiReady) narrateCurrent();
    }
  }

  function back(): void {
    stopAgent();
    state = reduce(state, { type: "back" });
    persist();
    positionSpotlight();
    if (mode === "ai" && aiReady) narrateCurrent();
  }

  function finish(): void {
    stopAgent();
    state = reduce({ ...state, step: state.step }, { type: "finish" });
    persist();
    active = false;
    rect = null;
    cardPos = null;
    tail = null;
    bubble = [];
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
      tail = null;
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
      tail = null;
      // centered bubble (welcome / provider / closing stops)
      const cardW = Math.min(400, window.innerWidth - 24);
      cardPos = {
        top: Math.max(24, window.innerHeight * 0.2),
        left: Math.max(12, (window.innerWidth - cardW) / 2),
      };
      return;
    }
    const r = target.getBoundingClientRect();
    const pad = 8;
    rect = { top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2 };
    const spaceBelow = window.innerHeight - r.bottom;
    const cardW = Math.min(400, window.innerWidth - 24);
    if (spaceBelow > 300) {
      // bubble below the target → tail points up
      tail = "up";
      cardPos = { top: r.bottom + 16, left: Math.min(Math.max(12, r.left), window.innerWidth - cardW - 12) };
    } else {
      // bubble above the target → tail points down
      tail = "down";
      cardPos = {
        top: Math.max(12, r.top - 300),
        left: Math.min(Math.max(12, r.left), window.innerWidth - cardW - 12),
      };
    }
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

  const presetIsPicked = (p: ProviderPreset) => p.id === pickedPreset;
</script>

<svelte:window onkeydown={onKey} />

{#if active && state.step === undefined && !state.done}
  <!-- choice screen -->
  <div class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Take a tour">
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
            <span class="block text-sm font-semibold">Guided by {AGENT_IDENTITY.name} — {AGENT_IDENTITY.role}</span>
            <span class="mt-0.5 block text-xs leading-relaxed text-text/50">
              The agent speaks in a small speech bubble next to each feature, opens screens for you
              and answers questions right there. Nothing else opens over the tour.
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
              A classic walkthrough. Nothing is sent anywhere.
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
  <!-- tour stage: ring + one speech bubble; NO screen dim, the app stays usable -->
  <div class="pointer-events-none fixed inset-0 z-[60]" role="dialog" aria-modal="false" aria-label={step.title}>
    {#if rect}
      <div
        class="absolute rounded-xl ring-2 ring-[var(--brand-accent)] transition-all duration-200"
        style="top:{rect.top}px; left:{rect.left}px; width:{rect.width}px; height:{rect.height}px;
               box-shadow: 0 0 0 4px color-mix(in srgb, var(--brand-accent) 25%, transparent);"
      ></div>
    {/if}
    <div
      class="pointer-events-auto card absolute w-[min(92vw,400px)] p-4 shadow-xl"
      style="top:{cardPos?.top ?? 96}px; left:{cardPos?.left ?? 16}px;"
    >
      {#if tail === "up"}
        <div class="absolute -top-1.5 left-8 size-3 rotate-45 border-l border-t border-text/10 bg-[var(--brand-surface,#fff)]"></div>
      {:else if tail === "down"}
        <div class="absolute -bottom-1.5 left-8 size-3 rotate-45 border-r border-b border-text/10 bg-[var(--brand-surface,#fff)]"></div>
      {/if}

      <div class="flex items-center justify-between gap-2">
        <span class="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
          {mode === "ai" ? "AI tour" : "Tour"} · {(state.step ?? 0) + 1}/{steps.length}
        </span>
        {#if mode === "ai"}
          <span class="truncate rounded-full bg-text/10 px-2 py-0.5 text-[10px] font-medium text-text/60">
            {AGENT_IDENTITY.name} · {AGENT_IDENTITY.role}
          </span>
        {/if}
      </div>

      <h3 class="mt-2 text-sm font-semibold">{step.title}</h3>

      {#if mode === "ai"}
        <!-- provider picker first (Kilo pre-selected, keyless suggested) -->
        {#if showProviderPicker}
          <p class="mt-1 text-xs leading-relaxed text-text/60">
            Pick the AI provider for the tour — Kilo Gateway is pre-selected, and the free
            keyless ones are suggested.
          </p>
          <div class="mt-2 flex flex-wrap gap-1.5" data-tour="tour-provider-picker">
            {#each pickerPresets as p (p.id)}
              <button
                type="button"
                class="rounded-full border px-2.5 py-1 text-[11px] transition-colors
                  {presetIsPicked(p)
                    ? 'border-[var(--brand-accent)] bg-[color-mix(in_srgb,var(--brand-accent)_12%,transparent)] font-medium text-[var(--brand-accent)]'
                    : p.keyless
                      ? 'border-accent/40 text-text/70 hover:bg-text/5'
                      : 'border-text/15 text-text/40 hover:bg-text/5'}"
                title={p.note}
                onclick={() => (pickedPreset = p.id)}
              >
                {p.label}{p.keyless ? " · free" : ""}
                {#if presetIsPicked(p)}{p.id === "kilo-free" ? " · pre-selected" : " · selected"}{/if}
              </button>
            {/each}
          </div>
          <p class="mt-1.5 text-[11px] text-text/40">{presetById(pickedPreset)?.note}</p>
          <div class="mt-2">
            <AiDisclaimer />
          </div>
          <div class="mt-3 flex items-center justify-between">
            <button class="btn btn-ghost px-3 text-xs" onclick={continueWithoutAi}>Continue without AI</button>
            <button class="btn btn-primary px-3 text-xs" disabled={savingProvider} onclick={applyPreset}>
              {savingProvider ? "Starting…" : `Start with ${presetById(pickedPreset)?.label ?? "Kilo"}`}
            </button>
          </div>
        {:else}
          <!-- the agent's speech: narration streams here, questions come back -->
          <div class="mt-1.5 space-y-2">
            {#each bubble.slice(-4) as line, i (bubble.length - 4 + i)}
              {#if line.who === "you"}
                <div class="flex justify-end">
                  <div class="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-3 py-1.5 text-xs leading-relaxed text-white">
                    {line.text}
                  </div>
                </div>
              {:else}
                <div class="max-w-[95%] whitespace-pre-wrap rounded-2xl rounded-bl-md bg-text/10 px-3 py-1.5 text-xs leading-relaxed text-text/90">
                  {line.text || (agentBusy && i === bubble.slice(-4).length - 1 ? "…" : "")}
                  {#if agentBusy && i === bubble.slice(-4).length - 1}
                    <span class="ml-1 inline-block h-2.5 w-1.5 animate-pulse bg-[var(--brand-accent)] align-middle"></span>
                  {/if}
                </div>
              {/if}
            {/each}
            {#if bubble.length === 0 && agentBusy}
              <div class="text-xs text-text/40">{AGENT_IDENTITY.name} is typing…</div>
            {/if}
          </div>
          <form class="mt-2.5 flex items-center gap-2 border-t border-text/10 pt-2.5"
                onsubmit={(e) => { e.preventDefault(); ask(); }}>
            <input class="input text-xs" placeholder="Ask {AGENT_IDENTITY.name} about this stop…"
                   bind:value={askText} disabled={agentBusy} />
            <button type="submit" class="btn btn-primary px-3 text-xs" disabled={!askText.trim() || agentBusy}>
              <Icon name="send" size={14} />
            </button>
          </form>
          <div class="mt-2.5 flex items-center justify-between">
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
        {/if}
      {:else}
        <!-- classic: static copy, same bubble -->
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
      {/if}
    </div>
  </div>
{/if}
