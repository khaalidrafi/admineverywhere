<script lang="ts">
  /** Schema-driven model CRUD: search + paginated table + create/edit modal. */
  import { get } from "svelte/store";
  import { app, effectiveConfig, handleApiError, toast } from "../lib/stores";
  import { deleteRecord, listRecords, retrieveRecord } from "../lib/api";
  import { navigate } from "../lib/router";
  import { debounce } from "../lib/utils";
  import DataTable from "../components/DataTable.svelte";
  import RecordForm from "../components/RecordForm.svelte";
  import Icon from "../components/Icon.svelte";
  import type { RecordRow } from "../lib/types";

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

    <DataTable {model} {rows} {loading} onedit={openEdit} ondelete={onDelete} />

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

  {#if formOpen}
    <RecordForm {model} record={editing} onclose={() => (formOpen = false)} onsaved={onSaved} />
  {/if}
{/if}
