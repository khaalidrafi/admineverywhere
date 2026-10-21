/** A writable the test drives, mirroring what the router gives the page:
 *  Shell.svelte:54 renders <Page {...$route.params} />, so a hash change updates
 *  the page's PROPS on the SAME instance. Svelte 5 forbids $set() from a test,
 *  so the update has to travel through a parent the same way. */
import { writable } from "svelte/store";

export const harnessProps = writable<Record<string, any>>({});
