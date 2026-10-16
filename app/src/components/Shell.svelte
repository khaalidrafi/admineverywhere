<script lang="ts">
  import { app } from "../lib/stores.svelte";
  import { route } from "../lib/router.svelte";
  import Sidebar from "./Sidebar.svelte";
  import Dashboard from "../pages/Dashboard.svelte";
  import ModelPage from "../pages/ModelPage.svelte";
  import ChatPanel from "../ai/ChatPanel.svelte";
  import Icon from "./Icon.svelte";

  let sidebarOpen = $state(false);

  function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
  }
</script>

<div class="flex min-h-screen">
  <!-- mobile topbar -->
  <div class="fixed top-0 z-30 flex w-full items-center gap-3 bg-surface/95 px-4 py-3 backdrop-blur md:hidden">
    <button class="btn btn-ghost p-2" onclick={toggleSidebar} aria-label="Menu">
      <Icon name="menu" />
    </button>
    <span class="font-semibold">{app.brand.appName}</span>
  </div>

  <!-- sidebar: fixed on mobile (overlay), static on md+ -->
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
    {#if route.name === "dashboard"}
      <Dashboard />
    {:else if route.name === "model"}
      {#key route.id}
        <ModelPage id={route.id} recordId={route.recordId} />
      {/key}
    {:else}
      <div class="p-8 text-text/60">Unknown route — pick a model from the sidebar.</div>
    {/if}
  </main>
</div>

<ChatPanel />
