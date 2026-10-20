<script lang="ts">
  /** Schema-driven table: first 6 fields as columns, edit/delete + drop-in actions. */
  import Icon from "./Icon.svelte";
  import { formatCell } from "../lib/utils";
  import type { FieldSpec, ModelSpec, RecordRow } from "../lib/types";
  import { getLegalTransitions, getStatusField, hasLifecycle } from "../lib/statusTransitions";
  import type { RegisteredAction } from "../lib/actions/index";

  let {
    model,
    rows,
    loading = false,
    onedit,
    ondelete,
    ontransition,
    onshowhistory,
    actions = [],
    bulkActions = [],
    onaction,
  }: {
    model: ModelSpec;
    rows: RecordRow[];
    loading?: boolean;
    onedit: (row: RecordRow) => void;
    ondelete: (row: RecordRow) => void;
    ontransition?: (row: RecordRow, targetStatus: string) => void;
    onshowhistory?: (row: RecordRow) => void;
    /** record-scope actions applicable to this model (FR-R003 registry) */
    actions?: RegisteredAction[];
    bulkActions?: RegisteredAction[];
    onaction?: (action: RegisteredAction, rows: RecordRow[]) => void;
  } = $props();

  const columns = $derived(model.fields.filter((f) => f.type !== "json").slice(0, 6));
  const statusField = $derived(getStatusField(model.id));
  const hasLifecycleGovernance = $derived(hasLifecycle(model.id));

  /** Bulk selection holds ids, not row objects, so a page reload cannot leave
   *  a stale row reference behind — selectedRows re-reads from the live rows. */
  let selectedIds = $state<Set<string | number>>(new Set());
  const selectedRows = $derived(rows.filter((row) => row.id !== undefined && selectedIds.has(row.id)));
  const allSelected = $derived(rows.length > 0 && selectedRows.length === rows.length);

  function toggleRow(row: RecordRow) {
    const next = new Set(selectedIds);
    if (row.id === undefined) return;
    if (next.has(row.id)) next.delete(row.id);
    else next.add(row.id);
    selectedIds = next;
  }

  function toggleAll() {
    selectedIds = allSelected ? new Set() : new Set(rows.map((row) => row.id).filter((id) => id !== undefined));
  }
</script>

<div class="card overflow-hidden">
  {#if bulkActions.length > 0 && selectedRows.length > 0}
    <div class="flex flex-wrap items-center gap-2 border-b border-text/10 bg-text/5 px-4 py-2 text-sm">
      <span class="text-text/60">{selectedRows.length} selected</span>
      {#each bulkActions as bulk (bulk.id)}
        <button class="btn btn-primary px-3 py-1.5 text-xs" onclick={() => onaction?.(bulk, selectedRows)}>
          {bulk.meta.label}
        </button>
      {/each}
      <button class="btn btn-ghost px-3 py-1.5 text-xs" onclick={() => (selectedIds = new Set())}>Clear</button>
    </div>
  {/if}
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-text/10 text-left text-xs uppercase tracking-wider text-text/40">
          {#if bulkActions.length > 0}
            <th class="w-8 px-4 py-3">
              <input type="checkbox" class="accent-primary" checked={allSelected} onchange={toggleAll}
                     aria-label="Select all rows" />
            </th>
          {/if}
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
              {#if bulkActions.length > 0}<td class="px-4 py-3"></td>{/if}
              {#each columns as col (col.name)}
                <td class="px-4 py-3"><div class="skeleton h-4 w-24"></div></td>
              {/each}
              <td class="px-4 py-3"><div class="skeleton ml-auto h-4 w-16"></div></td>
            </tr>
          {/each}
        {:else if rows.length === 0}
          <tr>
            <td colspan={columns.length + 1 + (bulkActions.length > 0 ? 1 : 0)} class="px-4 py-12 text-center text-text/40">
              No records found{#if rows.length === 0 && model}. Create the first one above.{/if}
            </td>
          </tr>
        {:else}
          {#each rows as row (row.id ?? JSON.stringify(row))}
            <tr class="border-b border-text/5 transition-colors hover:bg-text/5">
              {#if bulkActions.length > 0}
                <td class="px-4 py-3">
                  <input type="checkbox" class="accent-primary"
                         checked={row.id !== undefined && selectedIds.has(row.id)}
                         onchange={() => toggleRow(row)} aria-label="Select row" />
                </td>
              {/if}
              {#each columns as col (col.name)}
                <td class="max-w-[22rem] px-4 py-3">
                  {@render cell(col, row[col.name], row)}
                </td>
              {/each}
              <td class="px-4 py-3">
                <div class="flex justify-end gap-1">
                  {#each actions as recordAction (recordAction.id)}
                    <button
                      class="btn btn-ghost p-2 text-xs"
                      title={recordAction.meta.label}
                      onclick={() => onaction?.(recordAction, [row])}
                    >
                      {recordAction.meta.label}
                    </button>
                  {/each}
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
                  {/if}
                  <button
                    class="btn btn-ghost p-2"
                    title="History & audit"
                    onclick={() => onshowhistory?.(row)}
                  >
                    <Icon name="history" size={15} />
                  </button>
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
