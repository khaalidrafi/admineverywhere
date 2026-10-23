<script lang="ts">
  /** A stand-in for "a client's own sign-in module", used by
   *  authGateMount.test.ts. It is deliberately NOT Login.svelte: the test
   *  points the registry's standalone slot at this component to prove the
   *  auth gate renders whatever the page registry declared rather than a
   *  hard-imported screen. Placed outside src/pages/ so the page glob never
   *  discovers it. */
</script>

<div id="probe-signin">
  <h1>Probe Sign-In Gate</h1>
  <p>standalone-from-registry</p>
</div>
