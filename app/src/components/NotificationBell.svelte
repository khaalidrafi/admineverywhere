<script lang="ts">
  /** Bell — the always-visible entry to the Notifications page, with the
   *  unread badge.
   *
   *  The target comes from the page REGISTRY (the page whose id is
   *  "Notifications"), never a typed hash — the same law the sidebar obeys
   *  (navMount refuses hand-typed routes). Hidden when no page declares the
   *  module, so a client can drop it without breaking the shell.
   */
  import { unreadCount } from "../lib/notifications";
  import { pages, pageHref } from "../lib/pages";
  import { navigate } from "../lib/router";
  import Icon from "./Icon.svelte";

  const target = $derived(pages.find((p) => p.id === "Notifications"));
</script>

{#if target}
  <button
    class="btn btn-ghost relative px-2 py-1"
    title="Notifications"
    aria-label="Notifications{$unreadCount ? `, ${$unreadCount} unread` : ""}"
    onclick={() => navigate(pageHref(target))}
  >
    <Icon name="bell" size={16} />
    {#if $unreadCount > 0}
      <span
        class="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold leading-none text-bg"
      >
        {$unreadCount > 9 ? "9+" : $unreadCount}
      </span>
    {/if}
  </button>
{/if}
