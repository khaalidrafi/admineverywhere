<script lang="ts">
  import { onMount } from "svelte";
  import { app, initApp, loadAiSettings, loadSchema } from "./lib/stores";
  import { resolveAsset } from "./lib/branding";
  import { authPage } from "./lib/pages";
  import Shell from "./components/Shell.svelte";
  import Toaster from "./components/Toaster.svelte";
  import ErrorBanner from "./components/ErrorBanner.svelte";

  // The auth screen is a registered page too (meta.standalone) — no static
  // import here, so a client that ships its own login drops in a file. The
  // same declaration drives the sidebar's Sign out href (lib/pages authPage).

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
  <!-- splash: the brand intro IS the loader (owner order — every other
       loader is gone). When the brand ships a loaderVideo it plays here;
       the accent frame keeps the old loader's brand color on first paint.
       No skeleton bar: the video (or the pulsing gradient fallback) is the
       entire progress indicator. -->
  <div class="flex min-h-screen flex-col items-center justify-center gap-4">
    {#if $app.brand.loaderVideo}
      <video
        src={resolveAsset($app.brand.loaderVideo)}
        autoplay
        muted
        loop
        playsinline
        disablepictureinpicture
        class="w-56 rounded-brand"
        style="box-shadow: 0 0 0 3px var(--brand-accent)"
      ></video>
    {:else}
      <div class="size-16 rounded-brand bg-gradient-to-br from-primary to-accent animate-pulse"></div>
    {/if}
    <div class="text-lg font-semibold">{$app.brand.appName}</div>
  </div>
{:else if !$app.token}
  {#if authPage}
    {@const AuthPage = authPage.component}
    <AuthPage />
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
