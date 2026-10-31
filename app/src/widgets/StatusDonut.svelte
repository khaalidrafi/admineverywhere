<script module lang="ts">
  export const meta = {
    title: "Share by status",
    size: "sm",
    data: { aggregate: "group" },
  };
</script>

<script lang="ts">
  /** StatusDonut — FR-R008 donut over an enum-grouped feed. The enum field is
   *  schema-resolved; pin it with meta.data = { endpoint, field }. */
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

  const groups = $derived(state.status === "ready" && state.result.kind === "groups" ? state.result : null);
  const R = 42;
  const C = 2 * Math.PI * R;
  const slices = $derived.by(() => {
    if (!groups || groups.total <= 0) return [];
    const shown = groups.groups.slice(0, 5);
    const restValue = groups.groups.slice(5).reduce((s, g) => s + g.value, 0);
    const parts = [...shown.map((g) => ({ name: g.name, value: g.value })),
      ...(restValue > 0 ? [{ name: "(other)", value: restValue }] : [])];
    let acc = 0;
    return parts.map((p, i) => {
      const frac = p.value / groups.total;
      const slice = { ...p, dash: `${(frac * C).toFixed(2)} ${C.toFixed(2)}`, offset: (-acc * C).toFixed(2), i };
      acc += frac;
      return slice;
    });
  });
</script>

{#if state.status === "loading"}
  <div class="skeleton h-36"></div>
{:else if state.status === "empty"}
  <div class="flex h-36 items-center justify-center text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="flex h-36 items-center justify-center text-sm text-text/40">{state.message}</div>
{:else if groups}
  <div class="flex items-center gap-4">
    <svg viewBox="0 0 100 100" class="h-24 w-24 shrink-0 -rotate-90" role="img" aria-label="Distribution by {groups.label}">
      <circle cx="50" cy="50" r={R} fill="none" stroke="var(--brand-text)" stroke-opacity="0.08" stroke-width="12" />
      {#each slices as s (s.name)}
        <circle cx="50" cy="50" r={R} fill="none"
                stroke={s.name === "(other)" ? "var(--brand-text)" : "var(--brand-primary)"}
                stroke-opacity={s.name === "(other)" ? 0.3 : Math.max(0.25, 1 - s.i * 0.18)}
                stroke-width="12" stroke-dasharray={s.dash} stroke-dashoffset={s.offset} />
      {/each}
      <text x="50" y="50" transform="rotate(90 50 50)" text-anchor="middle" dominant-baseline="central"
            class="fill-text text-[16px] font-semibold" fill="var(--brand-text)">{groups.total}</text>
    </svg>
    <ul class="min-w-0 space-y-1 text-xs text-text/70">
      {#each slices as s (s.name)}
        <li class="flex items-center gap-2 truncate">
          <span class="inline-block h-2 w-2 shrink-0 rounded-full bg-primary"
                style="opacity: {s.name === '(other)' ? 0.3 : Math.max(0.25, 1 - s.i * 0.18)}"></span>
          <span class="truncate">{s.name}</span>
          <span class="ml-auto tabular-nums text-text/50">{s.value}</span>
        </li>
      {/each}
    </ul>
  </div>
{/if}
