<script lang="ts">
  import { app, logout } from "../lib/stores";
  import { navigate, route } from "../lib/router";
  import Icon from "./Icon.svelte";

  let { onnavigate }: { onnavigate?: () => void } = $props();

  function go(hash: string) {
    navigate(hash);
    onnavigate?.();
  }
</script>

<aside class="flex h-full w-64 flex-col border-r border-text/10 bg-surface">
  <!-- brand header -->
  <div class="flex items-center gap-3 px-5 py-5">
    {#if $app.brand.logo}
      <img src={$app.brand.logo} alt="logo" class="size-9 rounded-lg" />
    {:else}
      <div class="size-9 rounded-lg bg-gradient-to-br from-primary to-accent"></div>
    {/if}
    <div class="min-w-0">
      <div class="truncate font-semibold leading-tight">{$app.brand.appName}</div>
      {#if $app.brand.tagline}
        <div class="truncate text-xs text-text/50">{$app.brand.tagline}</div>
      {/if}
    </div>
  </div>

  <nav class="flex-1 overflow-y-auto px-3 pb-4">
    <button
      class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium
        {$route.name === 'dashboard' ? 'bg-primary/15 text-primary' : 'text-text/70 hover:bg-text/5'}"
      onclick={() => go("#/")}
    >
      <Icon name="grid" size={16} />
      Dashboard
    </button>

    <div class="mt-4 px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-text/40">
      Models
    </div>

    {#if $app.schemaLoading}
      {#each Array(4) as _, i (i)}
        <div class="skeleton mx-3 my-2 h-8"></div>
      {/each}
    {:else if $app.schema}
      {#each $app.schema.models as model (model.id)}
        <button
          class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium
            {$route.name === 'model' && $route.id === model.id ? 'bg-primary/15 text-primary' : 'text-text/70 hover:bg-text/5'}"
          onclick={() => go(`#/m/${model.id}`)}
        >
          <Icon name="table" size={16} />
          {model.name}
        </button>
      {/each}
    {:else}
      <div class="px-3 py-2 text-xs text-text/50">Schema unavailable</div>
    {/if}
  </nav>

  <!-- footer -->
  <div class="border-t border-text/10 px-3 py-3">
    <div class="flex items-center justify-between gap-2 px-2 pb-2 text-xs text-text/50">
      <span class="truncate">@{$app.username || "admin"}</span>
      <button
        class="btn btn-ghost px-2 py-1 text-xs"
        onclick={() => { logout(); navigate("#/login"); }}
        title="Sign out"
      >
        <Icon name="logout" size={14} />
        Sign out
      </button>
    </div>
  </div>
</aside>
