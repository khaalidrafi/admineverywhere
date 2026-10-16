<script lang="ts">
  /** Schema-driven create/edit form.
   *  Renders text/number/boolean/date/datetime/enum-select/FK-dropdown,
   *  driven entirely by FieldSpecs. Client-side required validation plus
   *  DRF 400 field errors rendered under each input.
   */
  import { get } from "svelte/store";
  import { app, effectiveConfig, handleApiError, toast } from "../lib/stores";
  import { ApiError, createRecord, fetchAllRecords, fieldErrors, updateRecord } from "../lib/api";
  import Icon from "./Icon.svelte";
  import { toISOOrNull } from "../lib/utils";
  import type { FieldSpec, ModelSpec, RecordRow } from "../lib/types";

  let {
    model,
    record = null,
    onclose,
    onsaved,
  }: {
    model: ModelSpec;
    record?: RecordRow | null;
    onclose: () => void;
    onsaved: () => void;
  } = $props();

  const editable = $derived(model.fields.filter((f) => !f.readOnly && f.type !== "json"));

  let values = $state<Record<string, any>>({});
  let errors = $state<Record<string, string>>({});
  let busy = $state(false);
  let fkOptions = $state<Record<string, RecordRow[]>>({});
  let fkLoading = $state<Record<string, boolean>>({});

  function initValues() {
    const v: Record<string, any> = {};
    for (const f of editable) {
      const raw = record?.[f.name];
      if (f.type === "boolean") {
        v[f.name] = Boolean(raw);
      } else if (raw === null || raw === undefined) {
        v[f.name] = "";
      } else if (f.type === "date") {
        v[f.name] = String(raw).slice(0, 10);
      } else if (f.type === "datetime") {
        v[f.name] = String(raw).slice(0, 16); // datetime-local format
      } else {
        v[f.name] = raw;
      }
    }
    values = v;
    errors = {};
  }

  // initial values + FK option lists
  initValues();
  const fkTargets = [...new Set(editable.filter((f) => f.type === "fk" && f.fkModel)
    .map((f) => f.fkModel!))];
  for (const target of fkTargets) {
    fkLoading[target] = true;
    const targetModel = get(app).schema?.byId[target];
    if (!targetModel) {
      fkLoading[target] = false;
      continue;
    }
    fetchAllRecords(effectiveConfig(), get(app).token || null, targetModel)
      .then((rows) => (fkOptions[target] = rows))
      .catch((err) => handleApiError(err))
      .finally(() => (fkLoading[target] = false));
  }

  function fieldPlaceholder(f: FieldSpec): string {
    switch (f.type) {
      case "number": return "0";
      case "date": return "YYYY-MM-DD";
      case "datetime": return "YYYY-MM-DD HH:MM";
      case "fk": return "Select…";
      default: return f.name.replace(/_/g, " ");
    }
  }

  function fkLabel(f: FieldSpec, row: RecordRow): string {
    const target = get(app).schema?.byId[f.fkModel!];
    const label = target ? row[target.labelField] : row.name ?? row.id;
    return label !== undefined && label !== null ? String(label) : `#${row.id}`;
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    for (const f of editable) {
      const v = values[f.name];
      if (f.required && f.type !== "boolean" && (v === "" || v === null || v === undefined)) {
        errs[f.name] = "This field is required.";
      }
    }
    errors = errs;
    return Object.keys(errs).length === 0;
  }

  function buildPayload(): Record<string, any> {
    const payload: Record<string, any> = {};
    for (const f of editable) {
      const v = values[f.name];
      /** empty + not explicitly nullable -> OMIT the key entirely:
       *  DRF then applies field defaults; sending null would 400 on
       *  non-nullable fields (e.g. DecimalField(default=0)). */
      const empty = v === "" || v === null || v === undefined;
      const omit = empty && !f.nullable;
      switch (f.type) {
        case "boolean":
          payload[f.name] = Boolean(v);
          break;
        case "number":
        case "fk":
          payload[f.name] = omit ? undefined : empty ? null : Number(v);
          break;
        case "date":
          payload[f.name] = omit ? undefined : v || null;
          break;
        case "datetime":
          payload[f.name] = omit ? undefined : toISOOrNull(v);
          break;
        default:
          payload[f.name] = empty ? (f.nullable ? null : "") : v;
      }
    }
    return payload;
  }

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    if (busy) return;
    if (!validate()) return;
    busy = true;
    try {
      const payload = buildPayload();
      if (record?.id !== undefined) {
        await updateRecord(effectiveConfig(), get(app).token || null, model, record.id, payload);
        toast("success", `${model.name} updated`);
      } else {
        await createRecord(effectiveConfig(), get(app).token || null, model, payload);
        toast("success", `${model.name} created`);
      }
      onsaved();
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        errors = { ...errors, ...fieldErrors(err.detail) };
        toast("error", "Some fields need attention");
      } else {
        handleApiError(err);
      }
    } finally {
      busy = false;
    }
  }
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onclose()} />

