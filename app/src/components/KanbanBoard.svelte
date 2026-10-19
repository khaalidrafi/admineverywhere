<script lang="ts">
  /** Kanban board: columns per enum value, drag between columns fires transition API.
   *  409 Conflict → card snaps back + error banner shows reason.
   *  Keyboard a11y: move-to-column menu when drag unavailable.
   */
  import { get } from "svelte/store";
  import { app, effectiveConfig, toast } from "../lib/stores";
  import { transitionRecord } from "../lib/api";
  import { getLegalTransitions, getStatusField } from "../lib/statusTransitions";
  import Icon from "./Icon.svelte";
  import type { ModelSpec, RecordRow } from "../lib/types";

  let {
    model,
    rows,
    ontransition,
  }: {
    model: ModelSpec;
    rows: RecordRow[];
    ontransition?: (row: RecordRow, targetStatus: string) => Promise<void>;
  } = $props();

  const statusField = $derived(getStatusField(model.id));
  const states = $derived(statusField ? (model.byName[statusField]?.choices ?? []) : []);
  
  // Group rows by status
  const columns = $derived(
    states.map((state) => ({
      state,
      records: rows.filter((r) => r[statusField!] === state),
    }))
  );

  let dragging = $state<RecordRow | null>(null);
  let dragSource = $state<string | null>(null);

  function handleDragStart(e: DragEvent, row: RecordRow, fromState: string) {
    dragging = row;
    dragSource = fromState;
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(row.id));
    }
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "move";
    }
  }

  async function handleDrop(e: DragEvent, targetState: string) {
    e.preventDefault();
    if (!dragging || !dragSource || dragSource === targetState) {
      dragging = null;
      dragSource = null;
      return;
    }

    const row = dragging;
    const from = dragSource;
    dragging = null;
    dragSource = null;

    // Check if transition is legal
    const legal = getLegalTransitions(model.id, from);
    if (!legal.includes(targetState)) {
      toast("error", `Cannot transition from ${from} to ${targetState}`);
      return;
    }

    // Call the transition handler (which calls the API)
    if (ontransition) {
      await ontransition(row, targetState);
    }
  }

  // Keyboard accessibility: move-to-column menu
  let menuOpen = $state<RecordRow | null>(null);

  function openMoveMenu(row: RecordRow) {
    menuOpen = row;
  }

  function closeMoveMenu() {
    menuOpen = null;
  }

  async function moveViaKeyboard(row: RecordRow, targetState: string) {
    const currentStatus = row[statusField!];
    if (currentStatus === targetState) {
      closeMoveMenu();
      return;
    }

    const legal = getLegalTransitions(model.id, currentStatus);
    if (!legal.includes(targetState)) {
      toast("error", `Cannot transition from ${currentStatus} to ${targetState}`);
      closeMoveMenu();
      return;
    }

    if (ontransition) {
      await ontransition(row, targetState);
    }
    closeMoveMenu();
  }
</script>

<div class="flex gap-4 overflow-x-auto pb-4">
  {#each columns as column (column.state)}
    <div
      class="flex min-w-[280px] flex-col rounded-lg border border-text/10 bg-surface/50"
      ondragover={handleDragOver}
      ondrop={(e) => handleDrop(e, column.state)}
    >
      <div class="flex items-center justify-between border-b border-text/10 px-4 py-3">
        <h3 class="font-semibold capitalize">{column.state}</h3>
        <span class="rounded-full bg-text/10 px-2 py-0.5 text-xs font-medium">
          {column.records.length}
        </span>
      </div>

      <div class="flex-1 space-y-2 p-3">
        {#each column.records as row (row.id)}
          <div
            class="card cursor-move border-l-4 border-l-primary shadow-sm transition-shadow hover:shadow-md"
            draggable="true"
            ondragstart={(e) => handleDragStart(e, row, column.state)}
            role="listitem"
            aria-label="{model.name} {row[model.labelField] ?? row.id}, status {column.state}"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="flex-1">
                <p class="font-medium">
                  {row[model.labelField] ?? row.id}
                </p>
                {#if row.id !== undefined}
                  <p class="text-xs text-text/50">#{row.id}</p>
                {/if}
              </div>
              <button
                class="btn btn-ghost btn-sm p-1"
                onclick={() => openMoveMenu(row)}
                aria-label="Move {row[model.labelField] ?? row.id} to another column"
                title="Move to column"
              >
                <Icon name="more" size={16} />
              </button>
            </div>
          </div>

          {#if menuOpen?.id === row.id}
            <div class="card absolute right-0 top-8 z-10 min-w-[200px] shadow-lg">
              <div class="border-b border-text/10 px-3 py-2">
                <p class="text-xs font-semibold uppercase text-text/50">Move to</p>
              </div>
              <div class="p-1">
                {#each states as state}
                  {#if state !== column.state}
                    <button
                      class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-text/5"
                      onclick={() => moveViaKeyboard(row, state)}
                    >
                      <span class="capitalize">{state}</span>
                    </button>
                  {/if}
                {/each}
              </div>
              <div class="border-t border-text/10 p-1">
                <button
                  class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-text/50 hover:bg-text/5"
                  onclick={closeMoveMenu}
                >
                  Cancel
                </button>
              </div>
            </div>
          {/if}
        {/each}

        {#if column.records.length === 0}
          <p class="py-8 text-center text-sm text-text/40">No records</p>
        {/if}
      </div>
    </div>
  {/each}
</div>

{#if states.length === 0}
  <div class="flex h-64 flex-col items-center justify-center gap-2 text-text/50">
    <Icon name="alert" />
    <p>This model has no status field configured for kanban view.</p>
  </div>
{/if}
