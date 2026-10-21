<script module lang="ts">
  /** The CRUD page is ONE parameterised declaration: every schema model reuses
   *  it, and the sidebar's model links come from the schema, not from nav. */
  export const meta = {
    title: "Model",
    path: "/m/:modelId/:recordId?",
    nav: false,
    order: 200,
  };
</script>

<script lang="ts">
  /** Schema-driven model CRUD: search + paginated table + create/edit modal. */
  import { get } from "svelte/store";
  import { app, claims, effectiveConfig, handleApiError, toast } from "../lib/stores";
  import { deleteRecord, fetchAudit, fetchCsv, fetchHistory, listRecords, patchRecord, retrieveRecord, transitionRecord } from "../lib/api";
  import { downloadCsv, exportFileName, tableToCsv } from "../lib/csv";
  import { actionFailureReason, actions, actionsFor, type RegisteredAction } from "../lib/actions/index";
  import { findAuditModel } from "../lib/rbac";
  import { getStatusField } from "../lib/statusTransitions";
  import { cardLabel, planMove, resolveAxis } from "../lib/kanban";
  import { navigate } from "../lib/router";
  import { debounce } from "../lib/utils";
  import DataTable from "../components/DataTable.svelte";
  import KanbanBoard from "../components/KanbanBoard.svelte";
  import RecordForm from "../components/RecordForm.svelte";
  import Icon from "../components/Icon.svelte";
  import type { AuditEntry, FieldSpec, RecordRow } from "../lib/types";

  let { modelId, recordId }: { modelId: string; recordId?: string } = $props();

  const model = $derived($app.schema?.byId[modelId]);
  const listPath = $derived(model?.listPath ?? "");
  /** FR-R004: a board exists only for a model with a DECLARED kanban axis
   *  (lib/kanban.ts) — the axis is never guessed from the field name, so a
   *  model without one simply never shows the toggle. */
  const axis = $derived(resolveAxis(model));
  const BOARD_PAGE_SIZE = 100;

  let rows = $state<RecordRow[]>([]);
  let count = $state(0);
  let page = $state(1);
  let hasNext = $state(false);
  let hasPrev = $state(false);
  let loading = $state(true);
  let view = $state<"table" | "kanban">("table");
  let busyId = $state<string | number | null>(null);
  let exporting = $state(false);
  let searchInput = $state("");
  let searchTerm = $state("");
  let formOpen = $state(false);
  let editing = $state<RecordRow | null>(null);
  let reqId = 0; // drop stale responses
  let historyView = $state<RecordRow | null>(null);
  let history = $state<Array<{id: number; from_status: string; to_status: string; actor: string | null; created_at: string}>>([]);
  let audit = $state<AuditEntry[]>([]);
  let pendingAction = $state<{ action: RegisteredAction; rows: RecordRow[] } | null>(null);
  let actionInput = $state("");

  const recordActions = $derived(model ? actionsFor(model.id, "record", actions, $claims) : []);
  const bulkActions = $derived(model ? actionsFor(model.id, "bulk", actions, $claims) : []);

  const pages = $derived(count ? Math.ceil(count / (rows.length || 10)) : 1);

  const onSearch = debounce((value: string) => {
    searchTerm = value;
    page = 1;
  }, 300);

  async function load() {
    if (!model) return;
    const mine = ++reqId;
    loading = true;
    try {
      const p = await listRecords(effectiveConfig(), get(app).token || null, model, {
        page,
        search: searchTerm,
        // a board groups one page of records into columns; ten rows spread over
        // four columns says nothing, so the board asks for a wider page
        pageSize: view === "kanban" ? BOARD_PAGE_SIZE : undefined,
      });
      if (mine !== reqId) return; // a newer request superseded this one
      rows = p.results;
      count = p.count;
      hasNext = Boolean(p.next);
      hasPrev = Boolean(p.previous);
    } catch (err) {
      if (mine === reqId) handleApiError(err);
    } finally {
      if (mine === reqId) loading = false;
    }
  }

  // reload when model / page / search changes
  $effect(() => {
    if (model) void load();
  });

  // an axis declared for one model says nothing about the next, and the shell
  // renders pages without remounting them (FR R-006), so a model switch resets
  // the query state here rather than relying on a component recreate
  $effect(() => {
    void modelId;
    view = "table";
    page = 1;
    searchInput = "";
    searchTerm = "";
  });

  // deep-link #/m/<model>/<recordId> -> open that record for editing
  $effect(() => {
    if (recordId && model) {
      const rid = recordId;
      recordId = undefined; // consume once
      retrieveRecord(effectiveConfig(), get(app).token || null, model, rid)
        .then((row) => {
          editing = row;
          formOpen = true;
        })
        .catch((err) => handleApiError(err));
      navigate(`#/m/${modelId}`);
    }
  });

  async function onDelete(row: RecordRow) {
    if (!model || row.id === undefined) return;
    const label = row[model.labelField] ?? row.id;
    if (!confirm(`Delete ${model.name} "${label}"? This cannot be undone.`)) return;
    try {
      await deleteRecord(effectiveConfig(), get(app).token || null, model, row.id as any);
      toast("success", `${model.name} deleted`);
      if (rows.length === 1 && page > 1) page -= 1;
      else void load();
    } catch (err) {
      handleApiError(err);
    }
  }

  function openCreate() {
    editing = null;
    formOpen = true;
  }

  function openEdit(row: RecordRow) {
    editing = row;
    formOpen = true;
  }

  function onSaved() {
    formOpen = false;
    void load();
  }

  function clearSearch() {
    searchInput = "";
    onSearch("");
  }

  /** FR-R005 layer 1 — the table's own data, client-side, no server call.
   *  DataTable hands over the columns it actually rendered, so the file cannot
   *  disagree with what the user is looking at, and it carries the CURRENT
   *  page only (?search= and pagination already decided that). */
  function onExportVisible(columns: FieldSpec[]) {
    if (!model) return;
    if (rows.length === 0) {
      toast("info", "Nothing to export — this page has no records.");
      return;
    }
    const name = exportFileName(model.name, searchTerm ? `search-${searchTerm}` : `page-${page}`);
    if (!downloadCsv(name, tableToCsv(columns, rows))) {
      toast("error", "This environment cannot start a download.");
      return;
    }
    toast("success", `Exported ${rows.length} row${rows.length === 1 ? "" : "s"} of ${columns.length} columns to ${name}`);
  }

  /** FR-R005 layer 2 — the flattened line-level export, only when the schema
   *  documents it (model.exportPath comes from normalizeOpenAPI, never from a
   *  guessed path). The WHOLE collection is the server's answer, so the bytes
   *  are handed to downloadCsv untouched; it strips a duplicate BOM, not data. */
  async function onServerExport() {
    if (!model?.exportPath || exporting) return;
    exporting = true;
    try {
      const file = await fetchCsv(
        effectiveConfig(),
        get(app).token || null,
        model.exportPath,
        exportFileName(model.name, "line"),
      );
      if (!downloadCsv(file.filename, file.text)) {
        toast("error", "This environment cannot start a download.");
        return;
      }
      toast("success", `Full export saved as ${file.filename}`);
    } catch (err) {
      handleApiError(err);
    } finally {
      exporting = false;
    }
  }

  async function onTransition(row: RecordRow, targetStatus: string) {
    if (!model || row.id === undefined) return;
    const statusField = getStatusField(model.id);
    if (!statusField) return;
    
    try {
      const updated = await transitionRecord(
        effectiveConfig(),
        get(app).token || null,
        model,
        row.id as any,
        targetStatus,
      );
      toast("success", `Transitioned to ${targetStatus}`);
      // Update the row in place
      rows = rows.map((r) => (r.id === row.id ? updated : r));
    } catch (err: any) {
      // 409 Conflict: surface the reason
      if (err.status === 409 && err.detail?.reason) {
        toast("error", err.detail.reason);
      } else {
        handleApiError(err);
      }
    }
  }

  /** A kanban drop: `planMove` decides the call (and refuses an illegal or
   *  no-op move before anything hits the network). A lifecycle axis fires the
   *  R-001 transition endpoint; a free enum fires a PATCH of exactly the axis
   *  field — never a whole-row PUT, which is how accidental derived writes
   *  happen (docs/independent-enums.md §3 guardrail 1). */
  async function onBoardMove(row: RecordRow, columnKey: string) {
    if (!model || !axis || row.id === undefined) return;
    const plan = planMove(axis, row, columnKey);
    if (!plan.ok) {
      toast("error", plan.reason);
      void load(); // the board was showing a stale state
      return;
    }
    busyId = row.id;
    try {
      const cfg = effectiveConfig();
      const token = get(app).token || null;
      const updated = plan.via === "transition"
        ? await transitionRecord(cfg, token, model, row.id as any, plan.column)
        : await patchRecord(cfg, token, model, row.id as any, plan.body);
      rows = rows.map((r) => (r.id === updated.id ? updated : r));
      toast("success", `${cardLabel(model, updated)} → ${plan.column}`);
    } catch (err: any) {
      if (err.status === 409 && err.detail?.reason) toast("error", err.detail.reason);
      else handleApiError(err);
      void load();
    } finally {
      busyId = null;
    }
  }

  /** The record sub-view: R-001 lifecycle history (oldest-first) plus R-003
   *  audit entries (newest-first) for this record. History is only fetched for
   *  a trail the API actually documents (model.historyPath); the audit log is
   *  open to any model, so a plain record still shows what custom actions did
   *  to it. */
  async function showHistory(row: RecordRow) {
    if (!model || row.id === undefined) return;
    historyView = row;
    history = [];
    audit = [];
    try {
      if (model.historyPath) {
        history = await fetchHistory(effectiveConfig(), get(app).token || null, model, row.id as any);
      }
    } catch (err) {
      handleApiError(err);
      historyView = null;
      return;
    }
    // A backend that has not documented the R-003 audit model has no log to
    // show — skip the read entirely (fetchAudit refuses a guessed path), so
    // the sub-view degrades to the lifecycle half instead of failing.
    const logModel = findAuditModel(get(app).schema);
    if (logModel) {
      try {
        audit = (await fetchAudit(effectiveConfig(), get(app).token || null, {
          objectType: model.singular,
          objectId: row.id,
          path: logModel.listPath,
        })).results;
      } catch (err: any) {
        if (err.status !== 404) handleApiError(err);
      }
    }
  }

  function closeHistory() {
    historyView = null;
    history = [];
    audit = [];
  }

  /** Drop-in action entry point (FR-R003). meta.confirm is a FE-only guard —
   *  the server re-validates every field regardless. */
  function requestAction(action: RegisteredAction, targetRows: RecordRow[]) {
    if (!action.meta.confirm && !action.meta.input) {
      void fireAction(action, targetRows, undefined);
      return;
    }
    actionInput = "";
    pendingAction = { action, rows: targetRows };
  }

  async function fireAction(
    action: RegisteredAction,
    targetRows: RecordRow[],
    input: string | undefined,
  ) {
    if (!model) return;
    pendingAction = null;
    try {
      const entries = await action.meta.handler({
        cfg: effectiveConfig(),
        token: get(app).token || null,
        model,
        rows: targetRows,
        input,
      });
      const noun = entries.length === 1 ? "audit entry" : "audit entries";
      toast("success", `${action.meta.label}: ${entries.length} ${noun} written`);
      await load();
      if (historyView && targetRows.some((row) => row.id === historyView?.id)) await showHistory(historyView);
    } catch (err: any) {
      const reason = actionFailureReason(err);
      if (reason) toast("error", `${action.meta.label} rejected: ${reason}`);
      else handleApiError(err);
    }
  }