<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
     onclick={(e) => e.target === e.currentTarget && onclose()}>
  <form
    class="card max-h-[90vh] w-full max-w-lg overflow-y-auto p-6 shadow-2xl"
    onsubmit={submit}
  >
    <div class="mb-5 flex items-center justify-between">
      <h2 class="text-lg font-semibold">
        {record?.id !== undefined ? `Edit ${model.name} #${record.id}` : `New ${model.name}`}
      </h2>
      <button type="button" class="btn btn-ghost p-2" onclick={onclose} aria-label="Close">
        <Icon name="x" size={16} />
      </button>
    </div>

    <div class="flex flex-col gap-4">
      {#each editable as f (f.name)}
        <div>
          <label class="mb-1 flex items-baseline gap-2 text-xs font-medium text-text/60" for={`f-${f.name}`}>
            {f.name.replace(/_/g, " ")}
            {#if f.required}<span class="text-primary">*</span>{/if}
            {#if f.type === "fk"}<span class="text-text/30">(fk → {f.fkModel})</span>{/if}
          </label>

          {#if f.type === "boolean"}
            <label class="flex cursor-pointer items-center gap-3 rounded-lg border border-text/10 px-3 py-2.5">
              <input id={`f-${f.name}`} type="checkbox" class="size-4 accent-[var(--brand-primary)]"
                     bind:checked={values[f.name]} />
              <span class="text-sm">{values[f.name] ? "Yes" : "No"}</span>
            </label>

          {:else if f.type === "enum"}
            <select id={`f-${f.name}`} class="input" bind:value={values[f.name]}>
              <option value="">—</option>
              {#each f.choices ?? [] as choice (choice)}
                <option value={choice}>{choice}</option>
              {/each}
            </select>

          {:else if f.type === "fk"}
            <select id={`f-${f.name}`} class="input" bind:value={values[f.name]} disabled={fkLoading[f.fkModel!]}>
              <option value="">
                {fkLoading[f.fkModel!] ? "Loading options…" : "—"}
              </option>
              {#each fkOptions[f.fkModel!] ?? [] as opt (String(opt.id))}
                <option value={opt.id}>{fkLabel(f, opt)}</option>
              {/each}
            </select>

          {:else if f.type === "number"}
            <input id={`f-${f.name}`} class="input" type="number"
                   step={f.format === "decimal" ? "0.01" : "1"}
                   placeholder={fieldPlaceholder(f)} bind:value={values[f.name]} />

          {:else if f.type === "date"}
            <input id={`f-${f.name}`} class="input" type="date" bind:value={values[f.name]} />

          {:else if f.type === "datetime"}
            <input id={`f-${f.name}`} class="input" type="datetime-local" bind:value={values[f.name]} />

          {:else}
            <input id={`f-${f.name}`} class="input" type="text"
                   maxlength={f.maxLength ?? undefined}
                   placeholder={fieldPlaceholder(f)} bind:value={values[f.name]} />
          {/if}

          {#if errors[f.name]}
            <div class="mt-1 text-xs text-red-400">{errors[f.name]}</div>
          {/if}
        </div>
      {/each}
    </div>

    <div class="mt-6 flex justify-end gap-3">
      <button type="button" class="btn btn-ghost" onclick={onclose}>Cancel</button>
      <button type="submit" class="btn btn-primary" disabled={busy}>
        {#if busy}<Icon name="refresh" size={16} class="animate-spin" />{/if}
        {record?.id !== undefined ? "Save changes" : `Create ${model.name}`}
      </button>
    </div>
  </form>
</div>
