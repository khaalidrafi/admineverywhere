<script lang="ts">
  /** Schema-driven table: first 6 fields as columns, edit/delete actions. */
  import Icon from "./Icon.svelte";
  import { formatCell } from "../lib/utils";
  import type { FieldSpec, ModelSpec, RecordRow } from "../lib/types";
  import { getLegalTransitions, getStatusField, hasLifecycle } from "../lib/statusTransitions";

  let {
    model,
    rows,
    loading = false,
    onedit,
    ondelete,
    ontransition,
    onshowhistory,
  }: {
    model: ModelSpec;
    rows: RecordRow[];
    loading?: boolean;
    onedit: (row: RecordRow) => void;
    ondelete: (row: RecordRow) => void;
    ontransition?: (row: RecordRow, targetStatus: string) => void;
    onshowhistory?: (row: RecordRow) => void;
  } = $props();

  const columns = $derived(model.fields.filter((f) => f.type !== "json").slice(0, 6));
  const statusField = $derived(getStatusField(model.id));
  const hasLifecycleGovernance = $derived(hasLifecycle(model.id));
</script>

<div class="card overflow-hidden">
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-text/10 text-left text-xs uppercase tracking-wider text-text/40">
          {#each columns as col (col.name)}
            <th class="px-4 py-3 font-medium">{col.name.replace(/_/g, " ")}</th>
          {/each}
          <th class="px-4 py-3 text-right font-medium">Actions</th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          {#each Array(6) as _, r (r)}
            <tr class="border-b border-text/5">
              {#each columns as col (col.name)}
                <td class="px-4 py-3"><div class="skeleton h-4 w-24"></div></td>
              {/each}
              <td class="px-4 py-3"><div class="skeleton ml-auto h-4 w-16"></div></td>
            </tr>
          {/each}
        {:else if rows.length === 0}
          <tr>
            <td colspan={columns.length + 1} class="px-4 py-12 text-center text-text/40">
              No records found{#if rows.length === 0 && model}. Create the first one above.{/if}
            </td>
          </tr>
        {:else}
          {#each rows as row (row.id ?? JSON.stringify(row))}
            <tr class="border-b border-text/5 transition-colors hover:bg-text/5">
              {#each columns as col (col.name)}
                <td class="max-w-[22rem] px-4 py-3">
                  {@render cell(col, row[col.name], row)}
                </td>
              {/each}
              <td class="px-4 py-3">
                <div class="flex justify-end gap-1">
                  {#if hasLifecycleGovernance && statusField && row[statusField]}
                    {#each getLegalTransitions(model.id, row[statusField]) as targetStatus}
                      <button
                        class="btn btn-primary p-2 text-xs"
                        title="Transition to {targetStatus}"
                        onclick={() => ontransition?.(row, targetStatus)}
                      >
                        → {targetStatus}
                      </button>
                    {/each}
                    <button
                      class="btn btn-ghost p-2"
                      title="Show history"
                      onclick={() => onshowhistory?.(row)}
                    >
                      <Icon name="history" size={15} />
                    </button>
                  {/if}
                  <button
                    class="btn btn-ghost p-2"
                    title="Edit"
                    onclick={() => onedit(row)}
                  >
                    <Icon name="pencil" size={15} />
                  </button>
                  <button
                    class="btn btn-ghost p-2 hover:!border-red-500/40 hover:text-red-400"
                    title="Delete"
                    onclick={() => ondelete(row)}
                  >
                    <Icon name="trash" size={15} />
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
</div>

{#snippet cell(col: FieldSpec, value: any, row: RecordRow)}
  {#if value === null || value === undefined}
    <span class="text-text/30">—</span>
  {:else if col.type === "boolean"}
    <span class="inline-flex items-center gap-2">
      <span class="inline-block size-2 rounded-full {value ? 'bg-emerald-500' : 'bg-text/25'}"></span>
      {value ? "Yes" : "No"}
    </span>
  {:else if col.type === "enum"}
    <span class="inline-block rounded-full {col.name === statusField ? 'bg-primary/15 text-primary' : 'bg-accent/15 text-accent'} px-2.5 py-0.5 text-xs font-medium">
      {formatCell(value)}
    </span>
  {:else if col.type === "fk"}
    <span class="text-text/60" title="foreign key">#{formatCell(value)}</span>
  {:else if col.name === model.labelField}
    <span class="font-medium text-primary">{formatCell(value)}</span>
  {:else}
    <span class="text-text/80">{formatCell(value)}</span>
  {/if}
{/snippet}
