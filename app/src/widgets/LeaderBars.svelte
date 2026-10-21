<script module lang="ts">
  export const meta = {
    title: "Top values",
    size: "sm",
    data: { aggregate: "group" },
  };
</script>

<script lang="ts">
  /** LeaderBars — FR-R008 horizontal bar chart of the biggest enum groups. */
  import { app } from "../lib/stores";
  import { startWidgetFeed, type FeedState } from "../lib/widgets/feed";

  let state = $state<FeedState>({ status: "loading" });
  $effect(() => {
    const schema = $app.schema;
    if (!schema) return;
    return startWidgetFeed(meta.data, (s) => (state = s), schema);
  });

  const groups = $derived(state.status === "ready" && state.result.kind === "groups" ? state.result : null);
  const bars = $derived.by(() => {
    if (!groups) return [];
    const sorted = [...groups.groups].sort((a, b) => b.value - a.value).slice(0, 6);
    const max = sorted[0]?.value ?? 1;
    return sorted.map((g) => ({ ...g, pct: Math.round((g.value / max) * 100) }));
  });
</script>

{#if state.status === "loading"}
  <div class="skeleton h-32"></div>
{:else if state.status === "empty"}
  <div class="flex h-32 items-center justify-center text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="flex h-32 items-center justify-center text-sm text-text/40">{state.message}</div>
{:else if groups}
  <ul class="space-y-2">
    {#each bars as b (b.name)}
      <li>
        <div class="mb-0.5 flex justify-between text-xs text-text/60">
          <span class="truncate">{b.name}</span>
          <span class="tabular-nums">{b.value}</span>
        </div>
        <div class="h-2 w-full overflow-hidden rounded-full bg-text/10">
          <div class="h-full rounded-full bg-primary" style="width: {b.pct}%"></div>
        </div>
      </li>
    {/each}
  </ul>
  <div class="mt-2 text-[10px] text-text/40">{groups.label} · grouped from {groups.total} records</div>
{/if}
