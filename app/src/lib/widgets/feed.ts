/** Widget data feeds (FR-R008) — the polling + aggregation engine behind
 *  drop-in widgets that declare `meta.data = { endpoint, aggregate, pollInterval }`.
 *
 *  Laws this module obeys (same as actionPath/resolveAxis/exportPath):
 *  - Requests go ONLY through schema-discovered model paths (listRecords /
 *    fetchAllRecords); `endpoint` is a model id resolved against the loaded
 *    schema, never a hand-concatenated URL.
 *  - An unresolvable source resolves to a friendly "empty" render with a
 *    nameable reason — never a silent failure, never an error barrage.
 *  - pollInterval is clamped to a floor so a mistyped meta cannot DoS the
 *    user's own API; a non-positive interval means "fetch once".
 */
import { get } from "svelte/store";
import { app, effectiveConfig, handleApiError } from "../stores";
import { fetchAllRecords, listRecords } from "../api";
import type { AdminSchema, FieldSpec, ModelSpec, RecordRow } from "../types";

export type AggregateKind = "count" | "sum" | "avg" | "bucket" | "group" | "delta";

export interface WidgetDataSpec {
  /** schema-discovered model id (e.g. "order"); empty string = auto-pick */
  endpoint: string;
  aggregate: AggregateKind;
  /** field name for sum/avg/bucket/delta; enum field for group; "" = auto-pick */
  field: string;
  /** days covered by bucket/delta (delta compares this window vs the previous one) */
  days: number;
  /** milliseconds between refreshes; <= 0 means fetch once */
  pollInterval: number;
  /** hard cap on rows fetched for aggregate kinds other than count */
  rowCap: number;
}

export interface FeedProblem {
  reason: string;
}

export type FeedResult =
  | { kind: "count"; value: number | null; label: string }
  | { kind: "number"; value: number | null; label: string }
  | { kind: "series"; days: string[]; values: number[]; label: string }
  | { kind: "groups"; groups: { name: string; value: number }[]; total: number; label: string }
  | { kind: "delta"; current: number; previous: number | null; pct: number | null; label: string };

const KINDS: AggregateKind[] = ["count", "sum", "avg", "bucket", "group", "delta"];
const MIN_POLL_MS = 5_000;
const DEFAULT_ROW_CAP = 300;

/** Validate whatever `<script module>` exported as `meta.data`. Never throws:
 *  a broken declaration comes back as a nameable problem, same law as the
 *  page registry's patternProblem(). */
export function validateWidgetData(raw: unknown): { spec: WidgetDataSpec } | { problem: FeedProblem } {
  if (raw == null) return { problem: { reason: "no data spec given" } };
  if (typeof raw !== "object" || Array.isArray(raw)) {
    return { problem: { reason: "meta.data must be an object {endpoint, aggregate, pollInterval}" } };
  }
  const d = raw as Record<string, unknown>;
  const endpoint = d.endpoint == null ? "" : String(d.endpoint);
  const field = d.field == null ? "" : String(d.field);
  const aggregate = (d.aggregate == null ? "count" : String(d.aggregate)) as AggregateKind;
  if (!KINDS.includes(aggregate)) {
    return { problem: { reason: `unknown aggregate "${aggregate}" (one of ${KINDS.join(", ")})` } };
  }
  let days = typeof d.days === "number" && Number.isFinite(d.days) ? Math.trunc(d.days) : 14;
  days = Math.min(Math.max(days, 2), 366);
  let pollInterval = typeof d.pollInterval === "number" && Number.isFinite(d.pollInterval) ? Math.trunc(d.pollInterval) : 0;
  if (pollInterval > 0 && pollInterval < MIN_POLL_MS) pollInterval = MIN_POLL_MS;
  const rowCap =
    typeof d.rowCap === "number" && Number.isFinite(d.rowCap)
      ? Math.min(Math.max(Math.trunc(d.rowCap), 1), 1000)
      : DEFAULT_ROW_CAP;
  return { spec: { endpoint, aggregate, field, days, pollInterval, rowCap } };
}

/** Rank a datetime field for auto-pick (same preference order ActivityChart
 *  learned: readOnly created_at first, manual datetimes last). */
function dtRank(f: FieldSpec): number {
  return (f.type === "datetime" || f.type === "date" ? 0 : 99) + (f.readOnly ? 0 : 10) + (f.name === "created_at" ? 0 : 1);
}

