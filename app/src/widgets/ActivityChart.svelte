<script module>
  export const meta = { title: "Activity — last 14 days", size: "lg" };
</script>

<script lang="ts">
  /** ActivityChart — hand-rolled SVG line chart of records per day.
   *  Picks the first model with a datetime field (drives off schema only —
   *  no hardcoded model names), buckets the first pages of data by day.
   */
  import { onMount } from "svelte";
  import { app, effectiveConfig, handleApiError } from "../lib/stores.svelte";
  import { listRecords } from "../lib/api";
  import type { ModelSpec, RecordRow } from "../lib/types";

  const DAYS = 14;
  let buckets = $state<number[]>([]);
  let modelName = $state("");
  let fieldName = $state("");
  let state = $state<"loading" | "ready" | "empty" | "error">("loading");

  function pickModel(): { model: ModelSpec; field: string } | null {
    for (const m of app.schema?.models ?? []) {
      const dt = m.fields.find((f) => f.type === "datetime" && f.name === "created_at")
        ?? m.fields.find((f) => f.type === "datetime");
      if (dt) return { model: m, field: dt.name };
    }
    return null;
  }

  function dayKey(iso: string): string {
    return String(iso).slice(0, 10);
  }

  onMount(async () => {
    const picked = pickModel();
    if (!picked) {
      state = "empty";
      return;
    }
    modelName = picked.model.name;
    fieldName = picked.field;
    const today = new Date();
    const keys: string[] = [];
    for (let d = DAYS - 1; d >= 0; d--) {
      const date = new Date(today);
      date.setDate(today.getDate() - d);
      keys.push(date.toISOString().slice(0, 10));
    }
    const byDay = new Map<string, number>(keys.map((k) => [k, 0]));

    try {
      let rows: RecordRow[] = [];
      for (let page = 1; page <= 3; page++) {
        const p = await listRecords(effectiveConfig(), app.token || null, picked.model, { page });
        rows = rows.concat(p.results);
        if (!p.next) break;
      }
      for (const row of rows) {
        const k = dayKey(String(row[picked.field] ?? ""));
        if (byDay.has(k)) byDay.set(k, (byDay.get(k) ?? 0) + 1);
      }
      buckets = keys.map((k) => byDay.get(k) ?? 0);
      state = "ready";
    } catch (err) {
      handleApiError(err);
      state = "error";
    }
  });

  const W = 560;
  const H = 160;
  const PAD = 8;

  const points = $derived.by(() => {
    if (!buckets.length || Math.max(...buckets) === 0) return "";
    const max = Math.max(...buckets, 1);
    const stepX = (W - PAD * 2) / (buckets.length - 1 || 1);
    return buckets
      .map((v, i) => {
        const x = PAD + i * stepX;
        const y = H - PAD - (v / max) * (H - PAD * 2);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  });

  const area = $derived(
    points ? `${points} L${W - PAD},${H - PAD} L${PAD},${H - PAD} Z` : "",
  );
</script>

{#if state === "loading"}
  <div class="skeleton h-40"></div>
{:else if state === "empty"}
  <div class="flex h-40 items-center justify-center text-sm text-text/40">
    No timestamped model found in the schema.
  </div>
{:else if state === "error"}
  <div class="flex h-40 items-center justify-center text-sm text-text/40">
    Could not load activity data.
  </div>
{:else}
  <div>
    <svg viewBox="0 0 {W} {H}" class="w-full" role="img"
         aria-label="Records per day over the last 14 days">
      <defs>
        <linearGradient id="activity-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--brand-primary)" stop-opacity="0.35" />
          <stop offset="1" stop-color="var(--brand-primary)" stop-opacity="0.02" />
        </linearGradient>
      </defs>
      {#if points}
        <path d={area} fill="url(#activity-fill)" />
        <path d={points} fill="none" stroke="var(--brand-primary)" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round" />
        {#each buckets as v, i (i)}
          {#if v > 0}
            <circle
              cx={PAD + (i * (W - PAD * 2)) / (buckets.length - 1 || 1)}
              cy={H - PAD - (v / Math.max(...buckets, 1)) * (H - PAD * 2)}
              r="3" fill="var(--brand-accent)">
              <title>{v} on day -{DAYS - 1 - i}</title>
            </circle>
          {/if}
        {/each}
      {:else}
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="var(--brand-text)"
              stroke-opacity="0.15" />
      {/if}
    </svg>
    <div class="mt-1 flex justify-between text-[10px] text-text/40">
      <span>-{DAYS}d</span>
      <span>{modelName} by {fieldName.replace(/_/g, " ")} · first pages only</span>
      <span>today</span>
    </div>
  </div>
{/if}
