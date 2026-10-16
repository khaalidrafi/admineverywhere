<script lang="ts">
  import { toasts } from "../lib/stores.svelte";
</script>

<div class="fixed bottom-6 left-6 z-50 flex w-80 flex-col gap-2">
  {#each toasts as t (t.id)}
    <div
      class="card flex items-center gap-3 px-4 py-3 text-sm shadow-lg
        {t.kind === 'error' ? 'border-l-4 border-l-red-500' : t.kind === 'success' ? 'border-l-4 border-l-emerald-500' : 'border-l-4 border-l-accent'}"
    >
      <span class="flex-1">{t.text}</span>
    </div>
  {/each}
</div>
