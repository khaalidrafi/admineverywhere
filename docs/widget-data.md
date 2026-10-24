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

## Proof (mount-level, not module-level)

`feed.ts` is unit-pinned by `widgetFeed.test.ts`, but a chart that maps the
wrong field, draws slice geometry off the wrong quantity, or forgets its own
page cap keeps that suite green — the same failure shape `chatMount`/
`brandingMount` were written against. The components are therefore judged
through their DOM and their requests:

- `widgetMount.test.ts` — `HeatStrip` day cells, `DeltaChip` poll + timer death.
- `chartMount.test.ts` — `StatusDonut` (dash/offset geometry from the group
  fraction, top-5 fold into `(other)`, total in the ring, nameable `empty`
  with ZERO requests, friendly `error`), `LeaderBars` (value-descending sort,
  top-6 cut, percent-of-max widths, and the caption: `grouped from N records`
  with N measured against a server whose pagination never ends — 300 rows at
  the default `rowCap`, so the number is proven to be the cap and not the
  fixture), `TrendArea` (30-day point set matches the
  day keys, flat baseline when the window is all zeros) and `ActivityChart`
  — which predates the engine, so its own model-picker (a readOnly
  `created_at` beats every other timestamp) and its 3-page walk cap are pinned
  against a server whose pagination never ends. Every request is asserted
  against the schema-discovered `listPath` with the token header, never a
  concatenated URL.
- `feedGridMount.test.ts` — the same components, but reached through the grid
  instead of an `import`. `dashboardMount.test.ts` keeps `$app.schema` null on
  purpose, so nothing mounted the grid against a live schema, and the per-component
  harnesses import the chart they want — a door no product code walks. This one
  reads `widgets[]` and takes every entry whose `data` block carries an
  `aggregate` (a registry that stopped exporting `data`, or a built-in whose
  declaration silently left the domain, fails the floor rather than grading a
  shorter list), then proves four things the other files cannot see:
  **every** fed widget paints chart DOM off the globbed declaration (skeleton
  gone, no reason line, real chart); the feeds are **base + discovered
  `listPath` + page query** as one well-formed URL — the exact
  `http://hostapi…` corruption `docs/custom-actions.md` records for `actionPath`
  is red here too; a schema that arrives **after** mount wakes every feed (the
  `$effect` law, checked at grid level, so reverting a widget to `onMount` is
  a named failure, not a card that quietly stays a skeleton); and a schema that
  can feed nothing leaves each fed cell rendering the engine's own wording
  (`no model in this API has … to aggregate`) with no chart drawn over it, no
  second request barrage, and no request to a pathname the schema never
  discovered.

Mutant-checked: dropping the fold, the sort, the offset step, the page cap and
the picker preference each fail a named test; so does `DEFAULT_ROW_CAP` 300→400
(the caption test) and reverting the caption to the old `first N records`.
`feedGridMount.test.ts` carries its own seven-mutant battery — registry drops
`meta.data` (floor fires), registry drops one widget's declaration (the
aggregate-coverage door fires), a chart reads the schema non-reactively (the
wake test fires alone), a refused feed probes a guessed `/api/trend/` (red,
naming the path), a chart stops calling the engine (red, naming the widget),
a chart swallows its reason for "No data to show." (red, naming the widget),
a chart draws bars over its own refusal (red), the delta window compares
against itself (the `5 vs 1` literal fires) and `listRecords` loses the
leading `/` of the discovered path (the origin-shape door fires). 9/9 killed,
sources restored byte-identical between runs.

## Caption law

`FeedResult.groups.total` is `rows.length` — however many rows the feed
actually consumed, capped at `rowCap`. It is NOT a statement that a cap was
applied: a 50-row API returns 50 and says "first 50 records", which promises a
truncation that never happened. Say what the number is — `grouped from N
records` — and mean it in both directions. The same reasoning binds any widget
that prints a fetched count.

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
6. A timer the widget arms itself — a flip, a caret blink, a deferred swap —
   obeys the same law as the poll: clear it from an `$effect` cleanup, because
   `startWidgetFeed`'s stop fn only owns the feed's timer. `QuoteCard` had a
   225 ms flip timer with no cleanup (a click then unmount fired the swap
   against a destroyed component) and `gapMount.test.ts` now pins the death:
   click, unmount mid-flip, advance past 225 ms, assert the quote picker drew
   NO extra random value.
