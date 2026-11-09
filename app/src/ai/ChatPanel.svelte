<script lang="ts">
  /** AI agent — one floating panel, streaming, OpenAI-compatible tool calling.
   *  Ctrl+K or the spark button opens it. Unconfigured = friendly setup.
   *  The agent runs admin actions through the operator's own session: reads
   *  execute at once, every write waits for a Confirm card in the transcript
   *  (agent.ts law). No cross-turn tool history is replayed — text memory
   *  only, so a fresh turn starts clean.
   */
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import { ai, app, effectiveConfig, loadAiSettings, saveAiSettings, toast } from "../lib/stores";
  import {
    buildSchemaPrompt,
    ChatError,
    streamAssistantTurn,
    systemPrompt,
    type ParsedToolCall,
    type WireMessage,
  } from "../lib/chat";
  import {
    agentSystemAddendum,
    buildAgentTools,
    executeTool,
    humanSummary,
    isDestructive,
    navigateTool,
    toolResultMessage,
    tourGuideAddendum,
    type ToolCtx,
  } from "../lib/agent";

  import { isWebStorage } from "../lib/secrets";
  import {
    tourActive,
    onboardingAgent,
  } from "../lib/tourBus";
  import { stepAgentTurn } from "../lib/onboarding";
  import { AI_PRESETS } from "../lib/aiProviders";
  import AiDisclaimer from "./AiDisclaimer.svelte";
  import Icon from "../components/Icon.svelte";

  const MAX_ROUNDS = 6;

  interface ToolInv {
    id: string;
    name: string;
    args: Record<string, any>;
    destructive: boolean;
    summary: string;
    status: "awaiting" | "running" | "done" | "error" | "denied";
    result?: any;
  }

  type ChatEntry =
    | { kind: "msg"; role: "user" | "assistant"; content: string }
    | { kind: "tool"; inv: ToolInv };

  let open = $state(false);
  let showSettings = $state(false);
  let entries = $state<ChatEntry[]>([]);
  let input = $state("");
  let busy = $state(false);
  let streamError = $state("");
  let scroller: HTMLDivElement | undefined = $state();

  // settings form state
  let baseUrl = $state("");
  let apiKey = $state("");
  let model = $state("");
  let systemPromptText = $state("");

  let abort: AbortController | null = null;
  /** operator gate: call id → resolver of its Confirm/Deny promise */
  const gates = new Map<string, (ok: boolean) => void>();

  const configured = $derived(Boolean($ai.baseUrl && $ai.model));
  /** Guided-tour mode (owner order 2026-11-08): the agent becomes the tour
   *  guide — it may open screens (navigate tool) and narrates each stop. */
  const tourMode = $derived($tourActive);

  $effect(() => {
    baseUrl = $ai.baseUrl;
    apiKey = $ai.apiKey;
    model = $ai.model;
    systemPromptText = $ai.systemPrompt;
    if (!$ai.baseUrl) showSettings = open && true;
  });

  onMount(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        open = !open;
      }
    };
    window.addEventListener("keydown", onKey);
    // agentic onboarding: the overlay asks, this panel narrates (owner order
    // 2026-11-08: the agent drives the app and the user can chat mid-tour)
    onboardingAgent.bindNarrationSender((step) => {
      if (busy) return;
      open = true;
      void sendText(stepAgentTurn(step, get(app).brand.appName));
    });
    return () => window.removeEventListener("keydown", onKey);
  });

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (scroller) scroller.scrollTop = scroller.scrollHeight;
    });
  }

  /* ---- operator gate ---- */

  function decide(callId: string, ok: boolean) {
    const resolve = gates.get(callId);
    if (resolve) {
      gates.delete(callId);
      resolve(ok);
    }
  }

  /** Resolves false for every still-pending gate (Stop pressed). */
  function denyAllPending() {
    for (const [id, resolve] of [...gates]) {
      gates.delete(id);
      resolve(false);
    }
  }

  /* ---- wire helpers ---- */

  /** Cross-turn memory: text bubbles only (tool traffic lives inside its turn). */
  function historyWire(): WireMessage[] {
    return entries
      .filter((e): e is { kind: "msg"; role: "user" | "assistant"; content: string } =>
        e.kind === "msg" && e.content.trim() !== "",
      )
      .slice(-8)
      .map((e) => ({ role: e.role, content: e.content }));
  }

  const toWireCall = (c: ParsedToolCall) => ({
    id: c.id,
    type: "function" as const,
    function: { name: c.name, arguments: JSON.stringify(c.args) },
  });

  /* ---- the agent loop ---- */

  async function runAgentTurn(
    text: string,
    history: WireMessage[],
    ctx: ToolCtx,
    tools: ReturnType<typeof buildAgentTools>,
  ) {
    const wire: WireMessage[] = [
      {
        role: "system",
        content:
          systemPrompt(
            get(app).brand.appName,
            get(app).schema ? buildSchemaPrompt(get(app).schema!) : "no schema loaded",
            get(ai).systemPrompt,
          ) +
          agentSystemAddendum() +
          (tourMode ? tourGuideAddendum() : ""),
      },
      ...history,
      { role: "user", content: text },
    ];

    for (let round = 0; round < MAX_ROUNDS; round++) {
      entries.push({ kind: "msg", role: "assistant", content: "" });
      const liveIdx = entries.length - 1;
      scrollToBottom();

      const turn = await streamAssistantTurn(get(ai), wire, {
        tools,
        signal: abort?.signal,
        onDelta: (delta) => {
          const e = entries[liveIdx];
          if (e.kind === "msg") e.content += delta;
          scrollToBottom();
        },
      });

      if (!turn.toolCalls.length) {
        if (!turn.text) entries.splice(liveIdx, 1); // no empty bubble
        return;
      }

      if (!turn.text) entries.splice(liveIdx, 1); // tools-only turn: drop the shell
      wire.push({ role: "assistant", content: turn.text, tool_calls: turn.toolCalls.map(toWireCall) });

      for (const call of turn.toolCalls) {
        const inv: ToolInv = {
          id: call.id,
          name: call.name,
          args: call.args,
          destructive: isDestructive(call.name),
          summary: humanSummary(call, get(app).schema),
          status: "awaiting",
        };
        entries.push({ kind: "tool", inv });
        scrollToBottom();
        // REACTIVITY LAW: `inv` above is the RAW object — mutating it after the
        // push never reaches the $state proxy, so the card froze on its first
        // painted status ("awaiting"/"running…") forever. All status/result
        // writes below go through entries[idx] — the PROXIED entry.
        const idx = entries.length - 1;
        const card = () => (entries[idx] as { kind: "tool"; inv: ToolInv }).inv;

        if (card().destructive) {
          const ok = await new Promise<boolean>((resolve) => gates.set(call.id, resolve));
          if (!ok) {
            card().status = "denied";
            wire.push(
              toolResultMessage(call, { ok: false, result: { error: "denied by operator" } }),
            );
            continue;
          }
        }

        card().status = "running";
        const res = await executeTool(call, ctx);
        card().status = res.ok ? "done" : "error";
        card().result = res.result;
        wire.push(toolResultMessage(call, res));
        scrollToBottom();
      }
    }
  }

  /** The composer entry point — sends what the operator typed. */
  function send(): void {
    void sendText(input);
  }

  /** One agent turn with any text (the agentic tour narrates through this). */
  async function sendText(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;
    if (!configured) {
      showSettings = true;
      return;
    }
    input = "";
    streamError = "";

    const a = get(app);
    const schema = a.schema ?? null;
    // Tool context carries the APP config (the Django API origin the agent's
    // actions run against) — NOT the AI provider settings. Passing the provider
    // store here made every tool call fail with "no backend is configured"
    // (owner report 2026-11-09): the provider store has no apiUrl at all.
    // effectiveConfig() = the same origin the rest of the app talks to (baked
    // brand host, or the login page's sanitized override).
    const ctx: ToolCtx = { cfg: effectiveConfig(), token: a.token || null, schema };
    let tools = buildAgentTools(schema);
    if (tourMode) {
      // the tour guide can DRIVE the app: open the screens it narrates
      tools = [...tools, navigateTool()];
      ctx.navigateTo = (path: string) => {
        window.location.hash = `#${path}`;
      };
    }
    // history BEFORE the new user bubble lands (runAgentTurn re-appends it)
    const history = historyWire();

    entries.push({ kind: "msg", role: "user", content: text });
    scrollToBottom();

    busy = true;
    abort = new AbortController();
    try {
      await runAgentTurn(text, history, ctx, tools);
    } catch (err: any) {
      if (err?.name === "AbortError") {
        const last = entries[entries.length - 1];
        if (last?.kind === "msg" && last.role === "assistant") last.content += " — stopped.";
      } else {
        streamError = err instanceof ChatError ? err.message : String(err?.message ?? err);
        const last = entries[entries.length - 1];
        if (last?.kind === "msg" && last.role === "assistant" && last.content === "")
          entries.pop();
      }
    } finally {
      denyAllPending();
      busy = false;
      abort = null;
      scrollToBottom();
    }
  }

  function stop() {
    abort?.abort();
    denyAllPending();
  }

  async function saveSettings(e: SubmitEvent) {
    e.preventDefault();
    await saveAiSettings(baseUrl, apiKey, model, systemPromptText);
    toast("success", "AI settings saved");
    showSettings = false;
  }

  /* ---- card helpers ---- */

  function preview(value: any, cap = 420): string {
    try {
      const s = JSON.stringify(value);
      return s.length > cap ? s.slice(0, cap) + " …" : s;
    } catch {
      return String(value);
    }
  }

  const statusLabel: Record<ToolInv["status"], string> = {
    awaiting: "needs your confirm",
    running: "running…",
    done: "done",
    error: "failed",
    denied: "denied",
  };
