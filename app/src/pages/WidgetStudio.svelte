<script module lang="ts">
  export const meta = { title: "Widget studio", path: "/widgets", nav: "main", icon: "grid", order: 12 };
</script>

<script lang="ts">
  /** Widget studio — build custom dashboard widgets out of the DISCOVERED
   *  widget types and the live schema, then persist them as plain JSON.
   *
   *  Laws this page obeys:
   *  - the type list IS the widget registry: a built-in dropped into
   *    src/widgets/ is immediately buildable here, nothing to register;
   *  - the data block is validated by the feed engine's own validateWidgetData
   *    and previewed through the SAME schema-resolved feed — never a guessed
   *    URL, and an unresolvable source shows the engine's nameable reason;
   *  - accents are brand ROLES (brand / accent / text), never colors — a
   *    rebrand recolors custom widgets exactly like built-ins;
   *  - everything persists as plain JSON (localStorage, capped) with
   *    export/import, so a dashboard is copyable between devices and brands;
   *  - a draft that cannot be honoured is refused with a nameable problem,
   *    never half-added.
   */
  import { widgets } from "../widgets";
  import { app } from "../lib/stores";
  import {
    instances,
    addInstance,
    removeInstance,
    updateInstance,
    moveInstance,
    exportInstances,
    importInstances,
    validateInstance,
    type WidgetInstance,
    type AccentRole,
    type NotifyMode,
  } from "../lib/widgets/instances";
  import type { AggregateKind } from "../lib/widgets/feed";
  import WidgetInstanceCard from "../components/WidgetInstanceCard.svelte";
  import Icon from "../components/Icon.svelte";

  const typeName = (file: string) => file.split("/").pop()!.replace(/\.svelte$/, "");

  // ---- draft form state -------------------------------------------------
  let type = $state("TrendArea");
  let title = $state("");
  let size = $state<"sm" | "lg">("sm");
  let accent = $state<AccentRole>("brand");
  let endpoint = $state(""); // model id; "" = auto-pick
  let aggregate = $state<AggregateKind>("bucket");
  let field = $state(""); // field name; "" = auto-pick
  let days = $state(30);
  let pollSec = $state(0); // seconds; 0 = fetch once
  let notifyMode = $state<NotifyMode | "">("");
  let notifyValue = $state(""); // raw text: "" or garbage = refused loudly, never silently 0
  let problem = $state("");
  let flash = $state("");
  let ioText = $state("");
  let ioProblem = $state("");

  const typeInfo = $derived(widgets.find((w) => typeName(w.file) === type));
  const fed = $derived(typeInfo?.data != null);
  const schema = $derived($app.schema);
  const model = $derived(endpoint && schema ? schema.byId[endpoint] : undefined);
  const needsField = $derived(aggregate !== "count");
  const needsDays = $derived(aggregate === "bucket" || aggregate === "delta");

  const draftCheck = $derived(
    validateInstance({
      type,
      title: title.trim() || typeInfo?.title || type,
      size,
      accent,
      ...(fed
        ? {
            data: {
              endpoint,
              aggregate,
              field: needsField ? field : "",
              days,
              pollInterval: Math.round(pollSec * 1000),
            },
          }
        : {}),
      ...(notifyMode
        ? {
            notify:
              notifyMode === "change"
                ? { mode: "change" }
                : {
                    mode: notifyMode,
                    value:
                      notifyValue.trim() === "" || !Number.isFinite(Number(notifyValue))
                        ? Number.NaN // the validator refuses a missing threshold loudly
                        : Number(notifyValue),
                  },
          }
        : {}),
      enabled: true,
    }),
  );
  const draft = $derived("instance" in draftCheck ? draftCheck.instance : null);
  const draftProblem = $derived("problem" in draftCheck ? draftCheck.problem : "");

  function addToDashboard() {
    problem = "";
    flash = "";
    if (!draft) {
      problem = draftProblem;
      return;
    }
    const r = addInstance(draft);
    if ("problem" in r) problem = r.problem;
    else flash = `Added "${r.instance.title}" — it's on your dashboard.`;
  }

  const dot = (a: AccentRole) => (a === "accent" ? "bg-accent" : a === "text" ? "bg-text" : "bg-primary");
