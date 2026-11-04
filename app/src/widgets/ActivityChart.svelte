<script module>
  export const meta = { title: "Activity — last 14 days", size: "lg" };
</script>

<script lang="ts">
  /** ActivityChart — hand-rolled SVG line chart of records per day.
   *  Picks the first model with a datetime field (drives off schema only —
   *  no hardcoded model names), buckets the first pages of data by day.
   *
   *  Empty-source fallback (owner blank-dashboard report 2026-11-04): the
   *  candidates are tried in rank order until one has a non-zero day in the
   *  window — an all-zero first source (a fresh audit log) no longer renders
   *  as a blank flat line while real activity sits in another model. */
  import { get } from "svelte/store";
  import { app, effectiveConfig, handleApiError } from "../lib/stores";
  import { listRecords } from "../lib/api";
  import type { AdminSchema, ModelSpec, RecordRow } from "../lib/types";

  const DAYS = 14;
  let buckets = $state<number[]>([]);
  let modelName = $state("");
  let fieldName = $state("");
  let state = $state<"loading" | "ready" | "empty" | "error">("loading");
  let started = false;

  function pickModels(schema: AdminSchema): { model: ModelSpec; field: string }[] {
    // prefer auto timestamps (readOnly) on fields named created_at, then any
    // readOnly datetime — manually-set datetimes (e.g. Category.created_at)
    // usually describe old backfill, not recent activity
    const rank = (f: { type: string; name: string; readOnly: boolean }) =>
      (f.type === "datetime" ? 0 : 99) + (f.readOnly ? 0 : 10) + (f.name === "created_at" ? 0 : 1);
    const scored: { model: ModelSpec; field: string; score: number }[] = [];
    for (const m of schema.models) {
      for (const f of m.fields) {
        if (f.type !== "datetime") continue;
        scored.push({ model: m, field: f.name, score: rank(f) });
      }
    }
    return scored
      .sort((a, b) => a.score - b.score)
      .slice(0, 3)
      .map(({ model, field }) => ({ model, field }));
  }

  // widgets can mount before the schema finishes loading -> react to it
  $effect(() => {
    const schema = $app.schema;
    if (!schema || started) return;
    started = true;
    const candidates = pickModels(schema);
    if (!candidates.length) {
      state = "empty";
      return;
    }
    void tryCandidate(candidates, 0);
  });

  async function tryCandidate(candidates: { model: ModelSpec; field: string }[], index: number) {
    await load(candidates[index]);
    if (state === "error") return; // a failed walk must stay an error — never downgraded
    const anyActivity = buckets.some((v) => v > 0);
    if (!anyActivity && index + 1 < candidates.length) {
      await tryCandidate(candidates, index + 1);
      return;
    }
    state = "ready";
  }

  async function load(picked: { model: ModelSpec; field: string }): Promise<RecordRow[]> {
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
        const p = await listRecords(effectiveConfig(), get(app).token || null, picked.model, { page });
        rows = rows.concat(p.results);
        if (!p.next) break;
      }
      for (const row of rows) {
        const k = String(row[picked.field] ?? "").slice(0, 10);
        if (byDay.has(k)) byDay.set(k, (byDay.get(k) ?? 0) + 1);
      }
      buckets = keys.map((k) => byDay.get(k) ?? 0);
      return rows;
    } catch (err) {
      handleApiError(err);
      state = "error";
      return [];
    }
  }

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

  const area = $derived((points ? `${points} L${W - PAD},${H - PAD} L${PAD},${H - PAD} Z` : ""));
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
