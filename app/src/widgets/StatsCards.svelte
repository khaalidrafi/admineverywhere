<script module>
  export const meta = { title: "Records", size: "lg" };
</script>

<script lang="ts">
  /** StatsCards — record count per model (from pagination count). */
  import { onMount } from "svelte";
  import { app, effectiveConfig, handleApiError } from "../lib/stores.svelte";
  import { listRecords } from "../lib/api";
  import { navigate } from "../lib/router.svelte";

  let counts = $state<Record<string, number | null>>({});
  let failed = $state(false);

  onMount(async () => {
    if (!app.schema) return;
    await Promise.all(
      app.schema.models.map(async (m) => {
        try {
          const page = await listRecords(effectiveConfig(), app.token || null, m, {
            page: 1,
            pageSize: 1,
          });
          counts[m.id] = page.count;
        } catch (err) {
          failed = true;
          handleApiError(err);
        }
      }),
    );
  });
</script>

{#if Object.keys(counts).length}
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
    {#each Object.entries(counts) as [id, n] (id)}
      <button
        class="card group cursor-pointer p-4 text-left transition-transform hover:-translate-y-0.5"
        onclick={() => navigate(`#/m/${id}`)}
      >
        <div class="text-2xl font-semibold text-primary">
          {n === null ? "—" : n}
        </div>
        <div class="mt-0.5 text-xs text-text/50 group-hover:text-text/70">
          {app.schema?.byId[id]?.name ?? id}
        </div>
      </button>
    {/each}
  </div>
{:else}
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
    {#each Array(6) as _, i (i)}
      <div class="skeleton h-20"></div>
    {/each}
  </div>
{/if}

{#if failed}
  <div class="mt-2 text-xs text-text/40">Some counts could not be loaded.</div>
{/if}
