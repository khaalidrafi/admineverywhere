<script lang="ts">
  /** Renders ONE user-built widget instance on the dashboard.
   *
   *  Same chrome and grid cell as the built-ins, so a custom widget is a
   *  citizen, not an embed. Laws:
   *  - the component comes from the WIDGET REGISTRY by type id — an instance
   *    names a type, it never ships code;
   *  - accents are brand ROLES: the card re-maps --brand-primary onto another
   *    brand variable, so a rebrand recolors custom widgets exactly like
   *    built-ins and no hard-coded color enters the tree;
   *  - fed types run the SAME feed engine with the instance's data override;
   *  - a threshold rule raises notifications through the ONE notification
   *    store, and only on the transitions shouldFire() promises.
   */
  import { widgets } from "../widgets";
  import { app } from "../lib/stores";
  import { startWidgetFeed, type FeedState } from "../lib/widgets/feed";
  import { shouldFire, type WidgetInstance } from "../lib/widgets/instances";
  import { pushNotification } from "../lib/notifications";

  let { inst }: { inst: WidgetInstance } = $props();

  const base = $derived(
    widgets.find((w) => w.file.split("/").pop()!.replace(/\.svelte$/, "") === inst.type),
  );
  // the type declares a feed → the instance may pin its own data source
  const fed = $derived(base?.data != null);
  const accentStyle = $derived(
    inst.accent === "accent"
      ? "--brand-primary: var(--brand-accent);"
      : inst.accent === "text"
        ? "--brand-primary: var(--brand-text);"
        : "",
  );

  let state = $state<FeedState>({ status: "loading" });
  $effect(() => {
    const schema = $app.schema;
    if (!schema || !base || !fed) return;
    return startWidgetFeed(inst.data ?? base.data, (s) => {
      state = s;
      if (s.status === "ready") {
        const verdict = shouldFire(inst, s.result);
        if (verdict.fire) {
          pushNotification({ title: inst.title, body: verdict.text, source: `widget:${inst.type}` });
        }
      }
    }, schema);
  });
</script>

{#if base && inst.enabled}
  <div class="card p-4" style={accentStyle}>
    <div class="mb-3 flex items-center justify-between">
      <h2 class="text-sm font-semibold text-text/70">{inst.title}</h2>
      {#if inst.notify}
        <span class="rounded-full bg-text/10 px-2 py-0.5 text-[10px] text-text/50">alerts</span>
      {/if}
    </div>
    {#if fed}
      {@const Widget = base.component}
      <Widget data={inst.data ?? base.data} />
    {:else}
      {@const Widget = base.component}
      <Widget />
    {/if}
  </div>
{/if}
