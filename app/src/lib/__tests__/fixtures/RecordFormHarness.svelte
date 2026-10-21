<!-- Test-only parent that holds RecordForm mounted while its props move —
     exactly the transition RecordForm.svelte's re-hydration effect promises.
     ModelPage cannot deliver it: its own $effect reads props, and ANY
     re-spread of the params object (even one carrying the same values)
     re-fires prop-reading effects in Svelte 5, so the page's model-switch
     guard closes the modal before the form ever sees a moved prop. -->
<script lang="ts">
  import RecordForm from "../../../components/RecordForm.svelte";
  import { recordFormHarnessProps } from "./harnessProps";

  const props = $derived($recordFormHarnessProps);
</script>

<RecordForm {...props} />
