<script module lang="ts">
  export const meta = {
    title: "Activity heat",
    size: "sm",
    // The audit log is the real activity stream; when a backend's log is
    // still empty the component falls back to order volume (see below).
    data: { aggregate: "bucket", days: 35 },
  };
</script>

<script lang="ts">
  /** HeatStrip — FR-R008 GitHub-style strip: one cell per calendar day of a
   *  day-bucketed feed, opacity following volume.
   *
   *  Empty-log fallback (owner blank-dashboard report 2026-11-04): a brand-new
   *  or not-yet-mirroring audit log buckets to an all-zero strip that reads as
   *  "blank". When the AUTO-picked source (no endpoint declared) comes back
   *  all-zero, the feed is restarted once against the shop's order volume —
   *  real data, clearly re-labelled by the feed itself. A PINNED source
   *  (meta.data.endpoint set, e.g. from the Widget studio) is never swapped:
   *  the studio's choice is the user's choice. */
  import { app } from "../lib/stores";
  import { startWidgetFeed, type FeedState } from "../lib/widgets/feed";

  /** The Widget studio overrides meta.data per instance; nothing passed here
   *  means the module's own declaration, byte-for-byte as before. */
  let { data = meta.data }: { data?: unknown } = $props();

  let state = $state<FeedState>({ status: "loading" });
  let source = $state<unknown>(data);
  let fellBack = $state(false);

  $effect(() => {
    const schema = $app.schema;
    if (!schema) return;
    return startWidgetFeed(source, (s) => {
      state = s;
      if (
        !fellBack &&
        s.status === "ready" &&
        s.result.kind === "series" &&
        s.result.values.every((v) => v === 0) &&
        !(data as { endpoint?: string } | undefined)?.endpoint
      ) {
        // audit (or whatever auto-picked) is empty — try real orders once
        fellBack = true;
        source = { ...(data as object), endpoint: "orders", field: "created_at" };
      }
    }, schema);
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
