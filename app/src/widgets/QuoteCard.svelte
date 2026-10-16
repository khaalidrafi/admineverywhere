<script module>
  export const meta = { title: "Daily Spark", size: "sm" };
</script>

<script lang="ts">
  /** QuoteCard — the "drop one file, get a widget" demo.
   *  Random curated quote; click flips to a new one (CSS 3D flip).
   */
  import { QUOTES, randomQuote } from "./quotes";
  import { app } from "../lib/stores.svelte";

  let index = $state(randomQuote());
  let flipping = $state(false);
  let flipTimer: ReturnType<typeof setTimeout> | undefined;

  const quote = $derived(QUOTES[index]);

  function next() {
    if (flipping) return;
    flipping = true;
    clearTimeout(flipTimer);
    // swap the text at the halfway point of the 450ms flip
    flipTimer = setTimeout(() => {
      index = randomQuote(index);
      flipping = false;
    }, 225);
  }
</script>

<button class="flip-scene block w-full text-left" onclick={next} title="Click for another quote">
  <div class="flip-card card relative min-h-[11rem] p-4 {flipping ? 'flipping' : ''}">
    <div class="mb-2 flex items-center justify-between">
      <span class="text-[10px] font-semibold uppercase tracking-widest text-accent">
        {app.brand.appName} · Daily Spark
      </span>
      <span class="text-text/30 transition-transform {flipping ? 'rotate-180' : ''}">↻</span>
    </div>
    <blockquote class="text-sm leading-relaxed text-text/90">
      “{quote.text}”
    </blockquote>
    <footer class="mt-3 text-xs text-text/45">— {quote.source}</footer>
  </div>
</button>