function isDateish(f: FieldSpec): boolean {
  return f.type === "datetime" || f.type === "date";
}

/** Resolve a declared source against the schema, or auto-pick a sensible one.
 *  Returns null (with the reason on the returned object) when the API has
 *  nothing that can feed this widget. */
export function resolveTarget(
  schema: AdminSchema,
  spec: WidgetDataSpec,
): { model: ModelSpec; field: FieldSpec | null } | { problem: FeedProblem } {
  if (spec.endpoint) {
    const model = schema.byId[spec.endpoint];
    if (!model) {
      return { problem: { reason: `model "${spec.endpoint}" is not in this API's schema` } };
    }
    if (spec.field) {
      const f = model.byName[spec.field];
      if (!f) {
        return { problem: { reason: `model "${spec.endpoint}" has no field "${spec.field}"` } };
      }
      return { model, field: f };
    }
    return { model, field: autoField(model, spec.aggregate) };
  }
  // No endpoint declared: pick the model+field best suited to the aggregate.
  let best: { model: ModelSpec; field: FieldSpec; score: number } | null = null;
  for (const m of schema.models) {
    for (const f of m.fields) {
      let score = 999;
      if (spec.aggregate === "group") {
        if (!f.choices || f.choices.length < 2) continue;
        score = (f.name === "status" ? 0 : 1) + f.choices.length / 1000;
      } else if (spec.aggregate === "bucket" || spec.aggregate === "delta") {
        if (!isDateish(f)) continue;
        score = dtRank(f);
      } else if (spec.aggregate === "sum" || spec.aggregate === "avg") {
        if (f.type !== "number" && f.format !== "decimal") continue;
        score = (f.name === "total" || f.name === "amount" ? 0 : 1) + (f.readOnly ? 10 : 0);
      } else {
        // count needs no field; prefer the model with a created_at for the label
        score = m.byName["created_at"] ? 0 : 1;
      }
      if (!best || score < best.score) best = { model: m, field: f, score };
    }
    if (spec.aggregate === "count" && best) break;
  }
  if (!best) {
    const need =
      spec.aggregate === "group"
        ? "an enum (choices) field"
        : spec.aggregate === "sum" || spec.aggregate === "avg"
          ? "a numeric field"
          : spec.aggregate === "count"
            ? "any model"
            : "a date or datetime field";
    return { problem: { reason: `no model in this API has ${need} to aggregate` } };
  }
  return { model: best.model, field: spec.aggregate === "count" ? null : best.field };
}

function autoField(model: ModelSpec, aggregate: AggregateKind): FieldSpec | null {
  if (aggregate === "group") {
    return model.fields.find((f) => f.choices && f.choices.length >= 2) ?? null;
  }
  if (aggregate === "bucket" || aggregate === "delta") {
    const dated = model.fields.filter(isDateish).sort((a, b) => dtRank(a) - dtRank(b));
    return dated[0] ?? null;
  }
  if (aggregate === "sum" || aggregate === "avg") {
    return model.fields.find((f) => f.type === "number" || f.format === "decimal") ?? null;
  }
  return null;
}

export function fieldLabel(target: { model: ModelSpec; field: FieldSpec | null }): string {
  return target.field ? `${target.model.name} · ${target.field.name.replace(/_/g, " ")}` : target.model.name;
}

function toNumber(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v); // DRF sends decimals as strings — coerce, never re-flow
  return Number.isFinite(n) ? n : null;
}

/** Last N calendar-day keys, oldest first, as YYYY-MM-DD (local time). */
export function dayKeys(days: number, now: Date = new Date()): string[] {
  const keys: string[] = [];
  for (let d = days - 1; d >= 0; d--) {
    const date = new Date(now);
    date.setDate(now.getDate() - d);
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    keys.push(`${y}-${m}-${day}`);
  }
  return keys;
}

/** Pure aggregation over already-fetched rows — the seam every chart tests
 *  against, no fetch and no clock involved. */
