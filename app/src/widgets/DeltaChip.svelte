<script module lang="ts">
  export const meta = {
    title: "7-day change",
    size: "sm",
    data: { aggregate: "delta", days: 7, pollInterval: 60_000 },
  };
</script>

<script lang="ts">
  /** DeltaChip — FR-R008 momentum chip: this window vs the previous one.
   *  The only built-in that polls (every 60 s, floor-clamped in feed.ts) —
   *  proof the pollInterval leg of the contract works on a live feed. */
  import { app } from "../lib/stores";
  import { startWidgetFeed, type FeedState } from "../lib/widgets/feed";

  /** The Widget studio overrides meta.data per instance; nothing passed here
   *  means the module's own declaration, byte-for-byte as before. */
  let { data = meta.data }: { data?: unknown } = $props();

  let state = $state<FeedState>({ status: "loading" });
  $effect(() => {
    const schema = $app.schema;
    if (!schema) return;
    return startWidgetFeed(data, (s) => (state = s), schema);
  });

  const delta = $derived(state.status === "ready" && state.result.kind === "delta" ? state.result : null);
  const dir = $derived(!delta ? "flat" : delta.pct === null ? (delta.current > 0 ? "up" : "flat") : delta.pct > 0 ? "up" : delta.pct < 0 ? "down" : "flat");
</script>

{#if state.status === "loading"}
  <div class="skeleton h-10 w-32 rounded-full"></div>
{:else if state.status === "empty"}
  <div class="text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="text-sm text-text/40">{state.message}</div>
{:else if delta}
  <div class="flex items-baseline gap-2">
    <span class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm font-semibold
                 {dir === 'up' ? 'bg-primary/15 text-primary' : dir === 'down' ? 'bg-text/10 text-text/60' : 'bg-text/10 text-text/50'}"
          role="status">
      {#if dir === "up"}▲{:else if dir === "down"}▼{:else}•{/if}
      {#if delta.pct === null}
        {delta.current > 0 ? "new" : "—"}
      {:else}
        {Math.abs(Math.round(delta.pct))}%
      {/if}
    </span>
    <span class="text-xs text-text/50">
      {delta.current} vs {delta.previous} · {delta.label} · refreshes every 60s
    </span>
  </div>
{/if}
