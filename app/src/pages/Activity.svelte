<script module lang="ts">
  /** R-007(b) proof: the activity screen is a dropped-in module, not a fork. */
  export const meta = { title: "Activity", path: "/activity", nav: "main", icon: "info", order: 45 };
</script>

<script lang="ts">
  /** Activity — the append-only audit log (FR-R003 endpoint, FR-R007 screen).
   *
   *  Reads GET <audit listPath> newest-first, paginated, with the server's
   *  object_type / object_id filters. The listPath comes from the schema —
   *  findAuditModel resolves the registered audit model, so a backend that
   *  mounts the log under a different segment still works, and one that has
   *  no audit endpoint at all renders a friendly empty with a nameable
   *  reason instead of a 404 against a guessed URL.
   */
  import { app, effectiveConfig, handleApiError } from "../lib/stores";
  import { fetchAudit } from "../lib/api";
  import { findAuditModel } from "../lib/rbac";
  import type { AuditEntry } from "../lib/types";
  import Icon from "../components/Icon.svelte";

  const auditModel = $derived(findAuditModel($app.schema));

  let rows = $state<AuditEntry[]>([]);
  let count = $state(0);
  let page = $state(1);
  let objectType = $state("");
  let objectId = $state("");
  let loading = $state(false);

  // Widgets/pages render from a schema-reactive $effect, never onMount —
  // the schema arrives after mount. One fetch per schema; filters re-load
  // explicitly.
  $effect(() => {
    if (auditModel) void load(1);
  });

  async function load(toPage: number) {
    const model = auditModel;
    if (!model) return;
    loading = true;
    try {
      const res = await fetchAudit(effectiveConfig(), $app.token || null, {
        path: model.listPath,
        page: toPage,
        objectType: objectType.trim() || undefined,
        objectId: objectId.trim() || undefined,
      });
      rows = res.results;
      count = res.count;
      page = toPage;
    } catch (err) {
      handleApiError(err);
    } finally {
      loading = false;
    }
  }

  function formatTime(iso: string): string {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  const lastPage = $derived(Math.max(1, Math.ceil(count / 10)));
</script>

<div class="mx-auto max-w-5xl">
  <div class="mb-6">
    <h1 class="text-2xl font-semibold">Activity</h1>
    <p class="text-sm text-text/50">
      Append-only audit trail — newest first. The log can only grow: there is
      no edit or delete anywhere in this view because there is none on the server.
    </p>
  </div>

  {#if !$app.schema}
    <div class="card p-6 text-sm text-text/50">Waiting for the API schema…</div>
  {:else if !auditModel}
    <div class="card p-6">
      <div class="flex items-start gap-3">
        <Icon name="alert" class="mt-0.5 size-5 text-warning" />
        <div>
          <div class="font-medium">No audit endpoint in this backend</div>
          <p class="mt-1 text-sm text-text/50">
            The OpenAPI document does not register a model whose path ends in
            <code class="rounded border border-text/20 bg-text/10 px-1.5 py-0.5 text-[11px]">/audit/</code>.
            Ship the FR-R003 reference (docs/custom-actions.md: an append-only
            List+Create ViewSet) and this page fills itself — nothing here to edit.
          </p>
        </div>
      </div>
    </div>
  {:else}
    <form
      class="card mb-4 flex flex-wrap items-end gap-3 p-4"
      onsubmit={(e) => {
        e.preventDefault();
        void load(1);
      }}
    >
      <label class="text-xs text-text/50">
        Object type
        <input
          bind:value={objectType}
          class="input mt-1 w-40"
          placeholder="order"
          aria-label="Filter by object type"
        />
      </label>
      <label class="text-xs text-text/50">
        Object id
        <input
          bind:value={objectId}
          class="input mt-1 w-28"
          placeholder="42"
          aria-label="Filter by object id"
        />
      </label>
      <button type="submit" class="btn btn-primary" disabled={loading}>
        {loading ? "Loading…" : "Filter"}
      </button>
      <span class="ml-auto text-xs text-text/50">{count} entries</span>
    </form>

    <div class="card overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-surface/60 text-xs uppercase tracking-wider text-text/50">
          <tr>
            <th class="px-4 py-2">When</th>
            <th class="px-4 py-2">Actor</th>
            <th class="px-4 py-2">Action</th>
            <th class="px-4 py-2">Object</th>
            <th class="px-4 py-2">Summary</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as entry (entry.id)}
            <tr class="border-t border-text/10">
              <td class="whitespace-nowrap px-4 py-2 text-text/60">{formatTime(entry.created_at)}</td>
              <td class="px-4 py-2">{entry.actor ?? "system"}</td>
              <td class="px-4 py-2"><span class="badge">{entry.action}</span></td>
              <td class="px-4 py-2 text-text/60">{entry.object_type}#{entry.object_id}</td>
              <td class="px-4 py-2">{entry.summary}</td>
            </tr>
          {:else}
            <tr>
              <td colspan="5" class="px-4 py-8 text-center text-sm text-text/50">
                Nothing logged{objectType || objectId ? " for this filter" : ""} yet.
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if lastPage > 1}
      <div class="mt-4 flex items-center justify-between text-sm">
        <button class="btn" disabled={page <= 1 || loading} onclick={() => void load(page - 1)}>
          ← Newer
        </button>
        <span class="text-text/50">page {page} / {lastPage}</span>
        <button class="btn" disabled={page >= lastPage || loading} onclick={() => void load(page + 1)}>
          Older →
        </button>
      </div>
    {/if}
  {/if}
</div>
