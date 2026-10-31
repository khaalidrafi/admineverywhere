<script module lang="ts">
  export const meta = { title: "Dashboard", path: "/", nav: "main", icon: "grid", order: 10 };
</script>

<script lang="ts">
  import { widgets, widgetUnits } from "../widgets";
  import { instances } from "../lib/widgets/instances";
  import WidgetInstanceCard from "../components/WidgetInstanceCard.svelte";
  import { app } from "../lib/stores";
</script>

<div class="mx-auto max-w-6xl">
  <div class="mb-6">
    <h1 class="text-2xl font-semibold">Dashboard</h1>
    <p class="text-sm text-text/50">
      {$app.schema ? `${$app.schema.models.length} models · ` : ""}
      {widgets.length} widgets{$instances.length ? ` + ${$instances.filter((i) => i.enabled).length} yours` : ""} · press <kbd class="rounded border border-text/20 bg-text/10 px-1.5 py-0.5 text-[11px]">Ctrl+K</kbd> for AI
    </p>
  </div>

  <!-- responsive grid: sm widgets take 1 unit, lg take 2 -->
  <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
    {#each widgets as w (w.file)}
      {@const Widget = w.component}
      <div class={widgetUnits(w) === 2 ? "md:col-span-2 xl:col-span-2" : ""}>
        <div class="card p-4">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-semibold text-text/70">{w.title}</h2>
          </div>
          <Widget />
        </div>
      </div>
    {/each}
    {#each $instances.filter((i) => i.enabled) as inst (inst.id)}
      <div class={inst.size === "lg" ? "md:col-span-2 xl:col-span-2" : ""}>
        <WidgetInstanceCard {inst} />
      </div>
    {/each}
  </div>
</div>
