/** Kanban axes (FR-R004) — the DECLARED grouping behind the board view.

docs/independent-enums.md §6 is the governing rule: a board groups records by
exactly one enum field, and that field must be DECLARED — never guessed from
"the field named status" or "the first enum field on the model", because on a
model with both `status` and `priority` either guess can be wrong and guessing
is the cross-derivation §3 forbids. So a model with no entry here gets no
kanban toggle at all.

Two kinds of axis, and the difference is not cosmetic:
  - `via: "transition"` — the field is governed by the R-001 state machine, so a
    drop fires POST <listPath><id>/transition/ and the server is the authority
    on legality (the UI only pre-filters to the machine's legal targets).
  - `via: "patch"` — a free enum. A drop is a plain PATCH carrying exactly one
    key, the axis field; nothing else on the record is touched (guardrail 1).

A declaration that contradicts itself is refused rather than honoured:
a transition axis needs the machine (guardrail 5 — otherwise the UI offers moves
the server rejects), and a lifecycle field may not be declared `patch`, which
would bypass the machine the backend enforces. Refusals are reported through
`axisProblem()` so the reason is diagnosable instead of a silently missing view.
*/
import type { ModelSpec, RecordRow } from "./types";
import {
  getStatusField,
  getLegalTransitions,
  hasLifecycle,
  isTransitionLegal,
  statusTransitions,
} from "./statusTransitions";

export type MoveVia = "transition" | "patch";

export interface KanbanAxis {
  /** the enum field the board groups by */
  field: string;
  /** how a drop moves a record: the R-001 machine, or a one-field PATCH */
  via: MoveVia;
  /** explicit column order; omit to derive it (states for a lifecycle axis, the
   *  field's own choices for a free enum) */
  columns?: string[];
}

/** Column key for records whose axis value is empty or not a declared state.
 *  Read-only: it exists so a board never silently drops a record. */
export const UNASSIGNED = "__unassigned__";

/** Declared axes, keyed by model id (the url segment), exactly like the
 *  transition registry — never by field name. */
export const kanbanAxes: Record<string, KanbanAxis> = {
  orders: { field: "status", via: "transition" },
};

export interface ResolvedAxis {
  modelId: string;
  field: string;
  via: MoveVia;
  /** declared column order, always non-empty */
  columns: string[];
}

/** Why a declaration is refused, or null when it is sound. */
export function axisProblem(
  model: ModelSpec | undefined | null,
  source: Record<string, KanbanAxis> = kanbanAxes,
): string | null {
  if (!model) return "no model";
  const declared = source[model.id];
  if (!declared) return null; // nothing declared is not a defect, it is no board
  const spec = model.byName[declared.field];
  if (!spec) return `declared axis field "${declared.field}" is not a field of "${model.id}"`;
  if (spec.type !== "enum") {
    return `declared axis field "${declared.field}" is type "${spec.type}", not an enum`;
  }
  const lifecycle = hasLifecycle(model.id) && getStatusField(model.id) === declared.field;
  if (declared.via === "transition" && !lifecycle) {
    return `"${model.id}.${declared.field}" has no R-001 state machine — declare it via "patch", or drop the axis`;
  }
  if (declared.via === "transition" && !model.transitionPath) {
    return `"${model.id}.${declared.field}" moves through POST ${model.detailPath}transition/, which this API does not document — the board is refused rather than dropped onto a 404`;
  }
  if (declared.via === "patch" && lifecycle) {
    return `"${model.id}.${declared.field}" is lifecycle-governed; a "patch" axis would bypass the machine — declare it via "transition"`;
  }
  const columns = columnsFor(declared, model, spec.choices);
  if (columns.length === 0) {
    return `axis "${model.id}.${declared.field}" resolves to zero columns (give it "columns" or choices)`;
  }
  return null;
}

function columnsFor(declared: KanbanAxis, model: ModelSpec, choices?: string[]): string[] {
  if (declared.columns?.length) return [...declared.columns];
  if (declared.via === "transition") return [...(statusTransitions[model.id]?.states ?? [])];
  return [...(choices ?? [])];
}

/** The board axis for a model, or null when there is none / it is refused.
 *  `null` is what removes the kanban toggle from the page. */
