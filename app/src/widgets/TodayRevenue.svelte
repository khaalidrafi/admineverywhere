<script module lang="ts">
  export const meta = {
    title: "Today — 7-day window",
    size: "sm",
    data: { aggregate: "bucket", days: 7 },
  };
</script>

<script lang="ts">
  /** TodayRevenue — FR-R008 latest-day tile: the LAST bucket of a small
   *  day-window, drawn big over a bar sparkline of the whole window behind
   *  it. Model and date field are schema-resolved (no hard-coded names); the
   *  feed engine owns the window (days, clamped to [2, 366]) and the rowCap.
   *  No fetched count is printed — the caption law binds any widget that
   *  would claim "N records", so this tile prints only what the bucket is:
   *  the feed label and the window it sits in. */
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

  const W = 70;
  const H = 40;

  const series = $derived(state.status === "ready" && state.result.kind === "series" ? state.result : null);
  const latest = $derived(series ? series.values[series.values.length - 1] : null);
  const flat = $derived(series ? !series.values.some((v) => v > 0) : false);
  const bars = $derived.by(() => {
    if (!series) return [];
    const max = Math.max(...series.values, 1);
    const step = W / series.values.length;
    return series.values.map((v, i) => ({
      day: series.days[i],
      v,
      x: Number((i * step + 1).toFixed(2)),
      w: Number((step - 2).toFixed(2)),
      h: Number(((v / max) * (H - 4)).toFixed(2)),
      last: i === series.values.length - 1,
    }));
  });
</script>

{#if state.status === "loading"}
  <div class="skeleton h-24"></div>
{:else if state.status === "empty"}
  <div class="flex h-24 items-center text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="flex h-24 items-center text-sm text-text/40">{state.message}</div>
{:else if series}
  <div class="relative h-24 overflow-hidden rounded-lg bg-text/5">
    <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" class="absolute inset-x-0 bottom-0 h-full w-full"
         role="img" aria-label="Records per day, last {series.days.length} days — today: {latest}">
      {#each bars as b (b.day)}
        <rect x={b.x} y={H - b.h} width={b.w} height={b.h} fill="var(--brand-primary)"
              fill-opacity={b.last ? 0.55 : 0.22}>
          <title>{b.day} — {b.v}</title>
        </rect>
      {/each}
      {#if flat}
        <line x1="0" y1={H - 1} x2={W} y2={H - 1} stroke="var(--brand-text)" stroke-opacity="0.15" />
      {/if}
    </svg>
    <div class="relative flex h-full flex-col justify-end p-3">
      <span class="text-3xl font-semibold leading-none tabular-nums">{latest}</span>
      <span class="mt-1.5 text-xs text-text/60">today · {series.label} · last {series.days.length} days</span>
    </div>
  </div>
{/if}
