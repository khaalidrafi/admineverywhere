<script module lang="ts">
  export const meta = {
    title: "Activity heat",
    size: "sm",
    data: { aggregate: "bucket", days: 35 },
  };
</script>

<script lang="ts">
  /** HeatStrip — FR-R008 GitHub-style strip: one cell per calendar day of a
   *  day-bucketed feed, opacity following volume. */
  import { app } from "../lib/stores";
  import { startWidgetFeed, type FeedState } from "../lib/widgets/feed";

  let state = $state<FeedState>({ status: "loading" });
  $effect(() => {
    const schema = $app.schema;
    if (!schema) return;
    return startWidgetFeed(meta.data, (s) => (state = s), schema);
  });

  const series = $derived(state.status === "ready" && state.result.kind === "series" ? state.result : null);
  const max = $derived(series ? Math.max(...series.values, 1) : 1);
</script>

{#if state.status === "loading"}
  <div class="skeleton h-16"></div>
{:else if state.status === "empty"}
  <div class="flex h-16 items-center justify-center text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="flex h-16 items-center justify-center text-sm text-text/40">{state.message}</div>
{:else if series}
  <div>
    <div class="flex flex-wrap gap-1" role="img" aria-label="Daily activity over the last {series.days.length} days">
      {#each series.values as v, i (series.days[i])}
        <span class="inline-block h-3 w-3 rounded-[2px] bg-primary"
              style="opacity: {v === 0 ? 0.08 : 0.15 + (v / max) * 0.85}"
              title="{series.days[i]} — {v}"></span>
      {/each}
    </div>
    <div class="mt-1.5 flex items-center justify-between text-[10px] text-text/40">
      <span>{series.days[0]}</span>
      <span>{series.label}</span>
      <span>today</span>
    </div>
  </div>
{/if}
