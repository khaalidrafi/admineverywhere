<script module lang="ts">
  export const meta = {
    title: "Completion gauge",
    size: "sm",
    data: { aggregate: "group" },
  };
</script>

<script lang="ts">
  /** CompletionGauge — FR-R008 radial gauge of the leading declared choice:
   *  one arc on a track, sized by that choice's fraction of the whole group
   *  feed. The enum field is schema-resolved ("group" auto-picks a status
   *  enum; pin it with meta.data = { endpoint, field }). The caption follows
   *  the caption law — "grouped from N records", N = the rows the feed
   *  actually consumed (rowCap-capped or not), never a claimed truncation. */
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

  const R = 40;
  const C = 2 * Math.PI * R;

  const groups = $derived(state.status === "ready" && state.result.kind === "groups" ? state.result : null);
  const leading = $derived.by(() => {
    if (!groups) return null;
    // engine order = declared choices first, unseen appended; the max of that
    // order is the leading choice (declared order breaks ties)
    return groups.groups.reduce<{ name: string; value: number } | null>(
      (best, g) => (!best || g.value > best.value ? g : best),
      null,
    );
  });
  const frac = $derived(groups && groups.total > 0 && leading ? leading.value / groups.total : 0);
  const pct = $derived(Math.round(frac * 100));
  const legend = $derived.by(() => {
    if (!groups) return [];
    const shown = groups.groups.slice(0, 5);
    const rest = groups.groups.slice(5).reduce((s, g) => s + g.value, 0);
    return [...shown, ...(rest > 0 ? [{ name: "(other)", value: rest }] : [])];
  });
</script>

{#if state.status === "loading"}
  <div class="skeleton h-32"></div>
{:else if state.status === "empty"}
  <div class="flex h-32 items-center text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="flex h-32 items-center text-sm text-text/40">{state.message}</div>
{:else if groups}
  <div class="flex items-center gap-4">
    <svg viewBox="0 0 100 100" class="h-24 w-24 shrink-0 -rotate-90" role="img"
         aria-label={leading ? `${leading.name} ${pct}% of ${groups.total}` : `no records yet`}>
      <circle cx="50" cy="50" r={R} fill="none" stroke="var(--brand-text)" stroke-opacity="0.08" stroke-width="12" />
      <circle cx="50" cy="50" r={R} fill="none" stroke="var(--brand-primary)"
              stroke-opacity={leading ? 1 : 0} stroke-width="12" stroke-linecap="butt"
              stroke-dasharray="{(frac * C).toFixed(2)} {C.toFixed(2)}" stroke-dashoffset="0" />
      <text x="50" y="50" transform="rotate(90 50 50)" text-anchor="middle" dominant-baseline="central"
            class="fill-text text-[15px] font-semibold" fill="var(--brand-text)">
        {leading ? `${pct}%` : "—"}
      </text>
    </svg>
    <div class="min-w-0">
      <div class="truncate text-sm font-medium text-text/80">{leading?.name ?? "(empty)"}</div>
      <ul class="mt-1 space-y-0.5 text-xs text-text/60">
        {#each legend as g (g.name)}
          <li class="flex items-center gap-2 truncate">
            <span class="truncate">{g.name}</span>
            <span class="ml-auto tabular-nums text-text/50">{g.value}</span>
          </li>
        {/each}
      </ul>
    </div>
  </div>
  <div class="mt-2 text-[10px] text-text/40">{groups.label} · grouped from {groups.total} records</div>
{/if}