</script>

<div class="mx-auto max-w-5xl">
  <div class="mb-6">
    <h1 class="text-2xl font-semibold">Widget studio</h1>
    <p class="text-sm text-text/50">
      compose your own dashboard widgets out of the {widgets.length} built-in types —
      title, size, brand accent, a schema-resolved data source, threshold alerts
    </p>
  </div>

  <!-- your widgets -->
  {#if $instances.length}
    <section class="mb-6">
      <h2 class="mb-2 text-sm font-semibold text-text/70">Your widgets ({$instances.length})</h2>
      <ul class="space-y-2">
        {#each $instances as inst, i (inst.id)}
          <li class="card flex items-center gap-3 p-3">
            <span class="size-3 shrink-0 rounded-full {dot(inst.accent)}" title="accent: {inst.accent}"></span>
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-semibold">{inst.title}</div>
              <div class="text-xs text-text/50">
                {inst.type} · {inst.size}
                {#if inst.notify}· alerts {inst.notify.mode}{inst.notify.value !== undefined ? ` ${inst.notify.value}` : ""}{/if}
                {#if !inst.enabled}· hidden{/if}
              </div>
            </div>
            <button class="btn btn-ghost px-1.5 py-1" title="Move up" disabled={i === 0} onclick={() => moveInstance(inst.id, -1)}>
              <Icon name="left" size={14} />
            </button>
            <button
              class="btn btn-ghost px-1.5 py-1"
              title="Move down"
              disabled={i === $instances.length - 1}
              onclick={() => moveInstance(inst.id, 1)}
            >
              <Icon name="right" size={14} />
            </button>
            <button
              class="btn btn-ghost px-1.5 py-1"
              title={inst.enabled ? "Hide from dashboard" : "Show on dashboard"}
              onclick={() => updateInstance(inst.id, { enabled: !inst.enabled })}
            >
              <Icon name={inst.enabled ? "check" : "x"} size={14} />
            </button>
            <button class="btn btn-ghost px-1.5 py-1" title="Remove" onclick={() => removeInstance(inst.id)}>
              <Icon name="trash" size={14} />
            </button>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <!-- import / export -->
  <section class="mb-6">
    <h2 class="mb-2 text-sm font-semibold text-text/70">Copy your dashboard (JSON)</h2>
    <textarea class="input font-mono text-xs" rows="4" bind:value={ioText}
      placeholder="Export puts your widgets here as JSON; paste JSON and press Import to take them to another device or brand."></textarea>
    {#if ioProblem}<p class="mt-1 text-xs text-primary" role="alert">{ioProblem}</p>{/if}
    <div class="mt-2 flex gap-2">
      <button class="btn btn-ghost text-xs" onclick={() => { ioText = exportInstances(); ioProblem = ""; }}>Export</button>
      <button
        class="btn btn-ghost text-xs"
        onclick={() => {
          const r = importInstances(ioText);
          if ("problem" in r) ioProblem = r.problem;
          else {
            ioProblem = "";
            flash = `Imported ${r.added} ${r.added === 1 ? "widget" : "widgets"}.`;
          }
        }}>Import</button>
    </div>
  </section>

  <!-- builder -->
  <section class="grid gap-6 md:grid-cols-2">
    <div>
      <h2 class="mb-2 text-sm font-semibold text-text/70">New widget</h2>
      <div class="card space-y-4 p-4">
        <label class="block text-sm">
          <span class="mb-1 block text-text/70">Type</span>
          <select class="input" bind:value={type} id="type-select">
            {#each widgets as w (w.file)}
              <option value={typeName(w.file)}>{w.title}{w.data != null ? " — data-fed" : ""}</option>
            {/each}
          </select>
        </label>

        <label class="block text-sm">
          <span class="mb-1 block text-text/70">Title</span>
          <input class="input" bind:value={title} placeholder={typeInfo?.title ?? type} />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="block text-sm">
            <span class="mb-1 block text-text/70">Size</span>
            <select class="input" bind:value={size}>
              <option value="sm">small (1 unit)</option>
              <option value="lg">large (2 units)</option>
            </select>
          </label>
          <label class="block text-sm">
            <span class="mb-1 block text-text/70">Accent</span>
            <select class="input" bind:value={accent}>
              <option value="brand">brand primary</option>
              <option value="accent">brand accent</option>
              <option value="text">brand text</option>
            </select>
          </label>
        </div>

        {#if fed}
          <div class="space-y-4 rounded-lg border border-text/10 p-3">
            <div class="text-xs font-semibold uppercase tracking-wide text-text/50">Data source</div>
            <label class="block text-sm">
              <span class="mb-1 block text-text/70">Model</span>
              <select class="input" bind:value={endpoint}>
                <option value="">auto-pick from this API</option>
                {#each schema?.models ?? [] as m (m.id)}
                  <option value={m.id}>{m.name}</option>
                {/each}
              </select>
            </label>
            <label class="block text-sm">
              <span class="mb-1 block text-text/70">Aggregate</span>
              <select class="input" bind:value={aggregate}>
                <option value="count">count</option>
                <option value="sum">sum</option>
                <option value="avg">average</option>
                <option value="bucket">per-day buckets</option>
                <option value="group">group by enum</option>
                <option value="delta">change vs previous window</option>
              </select>
            </label>
            {#if needsField}
              <label class="block text-sm">
                <span class="mb-1 block text-text/70">Field</span>
                <select class="input" bind:value={field}>
                  <option value="">auto-pick a field</option>
                  {#each model?.fields ?? [] as f (f.name)}
                    <option value={f.name}>{f.name}</option>
                  {/each}
                </select>
              </label>
            {/if}
            {#if needsDays}
              <label class="block text-sm">
                <span class="mb-1 block text-text/70">Days (2–366)</span>
                <input class="input" type="number" min="2" max="366" bind:value={days} />
              </label>
            {/if}
            <label class="block text-sm">
              <span class="mb-1 block text-text/70">Refresh every N seconds (0 = once)</span>
              <input class="input" type="number" min="0" bind:value={pollSec} />
            </label>
          </div>

          <div class="space-y-3 rounded-lg border border-text/10 p-3">
            <div class="text-xs font-semibold uppercase tracking-wide text-text/50">Alerts (notifications)</div>
            <label class="block text-sm">
              <span class="mb-1 block text-text/70">Notify me when…</span>
              <select class="input" bind:value={notifyMode}>
                <option value="">never</option>
                <option value="above">the number goes above a threshold</option>
                <option value="below">the number goes below a threshold</option>
                <option value="change">the number changes</option>
              </select>
            </label>
            {#if notifyMode === "above" || notifyMode === "below"}
              <label class="block text-sm">
                <span class="mb-1 block text-text/70">Threshold</span>
                <input class="input" type="text" inputmode="decimal" id="notify-value" bind:value={notifyValue}
                  placeholder="e.g. 10" />
              </label>
            {/if}
          </div>
        {:else}
          <p class="text-xs text-text/40">
            This type renders on its own — no data source to wire.
          </p>
        {/if}

        {#if problem}<p class="text-xs text-primary" role="alert">{problem}</p>{/if}
        {#if flash}<p class="text-xs text-accent" role="status">{flash}</p>{/if}
        <button class="btn btn-ghost w-full text-sm" onclick={addToDashboard} disabled={!draft}>
          Add to dashboard
        </button>
      </div>
    </div>

    <!-- live preview -->
    <div>
      <h2 class="mb-2 text-sm font-semibold text-text/70">Preview</h2>
      {#if draft}
        <div class={draft.size === "lg" ? "md:col-span-2" : ""}>
          <WidgetInstanceCard inst={draft} />
        </div>
      {:else}
        <div class="card p-4 text-sm text-text/40">{draftProblem}</div>
      {/if}
      <p class="mt-2 text-xs text-text/40">
        The preview runs the real feed engine against your API —
        a source it cannot serve says so instead of guessing a URL.
      </p>
    </div>
  </section>
</div>
