<script lang="ts">
  import { onMount } from "svelte";
  import { app, initApp, loadAiSettings, loadSchema } from "./lib/stores.svelte";
  import Login from "./pages/Login.svelte";
  import Shell from "./components/Shell.svelte";
  import Toaster from "./components/Toaster.svelte";
  import ErrorBanner from "./components/ErrorBanner.svelte";

  onMount(async () => {
    await initApp();
    await loadAiSettings();
  });

  // auto-load schema once logged in (and on re-login)
  $effect(() => {
    if (app.booted && app.token && !app.schema && !app.schemaLoading) {
      loadSchema();
    }
  });
</script>

{#if !app.booted}
  <!-- splash -->
  <div class="flex min-h-screen flex-col items-center justify-center gap-4">
    <div class="size-16 rounded-brand bg-gradient-to-br from-primary to-accent animate-pulse"></div>
    <div class="text-lg font-semibold">{app.brand.appName}</div>
    <div class="skeleton h-2 w-40"></div>
  </div>
{:else if !app.token}
  <Login />
{:else}
  <Shell />
{/if}

<ErrorBanner />
<Toaster />
