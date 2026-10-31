<script module lang="ts">
  export const meta = { title: "Notifications", path: "/notifications", nav: "main", icon: "bell", order: 15 };
</script>

<script lang="ts">
  /** Notifications — the in-app center + the OS permission row.
   *
   *  Everything shown here comes from lib/notifications.ts (ONE store, one
   *  truth: the bell badge and the dashboard threshold alerts read the same
   *  list). OS toasts are best-effort: browser mode has no Tauri runtime, so
   *  the permission row hides entirely; under Tauri (desktop + Android) the
   *  row shows the live status and offers the prompt.
   */
  import {
    notifications,
    unreadCount,
    markAllRead,
    markRead,
    clearNotifications,
    osPermissionStatus,
    requestOsPermission,
  } from "../lib/notifications";
  import Icon from "../components/Icon.svelte";

  let perm = $state<"granted" | "denied" | "unknown" | "unsupported">("unsupported");
  let asking = $state(false);

  $effect(() => {
    void osPermissionStatus().then((s) => (perm = s));
  });

  async function enable() {
    asking = true;
    const ok = await requestOsPermission();
    perm = ok ? "granted" : "denied";
    asking = false;
  }

  const when = (ts: number) => (ts ? new Date(ts).toLocaleString() : "");
</script>

<div class="mx-auto max-w-3xl">
  <div class="mb-6 flex items-center justify-between gap-3">
    <div>
      <h1 class="text-2xl font-semibold">Notifications</h1>
      <p class="text-sm text-text/50">
        {#if $notifications.length}
          {$notifications.length} {$notifications.length === 1 ? "event" : "events"} · {$unreadCount} unread
        {:else}
          threshold alerts from your dashboard widgets land here
        {/if}
      </p>
    </div>
    {#if $notifications.length}
      <div class="flex shrink-0 gap-2">
        <button class="btn btn-ghost text-xs" onclick={markAllRead} disabled={$unreadCount === 0}>
          Mark all read
        </button>
        <button class="btn btn-ghost text-xs" onclick={clearNotifications}>Clear</button>
      </div>
    {/if}
  </div>

  {#if perm !== "unsupported"}
    <div class="card mb-4 flex items-center justify-between p-4 text-sm">
      <div class="flex items-center gap-2">
        <Icon name="bell" size={16} />
        <span>OS notifications</span>
        <span class="text-text/50">
          {perm === "granted" ? "enabled — alerts also surface as system toasts" : perm === "denied" ? "not enabled yet" : "unavailable on this device"}
        </span>
      </div>
      {#if perm === "denied"}
        <button class="btn btn-ghost text-xs" disabled={asking} onclick={enable}>Enable</button>
      {/if}
    </div>
  {/if}

  {#if $notifications.length === 0}
    <div class="card p-8 text-center text-sm text-text/40">
      Quiet for now. Widgets you build in the Widget studio can raise threshold
      alerts here — and under Tauri they surface as system toasts too.
    </div>
  {:else}
    <ul class="space-y-2">
      {#each $notifications as n (n.id)}
        <li>
          <button
            class="card w-full p-4 text-left {n.read ? "opacity-60" : ""}"
            onclick={() => markRead(n.id)}
            title={n.read ? "" : "Mark as read"}
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex min-w-0 items-start gap-2">
                {#if !n.read}
                  <span class="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-label="unread"></span>
                {/if}
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold">{n.title}</div>
                  <div class="text-sm text-text/70">{n.body}</div>
                </div>
              </div>
              <div class="shrink-0 text-right text-[11px] text-text/40">
                <div>{when(n.ts)}</div>
                {#if n.source}
                  <div class="mt-1 inline-block rounded-full bg-text/10 px-2 py-0.5">{n.source}</div>
                {/if}
              </div>
            </div>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
