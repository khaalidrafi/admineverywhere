<script module lang="ts">
  /** The R-006 proof: this module was added by dropping ONE file into
   *  src/pages/ — no registry, router table, shell or sidebar edit. */
  export const meta = { title: "Modules", path: "/modules", nav: "main", icon: "info", order: 20 };
</script>

<script lang="ts">
  /** Modules — what the page registry discovered, and what it refused.
   *
   *  Same self-documenting role the QuoteCard widget plays for the dashboard
   *  grid: a client that onboards its own modules can see, in the app, which
   *  files registered a route, which got a sidebar entry, and which
   *  declarations were rejected with a reason.
   */
  import { app } from "../lib/stores";
  import { navigate } from "../lib/router";
  import { pages, refusedPages, pageHref } from "../lib/pages";
  import Icon from "../components/Icon.svelte";

  const modelCount = $derived($app.schema?.models.length ?? 0);
</script>

<div class="mx-auto max-w-4xl">
  <div class="mb-6">
    <h1 class="text-2xl font-semibold">Modules</h1>
    <p class="text-sm text-text/50">
      {pages.length} registered pages · {modelCount} schema models. A page is one
      <code class="rounded border border-text/20 bg-text/10 px-1.5 py-0.5 text-[11px]">.svelte</code>
      file in <code class="rounded border border-text/20 bg-text/10 px-1.5 py-0.5 text-[11px]">src/pages/</code>
      exporting <code class="rounded border border-text/20 bg-text/10 px-1.5 py-0.5 text-[11px]">meta</code>.
    </p>
  </div>

  <div class="card overflow-hidden">
    <table class="w-full text-left text-sm">
      <thead class="bg-surface/60 text-xs uppercase tracking-wider text-text/50">
        <tr>
          <th class="px-4 py-2">Title</th>
          <th class="px-4 py-2">Declared path</th>
          <th class="px-4 py-2">Nav</th>
          <th class="px-4 py-2"></th>
        </tr>
      </thead>
      <tbody>
        {#each pages as page (page.id)}
          <tr class="border-t border-text/10">
            <td class="px-4 py-2 font-medium">{page.title}</td>
            <td class="px-4 py-2 font-mono text-xs">{page.path}</td>
            <td class="px-4 py-2 text-xs">
              {page.nav === false ? "—" : page.nav}
              {#if page.standalone}<span class="ml-1 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] uppercase">standalone</span>{/if}
            </td>
            <td class="px-4 py-2 text-right">
              {#if page.params.length === 0}
                <button class="btn btn-ghost px-2 py-1 text-xs" onclick={() => navigate(pageHref(page))}>
                  <Icon name="right" size={14} />
                  Open
                </button>
              {:else}
                <span class="text-xs text-text/40">parameterised</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if refusedPages.length}
    <div class="mt-6 rounded-lg border border-red-500/30 bg-red-500/5 p-4">
      <h2 class="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Icon name="alert" size={16} />
        Refused declarations
      </h2>
      <ul class="space-y-1 text-xs">
        {#each refusedPages as bad (bad.id)}
          <li class="font-mono">{bad.id}: {bad.reason}</li>
        {/each}
      </ul>
      <p class="mt-2 text-xs text-text/50">
        A refused page registers no route and no sidebar entry — the reason above is the fix.
      </p>
    </div>
  {/if}
</div>
