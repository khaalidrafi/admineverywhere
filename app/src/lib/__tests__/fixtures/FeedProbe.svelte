<!-- Test-only stand-in for a client project's drop-in widget (FR-R008), written
     exactly to docs/widget-data.md's copy checklist: static `meta.data` in
     <script module>, a schema-reactive $effect that returns the feed's stop fn,
     and all four states rendered. Its declaration is deliberately hostile —
     pollInterval 100 ms (the engine must floor it to 5 s) and endpoint pinned
     to "orders" (so a schema swap that removes that model is observable on the
     wire). Lives outside app/src/widgets/ on purpose: it must never join the
     shipped widget glob. -->
<script module lang="ts">
  export const meta = {
    title: "Probe",
    size: "sm",
    data: { endpoint: "orders", aggregate: "count", pollInterval: 100 },
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
