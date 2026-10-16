<script lang="ts">
  import { app } from "../lib/stores.svelte";
  import Icon from "./Icon.svelte";

  function dismiss() {
    app.backendDown = false;
  }
</script>

{#if app.backendDown}
  <div class="fixed left-1/2 top-4 z-50 flex w-[min(92vw,640px)] -translate-x-1/2 items-center gap-3
    rounded-brand border border-red-500/40 bg-red-950/80 px-4 py-3 text-sm text-red-100 backdrop-blur">
    <Icon name="alert" class="shrink-0 text-red-400" />
    <span class="flex-1">
      Cannot reach the backend at <b>{app.apiUrlOverride || app.config?.apiUrl}</b>.
      Check the server and API URL, then retry.
    </span>
    <button class="btn btn-ghost px-2 py-1 text-xs" onclick={dismiss}>Dismiss</button>
  </div>
{/if}
