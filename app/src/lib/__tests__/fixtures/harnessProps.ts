/** A writable the test drives, mirroring what the router gives the page:
 *  Shell.svelte:54 renders <Page {...$route.params} />, so a hash change updates
 *  the page's PROPS on the SAME instance. Svelte 5 forbids $set() from a test,
 *  so the update has to travel through a parent the same way. */
import { writable } from "svelte/store";

export const harnessProps = writable<Record<string, any>>({});

/** The same drive, aimed at RecordForm directly: the page-level guard in
 *  ModelPage closes the editor on any route-params re-spread, so the props-move
 *  contract the form itself documents can ONLY be observed through a parent of
 *  its own. */
export const recordFormHarnessProps = writable<Record<string, any>>({});
