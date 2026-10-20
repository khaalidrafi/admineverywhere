<script lang="ts">
  /** Schema-driven model CRUD: search + paginated table + create/edit modal. */
  import { get } from "svelte/store";
  import { app, effectiveConfig, handleApiError, toast } from "../lib/stores";
  import { deleteRecord, fetchAudit, fetchHistory, listRecords, retrieveRecord, transitionRecord } from "../lib/api";
  import { actionFailureReason, actionsFor, type RegisteredAction } from "../lib/actions/index";
  import { getStatusField, hasLifecycle } from "../lib/statusTransitions";
  import { navigate } from "../lib/router";
  import { debounce } from "../lib/utils";
  import DataTable from "../components/DataTable.svelte";
  import RecordForm from "../components/RecordForm.svelte";
  import Icon from "../components/Icon.svelte";
  import type { AuditEntry, RecordRow } from "../lib/types";

  let { id, recordId }: { id: string; recordId?: string } = $props();

  const model = $derived($app.schema?.byId[id]);
  const listPath = $derived(model?.listPath ?? "");

  let rows = $state<RecordRow[]>([]);
  let count = $state(0);
  let page = $state(1);
  let hasNext = $state(false);
  let hasPrev = $state(false);
  let loading = $state(true);
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

  const recordActions = $derived(model ? actionsFor(model.id, "record") : []);
  const bulkActions = $derived(model ? actionsFor(model.id, "bulk") : []);

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
      navigate(`#/m/${id}`);
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

  /** The record sub-view: R-001 lifecycle history (oldest-first) plus R-003
   *  audit entries (newest-first) for this record. History is only fetched for
   *  lifecycle-governed models; the audit log is open to any model, so a plain
   *  record still shows what custom actions did to it. */
  async function showHistory(row: RecordRow) {
    if (!model || row.id === undefined) return;
    historyView = row;
    history = [];
    audit = [];
    try {
      if (hasLifecycle(model.id)) {
        history = await fetchHistory(effectiveConfig(), get(app).token || null, model, row.id as any);
      }
    } catch (err) {
      handleApiError(err);
      historyView = null;
      return;
    }
    try {
      audit = (await fetchAudit(effectiveConfig(), get(app).token || null, {
        objectType: model.singular,
        objectId: row.id,
      })).results;
    } catch (err: any) {
      // A backend that has not shipped the R-003 audit endpoint has no log to
      // show — degrade to the lifecycle half instead of failing the sub-view.
      if (err.status !== 404) handleApiError(err);
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
    <p>Unknown model "{id}".</p>
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
      <button class="btn btn-primary" onclick={openCreate}>
        <Icon name="plus" size={16} />
        New {model.name}
      </button>
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

    <DataTable {model} {rows} {loading} onedit={openEdit} ondelete={onDelete} ontransition={onTransition} onshowhistory={showHistory}
               actions={recordActions} bulkActions={bulkActions} onaction={requestAction} />

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
          <p class="text-text/50">No lifecycle history.</p>
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
