<script lang="ts">
  /** AI chat — one floating panel, streaming, OpenAI-compatible.
   *  Ctrl+K or the spark button opens it. Unconfigured = friendly setup.
   *  No tool calling, no history persistence (v2 material).
   */
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import { ai, app, loadAiSettings, saveAiSettings, toast } from "../lib/stores";
  import { ChatError, streamChatCompletion, systemPrompt, type ChatMessage } from "../lib/chat";
  import { schemaSummary } from "../lib/openapi";
  import { isWebStorage } from "../lib/secrets";
  import Icon from "../components/Icon.svelte";

  let open = $state(false);
  let showSettings = $state(false);
  let messages = $state<ChatMessage[]>([]);
  let input = $state("");
  let streaming = $state(false);
  let streamError = $state("");
  let scroller: HTMLDivElement | undefined = $state();

  // settings form state
  let baseUrl = $state("");
  let apiKey = $state("");
  let model = $state("");

  let abort: AbortController | null = null;

  const configured = $derived(Boolean($ai.baseUrl && $ai.model));

  $effect(() => {
    baseUrl = $ai.baseUrl;
    apiKey = $ai.apiKey;
    model = $ai.model;
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
    return () => window.removeEventListener("keydown", onKey);
  });

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (scroller) scroller.scrollTop = scroller.scrollHeight;
    });
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    if (!configured) {
      showSettings = true;
      return;
    }
    input = "";
    streamError = "";

    const a = get(app);
    const outgoing: ChatMessage[] = [
      {
        role: "system",
        content: systemPrompt(a.brand.appName, a.schema ? schemaSummary(a.schema) : "no schema loaded"),
      },
      ...messages.slice(-8), // short memory, no persistence by design
      { role: "user", content: text },
    ];
    messages.push({ role: "user", content: text });
    messages.push({ role: "assistant", content: "" });
    scrollToBottom();

    streaming = true;
    abort = new AbortController();
    try {
      await streamChatCompletion(
        get(ai),
        outgoing,
        (delta) => {
          messages[messages.length - 1].content += delta;
          scrollToBottom();
        },
        abort.signal,
      );
    } catch (err: any) {
      if (err?.name === "AbortError") {
        messages[messages.length - 1].content += " — stopped.";
      } else {
        streamError = err instanceof ChatError ? err.message : String(err?.message ?? err);
        if (messages[messages.length - 1]?.content === "") messages.pop();
      }
    } finally {
      streaming = false;
      abort = null;
      scrollToBottom();
    }
  }

  function stop() {
    abort?.abort();
  }

  async function saveSettings(e: SubmitEvent) {
    e.preventDefault();
    await saveAiSettings(baseUrl, apiKey, model);
    toast("success", "AI provider saved");
    showSettings = false;
  }
</script>

<!-- floating launcher -->
{#if !open}
  <button
    class="fixed bottom-6 right-6 z-40 flex size-13 items-center justify-center rounded-full
      bg-primary text-white shadow-xl shadow-primary/30 transition-transform hover:scale-105"
    title="AI assistant (Ctrl+K)"
    onclick={() => (open = true)}
  >
    <Icon name="chat" size={22} />
  </button>
{/if}

{#if open}
  <div class="fixed bottom-6 right-6 z-40 flex h-[min(70vh,620px)] w-[min(92vw,400px)] flex-col
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
        <button class="btn btn-ghost p-2" title="Close" onclick={() => (open = false)}>
          <Icon name="x" size={15} />
        </button>
      </div>
    </div>

    {#if showSettings}
      <!-- provider settings -->
      <form class="flex flex-1 flex-col gap-3 overflow-y-auto p-4" onsubmit={saveSettings}>
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
        <div class="rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-[11px] text-text/70">
          Works with OpenAI, Groq, Ollama, Mistral, LM Studio &amp; any OpenAI-compatible provider.
        </div>
        <div class="mt-auto flex gap-2">
          <button type="button" class="btn btn-ghost" onclick={() => (showSettings = false)}>Cancel</button>
          <button type="submit" class="btn btn-primary flex-1">Save provider</button>
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
          and ask questions about your {$app.brand.appName} models.
        </p>
        <button class="btn btn-primary mt-1" onclick={() => (showSettings = true)}>
          <Icon name="gear" size={15} />
          Set up provider
        </button>
      </div>
    {:else}
      <!-- messages -->
      <div bind:this={scroller} class="flex-1 space-y-3 overflow-y-auto p-4">
        {#if messages.length === 0}
          <div class="mt-8 text-center text-xs text-text/40">
            Ask anything about your data —
            <span class="text-text/60">"which models exist?", "what fields does Product have?"</span>
          </div>
        {/if}
        {#each messages as m, i (i)}
          <div class="flex {m.role === 'user' ? 'justify-end' : 'justify-start'}">
            <div class="max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed
              {m.role === 'user'
                ? 'rounded-br-md bg-primary text-white'
                : 'rounded-bl-md bg-text/10 text-text/90'}">
              {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
              {#if streaming && i === messages.length - 1 && m.role === "assistant"}
                <span class="ml-1 inline-block h-3 w-1.5 animate-pulse bg-accent align-middle"></span>
              {/if}
            </div>
          </div>
        {/each}
        {#if streamError}
          <div class="rounded-lg border border-[color-mix(in_srgb,var(--brand-text)_40%,transparent)] bg-[color-mix(in_srgb,var(--brand-surface)_40%,transparent)] px-3 py-2 text-xs text-[var(--brand-text)]">
            {streamError}
          </div>
        {/if}
      </div>

      <!-- composer -->
      <form
        class="flex items-center gap-2 border-t border-text/10 p-3"
        onsubmit={(e) => { e.preventDefault(); send(); }}
      >
        <input
          class="input"
          placeholder="Ask about your data…"
          bind:value={input}
          disabled={streaming}
        />
        {#if streaming}
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