</script>

{#if !model}
  <div class="flex h-64 flex-col items-center justify-center gap-2 text-text/50">
    <Icon name="alert" />
    <p>Unknown model "{modelId}".</p>
    <button class="btn btn-ghost" onclick={() => navigate("#/")}>Back to dashboard</button>
  </div>
{:else}
  <div class="mx-auto max-w-6xl">
    <!-- header -->
    <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold">{model.name}</h1>
        <p class="text-sm text-text/50">{model.fields.length} fields · {listPath}</p>
      </div>
      <div class="flex items-center gap-2">
        {#if axis}
          <div class="flex items-center gap-1 rounded-brand border border-text/10 p-1" role="group"
               aria-label="View for {model.name}">
            <button class="btn {view === 'table' ? 'btn-primary' : 'btn-ghost'} px-3 py-1.5 text-xs"
                    aria-pressed={view === "table"} onclick={() => (view = "table")}>
              <Icon name="table" size={14} /> Table
            </button>
            <button class="btn {view === 'kanban' ? 'btn-primary' : 'btn-ghost'} px-3 py-1.5 text-xs"
                    aria-pressed={view === "kanban"} onclick={() => (view = "kanban")}>
              <Icon name="grid" size={14} /> Kanban
            </button>
          </div>
        {/if}
        <button class="btn btn-primary" onclick={openCreate}>
          <Icon name="plus" size={16} />
          New {model.name}
        </button>
      </div>
    </div>

    <!-- search + count -->
    <div class="mb-4 flex items-center gap-3">
      <div class="relative max-w-xs flex-1">
        <span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text/40">
          <Icon name="search" size={16} />
        </span>
        <input
          class="input pl-9"
          placeholder="Search {model.name.toLowerCase()}…"
          bind:value={searchInput}
          oninput={(e) => onSearch((e.target as HTMLInputElement).value)}
        />
        {#if searchInput}
          <button class="absolute right-2 top-1/2 -translate-y-1/2 text-text/40 hover:text-text"
                  onclick={clearSearch}>
            <Icon name="x" size={14} />
          </button>
        {/if}
      </div>
      <span class="text-sm text-text/50">
        {loading ? "…" : `${count} record${count === 1 ? "" : "s"}`}
      </span>
    </div>

    {#if view === "kanban" && axis}
      <KanbanBoard {model} {rows} {axis} {loading} busy={busyId}
                   onmove={onBoardMove} onedit={openEdit} />
    {:else}
      <DataTable {model} {rows} {loading} onedit={openEdit} ondelete={onDelete} ontransition={onTransition} onshowhistory={showHistory}
                 actions={recordActions} bulkActions={bulkActions} onaction={requestAction}
                 onexport={onExportVisible} onserverexport={model.exportPath ? onServerExport : undefined}
                 {exporting} />
    {/if}

    <!-- pagination -->
    <div class="mt-4 flex items-center justify-between text-sm">
      <span class="text-text/50">Page {page}{pages > 1 ? ` of ${pages}` : ""}</span>
      <div class="flex gap-2">
        <button class="btn btn-ghost px-3 py-1.5" disabled={!hasPrev || loading}
                onclick={() => (page -= 1)}>
          <Icon name="left" size={14} /> Prev
        </button>
        <button class="btn btn-ghost px-3 py-1.5" disabled={!hasNext || loading}
                onclick={() => (page += 1)}>
          Next <Icon name="right" size={14} />
        </button>
      </div>
    </div>
  </div>

  {#if historyView && model}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onclick={closeHistory}>
      <div class="card max-h-[80vh] w-full max-w-2xl overflow-y-auto" onclick={(e) => e.stopPropagation()}>
        <div class="mb-4 flex items-center justify-between border-b border-text/10 pb-3">
          <h2 class="text-lg font-semibold">
            History & audit for {model.name} #{historyView.id}
          </h2>
          <button class="btn btn-ghost" onclick={closeHistory}>
            <Icon name="x" size={20} />
          </button>
        </div>
        {#if history.length === 0}
          <p class="text-text/50">
            {model.historyPath
              ? "No lifecycle history."
              : `This API does not document a lifecycle trail at ${model.detailPath}history/.`}
          </p>
        {:else}
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-text/10 text-left text-xs uppercase tracking-wider text-text/40">
                <th class="px-3 py-2">Transition</th>
                <th class="px-3 py-2">Actor</th>
                <th class="px-3 py-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {#each history as entry}
                <tr class="border-b border-text/5">
                  <td class="px-3 py-2">
                    {entry.from_status ? `${entry.from_status} → ${entry.to_status}` : `created as ${entry.to_status}`}
                  </td>
                  <td class="px-3 py-2">{entry.actor ?? "system"}</td>
                  <td class="px-3 py-2 text-text/60">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}

        <h3 class="mt-6 mb-2 text-sm font-semibold uppercase tracking-wider text-text/50">
          Audit log
        </h3>
        {#if audit.length === 0}
          <p class="text-text/50">No audit entries for this record.</p>
        {:else}
          <ul class="space-y-2">
            {#each audit as entry (entry.id)}
              <li class="rounded-brand border border-text/10 px-3 py-2 text-sm">
                <div class="flex items-center justify-between gap-3">
                  <span class="font-medium">{entry.summary}</span>
                  <span class="shrink-0 text-xs text-text/50">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </div>
                <p class="text-xs text-text/50">
                  {entry.action} · {entry.actor ?? "system"}
                </p>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  {/if}

  {#if pendingAction}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
         onclick={() => (pendingAction = null)}>
      <div class="card w-full max-w-md" onclick={(e) => e.stopPropagation()}>
        <h2 class="mb-2 text-lg font-semibold">{pendingAction.action.meta.label}</h2>
        <p class="mb-4 text-sm text-text/60">
          {pendingAction.action.meta.confirm ?? `Apply to ${pendingAction.rows.length} record(s)?`}
        </p>
        {#if pendingAction.action.meta.input}
          <label class="mb-4 block text-sm">
            <span class="mb-1 block text-text/60">{pendingAction.action.meta.input}</span>
            <input class="input" bind:value={actionInput}
                   placeholder={pendingAction.action.meta.input} />
          </label>
        {/if}
        <div class="flex justify-end gap-2">
          <button class="btn btn-ghost" onclick={() => (pendingAction = null)}>Cancel</button>
          <button class="btn btn-primary"
                  disabled={pendingAction.action.meta.input ? !actionInput.trim() : false}
                  onclick={() => fireAction(pendingAction!.action, pendingAction!.rows, actionInput.trim() || undefined)}>
            {pendingAction.action.meta.label}
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if formOpen}
    <RecordForm {model} record={editing} onclose={() => (formOpen = false)} onsaved={onSaved} />
  {/if}
{/if}
