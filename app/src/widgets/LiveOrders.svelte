<script module lang="ts">
  export const meta = {
    title: "Live orders",
    size: "sm",
    data: { aggregate: "count", pollInterval: 15_000 },
  };
</script>

<script lang="ts">
  /** LiveOrders — FR-R008 stat tile on a 15 s poll (floor-clamped in feed.ts).
   *  The ONLY timer in this widget is the feed engine's: startWidgetFeed arms
   *  it and the $effect cleanup below disarms it, so unmount cannot leave an
   *  orphan poller. The "live" pulse is pure CSS keyframes — no animation
   *  timer is armed, so there is nothing extra to clear (the gapMount law:
   *  any timer a widget DOES arm must die in the same $effect cleanup). */
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

  const count = $derived(state.status === "ready" && state.result.kind === "count" ? state.result : null);
</script>

{#if state.status === "loading"}
  <div class="skeleton h-16 w-36 rounded-xl"></div>
{:else if state.status === "empty"}
  <div class="flex min-h-16 items-center text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="flex min-h-16 items-center text-sm text-text/40">{state.message}</div>
{:else if count}
  <div class="flex items-center justify-between gap-3">
    <!-- role="status": the tile re-announces itself on every poll tick -->
    <span class="text-4xl font-semibold leading-none tabular-nums" role="status"
          aria-label="{count.label}: {count.value ?? "—"} right now">{count.value ?? "—"}</span>
    <span class="live-dot shrink-0" aria-hidden="true"></span>
  </div>
  <div class="mt-2 text-xs text-text/50">{count.label} · refreshes every 15s</div>
{/if}

<style>
  /* Brand-only pulse: no keyframe color outside --brand-*, no JS timer. */
  .live-dot {
    width: 0.625rem;
    height: 0.625rem;
    border-radius: 9999px;
    background: var(--brand-primary);
    animation: live-pulse 2s ease-in-out infinite;
  }
  @keyframes live-pulse {
    0%,
    100% {
      opacity: 1;
      transform: scale(1);
    }
    50% {
      opacity: 0.35;
      transform: scale(0.8);
    }
  }
</style>