</script>

<!-- floating launcher -->
{#if !open}
  <button
    class="fixed bottom-[calc(1.5rem_+_env(safe-area-inset-bottom))] right-6 z-40 flex size-13 items-center justify-center rounded-full
      bg-primary text-white shadow-xl shadow-primary/30 transition-transform hover:scale-105"
    title="AI assistant (Ctrl+K)"
    onclick={() => (open = true)}
  >
    <Icon name="chat" size={22} />
  </button>
{/if}

{#if open}
  <div class="fixed bottom-[calc(1.5rem_+_env(safe-area-inset-bottom))] right-6 z-40 flex h-[min(70vh,620px)] w-[min(92vw,400px)] flex-col
    card shadow-2xl overflow-hidden">
    <!-- header -->
    <div class="flex items-center justify-between border-b border-text/10 px-4 py-3">
      <div class="flex items-center gap-2">
        <span class="flex size-7 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Icon name="chat" size={15} />
        </span>
        <span class="text-sm font-semibold">AI Assistant</span>
        {#if configured}
          <span class="rounded-full bg-[color-mix(in_srgb,var(--brand-accent)_15%,transparent)] px-2 py-0.5 text-[10px] font-medium text-[var(--brand-accent)]">
            {$ai.model}
          </span>
        {/if}
      </div>
      <div class="flex items-center gap-1">
        <button class="btn btn-ghost p-2" title="Provider settings" onclick={() => (showSettings = !showSettings)}>
          <Icon name="gear" size={15} />
        </button>
        <button class="btn btn-ghost p-2" title="Close" onclick={() => { if (busy) stop(); open = false; }}>
          <Icon name="x" size={15} />
        </button>
      </div>
    </div>

    {#if showSettings}
      <!-- provider settings -->
      <form class="flex flex-1 flex-col gap-3 overflow-y-auto p-4" onsubmit={saveSettings}>
        <!-- one-click presets — buttons, not inputs. Owner order 2026-11-09
             ("where is the option to set system prompt and other AI settings?")
             added the System-prompt field: the form now keeps FOUR inputs
             (base URL, API key, model, system prompt); presets still fill
             only provider fields and never touch the prompt. -->
        <div class="flex flex-wrap gap-1.5" data-tour="ai-presets">
          {#each AI_PRESETS as p (p.id)}
            <button
              type="button"
              class="rounded-full border px-2.5 py-1 text-[11px] transition-colors
                {p.keyless ? 'border-accent/40 text-[var(--brand-accent)]' : 'border-text/15 text-text/60'}
                hover:bg-text/5"
              title={p.note}
              onclick={() => { baseUrl = p.baseUrl; model = p.model; apiKey = p.apiKey; }}
            >
              {p.label}{p.keyless ? " · free" : ""}
            </button>
          {/each}
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text/60" for="ai-base">Base URL</label>
          <input id="ai-base" class="input" type="url" placeholder="https://api.openai.com/v1"
                 bind:value={baseUrl} required />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text/60" for="ai-key">API key</label>
          <input id="ai-key" class="input" type="password" placeholder="sk-… (stored securely)"
                 bind:value={apiKey} />
          <div class="mt-1 text-[11px] text-text/40">
            {isWebStorage()
              ? "Browser mode: stored in localStorage (packaged app uses the OS keychain)."
              : "Stored in the OS keychain."}
          </div>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text/60" for="ai-model">Model</label>
          <input id="ai-model" class="input" type="text" placeholder="gpt-4o-mini / llama3.2 / …"
                 bind:value={model} required />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text/60" for="ai-prompt">System prompt</label>
          <textarea id="ai-prompt" class="input min-h-20" rows={3}
            placeholder="Optional — how the assistant should behave. Left empty, it introduces itself as your {$app.brand.appName} admin assistant and follows the live model list."
            bind:value={systemPromptText}></textarea>
          <div class="mt-1 text-[11px] text-text/40">
            Replaces the default persona; the model list and safety rules stay.
          </div>
        </div>
        <div class="rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-[11px] text-text/70">
          Works with OpenAI, Groq, Ollama, Mistral, LM Studio &amp; any OpenAI-compatible provider.
          The agent can run admin actions with your own login — writes ask before they land.
        </div>
        <AiDisclaimer />
        <div class="mt-auto flex gap-2">
          <button type="button" class="btn btn-ghost" onclick={() => (showSettings = false)}>Cancel</button>
          <button type="submit" class="btn btn-primary flex-1">Save AI settings</button>
        </div>
      </form>
    {:else if !configured}
      <!-- friendly unconfigured state -->
      <div class="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <span class="flex size-12 items-center justify-center rounded-2xl bg-primary/15 text-primary">
          <Icon name="chat" size={22} />
        </span>
        <div class="text-sm font-semibold">Talk to your data</div>
        <p class="text-xs leading-relaxed text-text/50">
          Connect any OpenAI-compatible provider — OpenAI, Groq, Ollama, LM Studio —
          and let the agent look up, create, update and transition your {$app.brand.appName} records.
        </p>
        <button class="btn btn-primary mt-1" onclick={() => (showSettings = true)}>
          <Icon name="gear" size={15} />
          Set up provider
        </button>
      </div>
    {:else}
      <!-- transcript -->
      <div bind:this={scroller} class="flex-1 space-y-3 overflow-y-auto p-4">
        {#if entries.length === 0}
          <div class="mt-8 text-center text-xs text-text/40">
            Ask anything, or tell the agent to act —
            <span class="text-text/60">"show the 5 latest orders", "mark order 7 as paid"</span>
          </div>
        {/if}
        {#each entries as e, i (i)}
          {#if e.kind === "msg"}
            <div class="flex {e.role === 'user' ? 'justify-end' : 'justify-start'}">
              <div class="max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed
                {e.role === 'user'
                  ? 'rounded-br-md bg-primary text-white'
                  : 'rounded-bl-md bg-text/10 text-text/90'}">
                {e.content || (busy && i === entries.length - 1 ? "…" : "")}
                {#if busy && i === entries.length - 1 && e.role === "assistant"}
                  <span class="ml-1 inline-block h-3 w-1.5 animate-pulse bg-accent align-middle"></span>
                {/if}
              </div>
            </div>
          {:else}
            <!-- tool card -->
            <div class="rounded-xl border p-3 text-xs {e.inv.status === 'awaiting' ? 'border-accent/50' : 'border-text/10'} bg-text/[0.04]">
              <div class="flex items-center gap-2">
                <span class="flex size-5 shrink-0 items-center justify-center rounded-md
                  {e.inv.destructive ? 'bg-accent/20 text-[var(--brand-accent)]' : 'bg-primary/15 text-primary'}">
                  <Icon name={e.inv.destructive ? "gear" : "chat"} size={11} />
                </span>
                <span class="font-medium">{e.inv.summary}</span>
                <span class="ml-auto shrink-0 rounded-full px-2 py-0.5 text-[10px]
                  {e.inv.status === 'awaiting' ? 'bg-accent/15 text-[var(--brand-accent)]' : ''}
                  {e.inv.status === 'running' ? 'bg-primary/15 text-primary' : ''}
                  {e.inv.status === 'done' ? 'bg-primary/10 text-primary' : ''}
                  {e.inv.status === 'error' ? 'bg-text/10 text-text/70' : ''}
                  {e.inv.status === 'denied' ? 'bg-text/10 text-text/50' : ''}">
                  {statusLabel[e.inv.status]}
                </span>
              </div>

              <details class="mt-1.5" open={e.inv.status === "awaiting"}>
                <summary class="cursor-pointer select-none text-[10px] text-text/40">{e.inv.name}</summary>
                <pre class="mt-1 overflow-x-auto rounded-md bg-text/[0.06] p-2 text-[10px] leading-snug">{preview(e.inv.args)}</pre>
              </details>

              {#if e.inv.status === "done" && e.inv.result !== undefined}
                <pre class="mt-1.5 max-h-24 overflow-y-auto rounded-md bg-text/[0.06] p-2 text-[10px] leading-snug">{preview(e.inv.result)}</pre>
              {:else if e.inv.status === "error"}
                <pre class="mt-1.5 overflow-x-auto rounded-md bg-text/[0.06] p-2 text-[10px] leading-snug text-text/70">{preview(e.inv.result)}</pre>
              {/if}

              {#if e.inv.status === "awaiting"}
                <div class="mt-2 flex justify-end gap-2">
                  <button class="btn btn-ghost px-3 py-1 text-[11px]"
                          onclick={() => decide(e.inv.id, false)}>Deny</button>
                  <button class="btn btn-primary px-3 py-1 text-[11px]"
                          onclick={() => decide(e.inv.id, true)}>Confirm</button>
                </div>
              {/if}
            </div>
          {/if}
        {/each}
        {#if streamError}
          <div class="rounded-lg border border-[color-mix(in_srgb,var(--brand-text)_40%,transparent)] bg-[color-mix(in_srgb,var(--brand-surface)_40%,transparent)] px-3 py-2 text-xs text-[var(--brand-text)]">
            {streamError}
          </div>
        {/if}
      </div>

      <!-- composer -->
      <AiDisclaimer compact />
      <form
        class="flex items-center gap-2 border-t border-text/10 p-3"
        onsubmit={(e) => { e.preventDefault(); send(); }}
      >
        <input
          class="input"
          placeholder="Ask about your data…"
          bind:value={input}
          disabled={busy}
        />
        {#if busy}
          <button type="button" class="btn btn-ghost px-3" title="Stop" onclick={stop}>
            <Icon name="x" size={16} />
          </button>
        {:else}
          <button type="submit" class="btn btn-primary px-3" disabled={!input.trim()}>
            <Icon name="send" size={16} />
          </button>
        {/if}
      </form>
    {/if}
  </div>
{/if}
