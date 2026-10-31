<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import { app, initApp, loadAiSettings, loadSchema } from "./lib/stores";
  import { resolveAsset } from "./lib/branding";
  import { authPage } from "./lib/pages";
  import Shell from "./components/Shell.svelte";
  import Toaster from "./components/Toaster.svelte";
  import ErrorBanner from "./components/ErrorBanner.svelte";

  // The auth screen is a registered page too (meta.standalone) — no static
  // import here, so a client that ships its own login drops in a file. The
  // same declaration drives the sidebar's Sign out href (lib/pages authPage).

  // ---- branded splash hold (QA 5-a / D1) ----------------------------------
  // QA measured the splash DOM committing for only ~22-42ms: initApp flips
  // `booted` synchronously after boot, so the login replaced the splash
  // BEFORE the first paint and the brand intro video was unreachable. The
  // splash now holds a brand-controlled minimum while boot continues
  // underneath — only the visual handover waits, never the boot itself.
  const VIDEO_HOLD_MS = 800; // the intro IS the loader: it plays out
  const TILE_HOLD_MS = 600;  // pulsing accent-tile fallback
  const SKIP_ARM_MS = 600;   // tap-to-skip goes live

  // The mode is decided at first paint and never flips mid-hold: a brand
  // swap while the splash is up must not orphan (or late-spawn) the video
  // element that owns the release. coldBoot guards remounts (HMR/tests)
  // where the splash never painted — there is nothing to hold.
  const coldBoot = !get(app).booted;
  let videoPhase = $state(coldBoot && Boolean(get(app).brand.loaderVideo));
  let videoPhaseDone = $state(!coldBoot); // ended | error | tap-skipped
  let minHoldDone = $state(!coldBoot);
  let skipReady = $state(false);

  const splashReleased = $derived(
    minHoldDone && (!videoPhase || videoPhaseDone || !$app.brand.loaderVideo),
  );

  // 'ended' fires unconditionally; the tap only counts once it is armed.
  function endVideoPhase(): void {
    videoPhaseDone = true;
  }

  function skipVideoPhase(): void {
    if (videoPhase && skipReady && !videoPhaseDone) endVideoPhase();
  }

  onMount(() => {
    if (!coldBoot) return;
    const minHold = setTimeout(
      () => (minHoldDone = true),
      videoPhase ? VIDEO_HOLD_MS : TILE_HOLD_MS,
    );
    const skipArm = videoPhase
      ? setTimeout(() => (skipReady = true), SKIP_ARM_MS)
      : undefined;
    return () => {
      clearTimeout(minHold);
      if (skipArm) clearTimeout(skipArm);
    };
  });

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

{#if !$app.booted || !splashReleased}
  <!-- splash: the brand intro IS the loader (owner order — every other
       loader is gone). With a loaderVideo it plays full-viewport and the
       splash holds until the clip ends (or tap-to-skip after 600ms) and
       the brand minimum elapsed; without one the pulsing brand-accent tile
       holds its own minimum. No skeleton bar, no spinner: the video (or
       the pulsing gradient fallback) is the entire progress indicator.
       Boot keeps running underneath — only the handover waits. -->
  {#if videoPhase}
    <div
      class="fixed inset-0 z-50 flex flex-col items-center justify-end gap-4 bg-black pb-10"
      role="status"
      aria-label="{$app.brand.appName} is loading"
    >
      <video
        src={resolveAsset($app.brand.loaderVideo)}
        autoplay
        muted
        playsinline
        disablepictureinpicture
        class="absolute inset-0 size-full object-cover"
        onended={endVideoPhase}
        onerror={endVideoPhase}
      ></video>
      {#if skipReady && !videoPhaseDone}
        <button
          type="button"
          class="relative z-10 rounded-full bg-white/15 px-4 py-1.5 text-sm font-medium text-white backdrop-blur transition-colors hover:bg-white/25"
          onclick={skipVideoPhase}
        >
          Tap to skip
        </button>
      {/if}
      <div class="relative z-10 text-lg font-semibold text-white drop-shadow">{$app.brand.appName}</div>
    </div>
  {:else}
    <div
      class="flex min-h-screen flex-col items-center justify-center gap-4"
      role="status"
      aria-label="{$app.brand.appName} is loading"
    >
      <div class="size-16 rounded-brand bg-gradient-to-br from-primary to-accent animate-pulse"></div>
      <div class="text-lg font-semibold">{$app.brand.appName}</div>
    </div>
  {/if}
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

<!-- click anywhere ends the video phase once skip is armed (guarded
     no-op outside the splash's video hold) -->
<svelte:window onclick={skipVideoPhase} />

<ErrorBanner />
<Toaster />
