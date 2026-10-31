<script module lang="ts">
  export const meta = {
    title: "Trend — daily volume",
    size: "lg",
    data: { aggregate: "bucket", days: 30 },
  };
</script>

<script lang="ts">
  /** TrendArea — FR-R008 area chart over a day-bucketed feed. Model and date
   *  field are schema-resolved (no hard-coded names); add `endpoint`/`field`
   *  to meta.data to pin the source. */
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

  const W = 560;
  const H = 150;
  const PAD = 8;

  const series = $derived(state.status === "ready" && state.result.kind === "series" ? state.result : null);
  const geom = $derived.by(() => {
    if (!series) return null;
    const max = Math.max(...series.values, 1);
    const stepX = (W - PAD * 2) / (series.values.length - 1 || 1);
    const pts = series.values.map((v, i) => ({
      x: PAD + i * stepX,
      y: H - PAD - (v / max) * (H - PAD * 2),
      v,
    }));
    const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    return { line, area: `${line} L${W - PAD},${H - PAD} L${PAD},${H - PAD} Z`, pts, max };
  });
</script>

{#if state.status === "loading"}
  <div class="skeleton h-40"></div>
{:else if state.status === "empty"}
  <div class="flex h-40 items-center justify-center text-sm text-text/40">{state.reason}.</div>
{:else if state.status === "error"}
  <div class="flex h-40 items-center justify-center text-sm text-text/40">{state.message}</div>
{:else if series && geom}
  <div>
    <svg viewBox="0 0 {W} {H}" class="w-full" role="img" aria-label="Records per day, last {series.days.length} days">
      <defs>
        <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--brand-primary)" stop-opacity="0.45" />
          <stop offset="1" stop-color="var(--brand-primary)" stop-opacity="0.04" />
        </linearGradient>
      </defs>
      {#if series.values.some((v) => v > 0)}
        <path d={geom.area} fill="url(#trend-fill)" />
        <path d={geom.line} fill="none" stroke="var(--brand-primary)" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round" />
        {#each geom.pts as p, i (i)}
          {#if p.v > 0}
            <circle cx={p.x} cy={p.y} r="2.5" fill="var(--brand-accent)">
              <title>{series.days[i]} — {p.v}</title>
            </circle>
          {/if}
        {/each}
      {:else}
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="var(--brand-text)" stroke-opacity="0.15" />
      {/if}
    </svg>
    <div class="mt-1 flex justify-between text-[10px] text-text/40">
      <span>{series.days[0]}</span>
      <span>{series.label}</span>
      <span>today</span>
    </div>
  </div>
{/if}
