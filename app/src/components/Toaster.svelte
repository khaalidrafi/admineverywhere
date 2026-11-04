<script lang="ts">
  import { toasts } from "../lib/stores";
</script>

<div class="fixed bottom-[calc(1.5rem_+_env(safe-area-inset-bottom))] left-6 z-50 flex w-80 flex-col gap-2" role="status" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div
      class="card flex items-center gap-3 px-4 py-3 text-sm shadow-lg
        {t.kind === 'error' ? 'border-l-4 border-l-error' : t.kind === 'success' ? 'border-l-4 border-l-success' : 'border-l-4 border-l-accent'}"
    >
      <span class="flex-1">{t.text}</span>
    </div>
  {/each}
</div>
