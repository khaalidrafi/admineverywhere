<script lang="ts">
  import { onMount } from "svelte";
  import { app, initApp, loadAiSettings, loadSchema } from "./lib/stores";
  import { standalonePages } from "./lib/pages";
  import Shell from "./components/Shell.svelte";
  import Toaster from "./components/Toaster.svelte";
  import ErrorBanner from "./components/ErrorBanner.svelte";

  // The auth screen is a registered page too (meta.standalone) — no static
  // import here, so a client that ships its own login drops in a file.
  const authPage = standalonePages[0];

  onMount(async () => {
    await initApp();
    await loadAiSettings();
  });

  // auto-load schema once logged in (and on re-login)
  $effect(() => {
    if ($app.booted && $app.token && !$app.schema && !$app.schemaLoading) {
      loadSchema();
    }
  });
</script>

{#if !$app.booted}
  <!-- splash -->
  <div class="flex min-h-screen flex-col items-center justify-center gap-4">
    <div class="size-16 rounded-brand bg-gradient-to-br from-primary to-accent animate-pulse"></div>
    <div class="text-lg font-semibold">{$app.brand.appName}</div>
    <div class="skeleton h-2 w-40"></div>
  </div>
{:else if !$app.token}
  {#if authPage}
    <svelte:component this={authPage.component} />
  {:else}
    <div class="flex min-h-screen items-center justify-center text-text/60">
      No page declares <code>standalone: true</code> — a sign-in module is required.
    </div>
  {/if}
{:else}
  <Shell />
{/if}

<ErrorBanner />
<Toaster />
