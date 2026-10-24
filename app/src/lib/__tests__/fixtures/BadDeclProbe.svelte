<!-- Test-only widget whose <script module> declaration is WRONG on purpose
     (aggregate: "median" is not one of the six kinds). feed.ts refuses a broken
     declaration with a nameable reason and zero requests; that guard ran only
     through a hand-built spec object in widgetFeed.test.ts until this file made
     it a real <script module> literal reaching the engine through a real
     component. Outside the shipped widget glob, like FeedProbe.svelte. -->
<script module lang="ts">
  export const meta = {
    title: "Bad Probe",
    size: "sm",
    data: { aggregate: "median" },
  };
</script>

<script lang="ts">
  import { app } from "../../stores";
  import { startWidgetFeed, type FeedState } from "../../widgets/feed";

  let state = $state<FeedState>({ status: "loading" });
  $effect(() => {
    const schema = $app.schema;
    if (!schema) return;
    return startWidgetFeed(meta.data, (s) => (state = s), schema);
  });
</script>

{#if state.status === "loading"}
  <div class="skeleton" data-state="loading"></div>
{:else if state.status === "empty"}
  <div data-state="empty">{state.reason}</div>
{:else if state.status === "error"}
  <div data-state="error">{state.message}</div>
{:else if state.status === "ready"}
  <div data-state="ready">{state.result.label}</div>
{/if}
