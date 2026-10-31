# Widget instances — the Widget studio contract

Owner order 2026-10-31: "add cool, brandable, customizable widget builder
for the android app. Also, add notifications."

Built-in widgets are **code**: one `.svelte` file in `app/src/widgets/`,
auto-discovered by the registry (see `widget-data.md` for the feed
contract). An **instance** is **user data**: a composed widget the user
builds in the Widget studio (`#/widgets`), the Dashboard renders after the
built-ins in the same grid, and localStorage persists as plain JSON.

## Instance schema

```ts
interface WidgetInstance {
  id: string;            // assigned by the store; identity, never patchable
  type: string;          // a widget file id from the registry ("TrendArea")
  title: string;         // falls back to the type's own title, then the type id
  size: "sm" | "lg";     // grid units, same promise as built-ins (sm=1, lg=2)
  accent: "brand" | "accent" | "text";  // brand ROLE, not a color
  data?: WidgetDataSpec; // SAME six fields the built-ins declare as meta.data
  notify?: { mode: "above" | "below" | "change"; value?: number };
  enabled: boolean;
}
```

Laws the schema rides on:

- **No second grammar.** The `data` block is validated by the feed engine's
  own `validateWidgetData` (`app/src/lib/widgets/feed.ts`) — a custom widget
  can never out-declare a built-in. The source resolves against the loaded
  schema (`endpoint` is a model id, never a URL); an unresolvable source
  renders the engine's nameable reason, exactly like a built-in.
- **Accents are brand roles, not colors.** The card re-maps
  `--brand-primary` onto `var(--brand-accent)` or `var(--brand-text)` on
  the card wrapper. A rebrand recolors custom widgets exactly like
  built-ins; no hard-coded color enters the tree.
- **One feed engine.** The eight fed built-ins (TrendArea, StatusDonut,
  LeaderBars, HeatStrip, DeltaChip, LiveOrders, TodayRevenue, CompletionGauge)
  accept an optional `data` prop; without it they render their own
  `meta.data`, byte-for-byte as before.

## Persistence and portability

- Store: `app/src/lib/widgets/instances.ts`, capped at 24 instances,
  newest-last order = dashboard order (`moveInstance` swaps neighbours).
- Key: `dad.widgetInstances.v1` (same `dad.` namespace as the other client
  state). Malformed entries are dropped on load — a half-broken instance
  never bricks the dashboard.
- Export/import: all-or-nothing JSON text. One bad entry and nothing
  changes; ids are regenerated on collision. A dashboard is data — copyable
  between devices and brands.

## Threshold notifications

`notify` is evaluated per feed tick in `shouldFire()`:

| mode     | fires when                                   |
| -------- | -------------------------------------------- |
| `above`  | the number crosses above `value` (cold→hot)  |
| `below`  | the number crosses below `value` (cold→hot)  |
| `change` | the number differs from the previous tick    |

- The watched number per feed kind: `count`/`number` → `value`; `delta` →
  `current`; `series` → last bucket; `groups` → `total`.
- **Crossing dedup**: a rule fires once on entering the hot state and stays
  silent while it holds; `change` fires once per actual change after a
  baseline tick. A widget added while already hot alerts exactly once.
- A fired rule goes through the ONE notification store
  (`app/src/lib/notifications.ts`) — the bell badge, the Notifications page
  and OS toasts all read the same list. Events carry
  `source: "widget:<Type>"`.

## Notification center

- Store: newest-first, capped at 50, persisted in `dad.notifications.v1`,
  rehydrated on load (malformed entries dropped). `markRead`, `markAllRead`,
  `clearNotifications`, `unreadCount`.
- OS toasts: `tauri-plugin-notification` — **best-effort**. Permission is
  requested at runtime from the Notifications page's Enable row
  (`notification:default` capability; Android's POST_NOTIFICATIONS prompt
  rides the plugin). Browser mode never imports the plugin (in-app only);
  a missing or broken plugin degrades silently — the in-app center already
  holds the event.
- The bell lives in the sidebar footer and routes through the page
  REGISTRY (the page whose id is `Notifications`), never a hand-typed
  hash — the navMount law.
