<script lang="ts">
  /** Kanban board (FR-R004) — groups the loaded records by a DECLARED enum axis
   *  and turns a drop into exactly one API call: the R-001 transition endpoint
   *  for a lifecycle field, a single-field PATCH for a free enum. Column set
   *  and order come from `axis`, never from a guess about the data.
   *
   *  Drag is a mouse-only gesture, so every move also has a keyboard path: the
   *  per-card "Move to" select lists the same columns a drop would accept and
   *  disables the rest. Nothing a pointer can do is unavailable to a keyboard. */
  import { boardColumns, cardLabel, reachableColumns, UNASSIGNED, type ResolvedAxis } from "../lib/kanban";
  import type { ModelSpec, RecordRow } from "../lib/types";

  let {
    model,
    rows,
    axis,
    loading = false,
    busy = null,
    onmove,
    onedit,
  }: {
    model: ModelSpec;
    rows: RecordRow[];
    axis: ResolvedAxis;
    loading?: boolean;
    /** id of the record with a move in flight — its controls lock until it lands */
    busy?: string | number | null;
    onmove: (row: RecordRow, column: string) => void;
    onedit?: (row: RecordRow) => void;
  } = $props();

  const columns = $derived(boardColumns(rows, axis));
  const secondary = $derived(
    model.fields
      .filter((f) => f.name !== axis.field && f.type !== "json" && f.name !== model.labelField)
      .slice(0, 2),
  );

  let dragging = $state<RecordRow | null>(null);

  function reachable(row: RecordRow): string[] {
    return reachableColumns(axis, row[axis.field]);
  }

  /** A card is draggable only when it has somewhere to go, and the unassigned
   *  bucket is display-only. */
  function columnClass(accepts: boolean, canDrop: boolean, blocked: boolean): string {
    const base = "flex w-72 shrink-0 flex-col rounded-brand border";
    if (canDrop) return `${base} border-dashed border-primary/60 bg-primary/5`;
    if (blocked || !accepts) return `${base} border-text/10 opacity-40`;
    return `${base} border-text/10`;
  }

  function cardClass(draggableCard: boolean, isDragging: boolean, isBusy: boolean): string {
    const base = "rounded-brand border border-text/10 bg-surface/40 px-3 py-2 text-sm shadow-sm";
    if (isBusy) return `${base} cursor-progress opacity-60`;
    if (isDragging) return `${base} cursor-grabbing opacity-50`;
    return draggableCard ? `${base} cursor-grab` : `${base}`;
  }

  function startDrag(event: DragEvent, row: RecordRow) {
    dragging = row;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(row.id ?? ""));
    }
  }

  function endDrag() {
    dragging = null;
  }

  function drop(event: DragEvent, colKey: string, allowed: boolean) {
    event.preventDefault();
    const row = dragging;
    endDrag();
    if (!row || !allowed) return;
    onmove(row, colKey);
  }
</script>

<div class="card overflow-hidden">
  <div class="flex flex-wrap items-center justify-between gap-2 border-b border-text/10 px-4 py-2 text-xs text-text/50">
    <span>
      Board by <span class="font-medium text-text/80">{axis.field}</span>
      · {axis.via === "transition" ? "moves go through the lifecycle API" : "moves are a one-field patch"}
    </span>
    <span>Drag a card to a highlighted column, or pick a target in its “Move to” list.</span>
  </div>

  <div class="flex gap-3 overflow-x-auto p-4">
    {#each columns as col (col.key)}
      {@const targets = dragging ? reachable(dragging) : []}
      {@const canDrop = col.accepts && dragging !== null && targets.includes(col.key)}
      {@const blocked = dragging !== null && col.accepts && !targets.includes(col.key)}
      <section
        class={columnClass(col.accepts, canDrop, blocked)}
        aria-label={`${col.label} column, ${col.rows.length} record${col.rows.length === 1 ? "" : "s"}`}
        ondragover={(event: DragEvent) => {
          if (!canDrop) return;
          event.preventDefault();
          if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
        }}
        ondrop={(event: DragEvent) => drop(event, col.key, canDrop)}
      >
        <header class="flex items-center justify-between gap-2 px-3 py-2">
          <h3 class="text-sm font-semibold {col.key === UNASSIGNED ? 'text-text/50' : 'text-text/80'}">
            {col.label}
          </h3>
          <span class="rounded-full bg-text/10 px-2 py-0.5 text-xs text-text/60">{col.rows.length}</span>
        </header>

        <div class="flex flex-col gap-2 px-2 pb-3">
          {#if loading}
            {#each Array(2) as _, skeletonIndex (skeletonIndex)}
              <div class="skeleton h-20 rounded-brand"></div>
            {/each}
          {:else if col.rows.length === 0}
            <p class="px-2 py-6 text-center text-xs text-text/30">
              {canDrop ? "Drop here" : "Empty"}
            </p>
          {:else}
            {#each col.rows as row (row.id ?? JSON.stringify(row))}
              {@const cardBusy = busy !== null && busy !== undefined && String(row.id) === String(busy)}
              {@const cardDraggable = col.accepts && !cardBusy && reachable(row).length > 0}
              <article
                class={cardClass(cardDraggable, dragging !== null && String(dragging.id) === String(row.id), cardBusy)}
                draggable={cardDraggable}
                ondragstart={(event: DragEvent) => { if (cardDraggable) startDrag(event, row); }}
                ondragend={endDrag}
              >
                <button
                  type="button"
                  class="block w-full text-left font-medium text-primary hover:underline"
                  onclick={() => onedit?.(row)}
                  title="Open {cardLabel(model, row)}"
                >
                  {cardLabel(model, row)}
                </button>
                {#each secondary as field (field.name)}
                  {#if row[field.name] !== null && row[field.name] !== undefined && row[field.name] !== ""}
                    <p class="mt-1 text-xs text-text/50">
                      {field.name.replace(/_/g, " ")}: {String(row[field.name])}
                    </p>
                  {/if}
                {/each}
                <label class="mt-2 flex items-center gap-2 text-xs text-text/50">
                  <span aria-hidden="true">Move to</span>
                  <select
                    class="input h-7 flex-1 px-2 py-0 text-xs"
                    disabled={cardBusy || !col.accepts}
                    value=""
                    aria-label="Move {cardLabel(model, row)} to another column"
                    onchange={(event) => {
                      const select = event.target as HTMLSelectElement;
                      const target = select.value;
                      select.value = "";
                      if (target) onmove(row, target);
                    }}
                  >
                    <option value="">—</option>
                    {#each axis.columns as option (option)}
                      <option value={option} disabled={!reachable(row).includes(option)}>
                        {option}{reachable(row).includes(option) ? "" : " (not allowed)"}
                      </option>
                    {/each}
                  </select>
                </label>
              </article>
            {/each}
          {/if}
        </div>
      </section>
    {/each}
  </div>
</div>
