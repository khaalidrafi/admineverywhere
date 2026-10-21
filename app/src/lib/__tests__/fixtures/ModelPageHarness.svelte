<!-- Test-only stand-in for the shell's <Page {...$route.params} /> slot
     (Shell.svelte:54). It exists so a case can change a page's props the way
     the router does — in place, on a live instance — instead of remounting it,
     which is the only way a stale-prop capture can ever be observed. -->
<script lang="ts">
  import ModelPage from "../../../pages/ModelPage.svelte";
  import { harnessProps } from "./harnessProps";

  const props = $derived($harnessProps);
</script>

<ModelPage {...props} />
