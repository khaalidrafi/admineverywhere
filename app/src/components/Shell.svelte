<script lang="ts">
  /** App shell — renders whatever the page registry declares.
   *
   *  FR R-006: this component used to import each page and switch on the
   *  route name, which made every new module a fork of the shell. The route
   *  table now comes from `lib/pages` (glob over src/pages), so the shell has
   *  no page-specific line left. Params a pattern captured are spread as props.
   */
  import { app } from "../lib/stores";
  import { route } from "../lib/router";
  import { pageById } from "../lib/pages";
  import Sidebar from "./Sidebar.svelte";
  import ChatPanel from "../ai/ChatPanel.svelte";
  import Icon from "./Icon.svelte";

  let sidebarOpen = $state(false);

  function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
  }

  // a standalone page (the auth gate) is never rendered inside the shell
  const current = $derived(
    $route.kind === "page" && !$route.standalone ? pageById($route.pageId!) : undefined,
  );
</script>

<div class="flex min-h-screen">
  <!-- mobile topbar -->
  <div class="fixed top-0 z-30 flex w-full items-center gap-3 bg-surface/95 px-4 py-3 backdrop-blur md:hidden">
    <button class="btn btn-ghost p-2" onclick={toggleSidebar} aria-label="Menu">
      <Icon name="menu" />
    </button>
    <span class="font-semibold">{$app.brand.appName}</span>
  </div>

  <!-- sidebar: fixed overlay on mobile, static on md+ -->
  <div
    class="fixed inset-y-0 left-0 z-40 md:static md:z-0 {sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'} transition-transform"
  >
    <Sidebar onnavigate={() => (sidebarOpen = false)} />
  </div>
  {#if sidebarOpen}
    <button
      class="fixed inset-0 z-30 bg-black/50 md:hidden"
      onclick={() => (sidebarOpen = false)}
      aria-label="Close menu"
    ></button>
  {/if}

  <main class="flex-1 px-4 pb-24 pt-20 md:px-8 md:pb-10 md:pt-6">
    {#if current}
      <svelte:component this={current.component} {...$route.params} />
    {:else if $route.kind === "page"}
      <div class="p-8 text-text/60">This module lives outside the app shell.</div>
    {:else}
      <div class="p-8 text-text/60">
        No page declares <code class="rounded bg-text/10 px-1">{$route.path}</code> — pick a
        module from the sidebar.
      </div>
    {/if}
  </main>
</div>

<ChatPanel />