export function resolveAxis(
  model: ModelSpec | undefined | null,
  source: Record<string, KanbanAxis> = kanbanAxes,
): ResolvedAxis | null {
  if (!model) return null;
  const declared = source[model.id];
  if (!declared) return null;
  if (axisProblem(model, source)) return null;
  const spec = model.byName[declared.field];
  return {
    modelId: model.id,
    field: declared.field,
    via: declared.via,
    columns: columnsFor(declared, model, spec?.choices),
  };
}

export interface KanbanColumn {
  key: string;
  label: string;
  rows: RecordRow[];
  /** the unassigned bucket is display-only */
  accepts: boolean;
}

/** Group the loaded rows by the axis field. Every declared column appears even
 *  when empty (an empty column is the point of a board), and any record whose
 *  value is empty or outside the declared set lands in a trailing unassigned
 *  column instead of disappearing. */
export function boardColumns(rows: RecordRow[], axis: ResolvedAxis): KanbanColumn[] {
  const buckets = new Map<string, RecordRow[]>();
  for (const key of axis.columns) buckets.set(key, []);
  const unassigned: RecordRow[] = [];
  for (const row of rows) {
    const value = row[axis.field];
    const key = value === null || value === undefined || value === ""
      ? UNASSIGNED
      : String(value);
    if (key === UNASSIGNED || !buckets.has(key)) unassigned.push(row);
    else buckets.get(key)!.push(row);
  }
  const columns: KanbanColumn[] = axis.columns.map((key) => ({
    key,
    label: key,
    rows: buckets.get(key) ?? [],
    accepts: true,
  }));
  if (unassigned.length > 0) {
    columns.push({ key: UNASSIGNED, label: "Unassigned", rows: unassigned, accepts: false });
  }
  return columns;
}

/** Columns a record may legally move to right now. A lifecycle axis offers
 *  only the machine's next states; a free enum offers every other value. */
export function reachableColumns(axis: ResolvedAxis, current: any): string[] {
  const from = current === null || current === undefined ? "" : String(current);
  if (axis.via === "transition") {
    return getLegalTransitions(axis.modelId, from).filter((t) => axis.columns.includes(t));
  }
  return axis.columns.filter((c) => c !== from);
}

export type MovePlan =
  | { ok: true; via: MoveVia; column: string; body: Record<string, any> }
  | { ok: false; reason: string };

function reject(reason: string): MovePlan {
  return { ok: false, reason };
}

/** Decide what a drop means BEFORE anything is sent. The returned `body` is
 *  exactly the request payload: `{transition: target}` for the R-001 API, or a
 *  single-key object for a free enum (guardrail 1 — one field, nothing else). */
export function planMove(
  axis: ResolvedAxis,
  row: RecordRow,
  targetColumn: string,
): MovePlan {
  if (row.id === undefined || row.id === null) return reject("record has no id — cannot be moved");
  if (targetColumn === UNASSIGNED) {
    return reject(`"${axis.field}" must be set to a declared value, not cleared here`);
  }
  if (!axis.columns.includes(targetColumn)) {
    return reject(`"${targetColumn}" is not a declared column of "${axis.field}"`);
  }
  const current = row[axis.field];
  const from = current === null || current === undefined ? "" : String(current);
  if (from === targetColumn) return reject(`already in "${targetColumn}"`);
  if (axis.via === "transition") {
    if (!isTransitionLegal(axis.modelId, from, targetColumn)) {
      const allowed = getLegalTransitions(axis.modelId, from);
      return reject(
        `illegal transition: '${from || "(unset)"}' -> '${targetColumn}' (allowed from current state: ${allowed.length ? allowed.join(", ") : "none — terminal"})`,
      );
    }
    return { ok: true, via: "transition", column: targetColumn, body: { transition: targetColumn } };
  }
  return { ok: true, via: "patch", column: targetColumn, body: { [axis.field]: targetColumn } };
}

/** Human label for a card's headline field. */
export function cardLabel(model: ModelSpec, row: RecordRow): string {
  const label = row[model.labelField];
  if (label !== null && label !== undefined && label !== "") return String(label);
  return row.id !== undefined ? `${model.name} #${row.id}` : model.name;
}
