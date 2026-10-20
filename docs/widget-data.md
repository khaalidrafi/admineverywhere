# Widget data sources (FR-R008) — the `meta.data` contract

One drop-in widget may declare a **data source**; the feed engine
(`app/src/lib/widgets/feed.ts`) validates it, resolves it against the live
OpenAPI schema, fetches through the existing `api.ts` helpers and hands the
component a ready / empty / error state. The drop-in law is unchanged: one
`.svelte` file in `app/src/widgets/`, nothing to register.

## Declaration

```svelte
<script module lang="ts">
  export const meta = {
    title: "7-day change",
    size: "sm",
    data: {
      endpoint: "orders",   // optional: schema model id (NOT a URL)
      field: "total",       // optional: field to aggregate
      aggregate: "delta",   // count | sum | avg | bucket | group | delta
      days: 7,              // bucket/delta window (clamped to [2, 366])
      pollInterval: 60000,  // ms — 0/absent fetches once; floor-clamped to 5s
      rowCap: 300,          // hard fetch cap for row-based aggregates
    },
  };
</script>
```

`<script module>` is static (no runes), so the declaration carries literal
strings — the feed resolves them at runtime against `$app.schema`.

## Resolution laws (same family as `actionPath` / `resolveAxis` / `exportPath`)

- **`endpoint` is a model id, not a URL.** It resolves through
  `schema.byId`; the request then goes to that model's schema-discovered
  `listPath` via `listRecords` / `fetchAllRecords`. Nothing is ever
  concatenated onto `apiUrl`.
- **Unknown source = friendly empty with a nameable reason**, not a crash,
  not a spinner, not an error toast storm: `"model "invoices" is not in
  this API's schema"`, `"no model in this API has an enum (choices) field
  to aggregate"`. The widget still renders — visibly useless rather than
  silently broken.
- **No `endpoint`/`field` declared = auto-pick**, and the picker encodes the
  lessons of this repo: `group` prefers an enum field named `status`;
  `bucket`/`delta` prefer a *readOnly* `created_at` over manual datetimes;
  `sum`/`avg` prefer `total`/`amount` over readOnly counters.
- **Polling cannot run away**: `pollInterval` is floored at 5 000 ms; the
  next tick is scheduled only after the previous fetch settles (no overlap
  even on a slow API); the `$effect` cleanup kills the timer on unmount, and
  a late response after stop cannot resurrect the widget.
- **Decimals stay strings on the wire** — `toNumber` coerces for math and
  the charts never re-flow the value back into the row.

## Aggregates → results

| aggregate | fetch | FeedResult | natural chart |
| --- | --- | --- | --- |
| `count` | 1-row page, server `count` | `{value}` | stat tile |
| `sum` / `avg` | rows ≤ `rowCap` | `{value}` | stat tile, delta |
| `bucket` | rows ≤ `rowCap` | `{days[], values[]}` | area, heat-strip, line |
| `group` | rows ≤ `rowCap` | `{groups[], total}` ordered by declared choices, unseen values appended, nulls → `(unset)` | donut, hbar |
| `delta` | rows ≤ `rowCap` | `{current, previous, pct|null}` (`pct` null when the previous window was empty — show "new", not ÷0) | chip |

## Shipped examples

`TrendArea` (30-day area), `StatusDonut` (enum share), `LeaderBars` (top
groups), `HeatStrip` (35-day strip), `DeltaChip` (7-day momentum, the one
built-in that polls) — all auto-resolve, so they follow any DRF schema;
`ActivityChart` remains the line chart that predates the contract.

## Copy checklist for client projects

1. Drop one `.svelte` in `app/src/widgets/`; export `meta` from
   `<script module>` with the `data` block above.
2. In the instance script: `$effect` on `$app.schema`, return the stop fn
   from `startWidgetFeed(meta.data, setState, schema)`.
3. Render all four states (`loading` skeleton, `empty` reason, `error`
   message, `ready` chart). Colors only from `--brand-*` / `text-text`
   utilities.
4. Pin `endpoint`/`field` for your own API; leave them out to stay
   schema-derived and generic.
5. Never compute against `window.__TAURI_INTERNALS__`-specific paths —
   web mode and Tauri mode share this exact code path.
