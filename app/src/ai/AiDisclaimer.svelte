<script lang="ts">
  /** AiDisclaimer — the mandatory AI cloud-data notice (owner order
   *  2026-11-08: EVERY AI feature must say that website data goes to the
   *  AI provider's cloud). Pure presentational; mount it on any AI surface.
   */
  let { compact = false }: { compact?: boolean } = $props();
</script>

{#if compact}
  <div
    class="flex items-start gap-1.5 px-3 py-1.5 text-[10px] leading-snug text-text/50"
    data-tour="ai-disclaimer"
  >
    <span class="mt-[1px] shrink-0 text-[var(--brand-accent)]">ⓘ</span>
    <span>
      AI features send app data to the AI provider's cloud.
    </span>
  </div>
{:else}
  <div
    class="flex items-start gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-[11px] leading-snug text-text/70"
    data-tour="ai-disclaimer"
  >
    <span class="mt-[1px] shrink-0 text-[var(--brand-accent)]">ⓘ</span>
    <span>
      <strong class="font-semibold">Privacy notice:</strong> AI features send app data (record
      names, fields and your messages) to the AI provider's cloud for processing. It is governed by
      that provider's terms — do not include secrets you would not share with the provider.
    </span>
  </div>
{/if}