export function computeAggregate(
  spec: WidgetDataSpec,
  target: { model: ModelSpec; field: FieldSpec | null },
  rows: RecordRow[],
  totalCount: number | null,
  now: Date = new Date(),
): FeedResult {
  const label = fieldLabel(target);
  switch (spec.aggregate) {
    case "count":
      return { kind: "count", value: totalCount ?? rows.length, label };
    case "sum": {
      let sum = 0;
      let seen = false;
      for (const r of rows) {
        const n = toNumber(r[target.field!.name]);
        if (n !== null) { sum += n; seen = true; }
      }
      return { kind: "number", value: seen ? sum : null, label };
    }
    case "avg": {
      let sum = 0;
      let n0 = 0;
      for (const r of rows) {
        const n = toNumber(r[target.field!.name]);
        if (n !== null) { sum += n; n0++; }
      }
      return { kind: "number", value: n0 ? sum / n0 : null, label };
    }
    case "bucket": {
      const keys = dayKeys(spec.days, now);
      const byDay = new Map(keys.map((k) => [k, 0]));
      const f = target.field!.name;
      for (const r of rows) {
        const k = String(r[f] ?? "").slice(0, 10);
        if (byDay.has(k)) byDay.set(k, (byDay.get(k) ?? 0) + 1);
      }
      return { kind: "series", days: keys, values: keys.map((k) => byDay.get(k)!), label };
    }
    case "group": {
      const f = target.field!.name;
      const counts = new Map<string, number>();
      for (const r of rows) {
        const key = r[f] == null || r[f] === "" ? "(unset)" : String(r[f]);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      // declared choices first (schema order = the enum's own order), then
      // any values the data carries that the schema did not predict
      const order = (target.field?.choices ?? []).map(String);
      const names = [...order.filter((o) => !o.startsWith("__all__")), ...[...counts.keys()].filter((k) => !order.includes(k))];
      const groups = names
        .map((name) => ({ name, value: counts.get(name) ?? 0 }))
        .filter((g) => g.value > 0);
      return { kind: "groups", groups, total: rows.length, label };
    }
    case "delta": {
      const keys = dayKeys(spec.days, now);
      const currentKey = new Set(keys);
      const prevKeys = dayKeys(spec.days, new Date(now.getTime() - spec.days * 86_400_000));
      const prevKey = new Set(prevKeys);
      const f = target.field!.name;
      let current = 0;
      let previous = 0;
      for (const r of rows) {
        const k = String(r[f] ?? "").slice(0, 10);
        if (currentKey.has(k)) current++;
        else if (prevKey.has(k)) previous++;
      }
      const pct = previous > 0 ? ((current - previous) / previous) * 100 : null;
      return { kind: "delta", current, previous: previous, pct, label };
    }
  }
}

/** One fetch + aggregate pass against the resolved target. */
export async function runFeedOnce(
  spec: WidgetDataSpec,
  target: { model: ModelSpec; field: FieldSpec | null },
): Promise<FeedResult> {
  const cfg = effectiveConfig();
  const token = get(app).token || null;
  if (spec.aggregate === "count") {
    const page = await listRecords(cfg, token, target.model, { page: 1, pageSize: 1 });
    return computeAggregate(spec, target, [], page.count);
  }
  const rows = await fetchAllRecords(cfg, token, target.model, spec.rowCap);
  return computeAggregate(spec, target, rows, null);
}

export type FeedState =
  | { status: "loading" }
  | { status: "empty"; reason: string }
  | { status: "ready"; result: FeedResult }
  | { status: "error"; message: string };

/** Start a feed against meta.data for the CURRENT schema. Returns a stop fn —
 *  call it from the $effect cleanup so unmount always kills the timer.
 *  Polling never overlaps: the next tick is scheduled after the previous
 *  fetch settles, and the first tick is immediate. */
export function startWidgetFeed(
  raw: unknown,
  setState: (s: FeedState) => void,
  schema: AdminSchema,
): () => void {
  const validated = validateWidgetData(raw);
  if ("problem" in validated) {
    setState({ status: "empty", reason: validated.problem.reason });
    return () => {};
  }
  const spec = validated.spec;
  const resolved = resolveTarget(schema, spec);
  if ("problem" in resolved) {
    setState({ status: "empty", reason: resolved.problem.reason });
    return () => {};
  }
  const target = resolved;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  setState({ status: "loading" });

  const tick = async () => {
    if (stopped) return;
    try {
      const result = await runFeedOnce(spec, target);
      if (stopped) return;
      setState({ status: "ready", result });
    } catch (err) {
      if (stopped) return;
      handleApiError(err);
      setState({ status: "error", message: "Could not load this widget's data." });
    }
    if (!stopped && spec.pollInterval > 0) {
      timer = setTimeout(tick, spec.pollInterval);
    }
  };
  void tick();

  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
  };
}
