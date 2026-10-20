/** Actions auto-discovery via Vite glob import — the FR-R003 client half of the
 *  drop-in registry contract (mirror of the widget contract in lib/widgets).
 *
 *  Any `.ts` file in `src/actions/` exporting
 *    export const meta = {
 *      label: "Flag",                 // button text
 *      scope: "record" | "bulk",      // detail=True vs detail=False @action
 *      model: "orders",               // url segment it applies to; omit = any model
 *      confirm: "…",                  // FE-only dialog; the BE always re-validates
 *      input: "Reason",               // optional text the dialog collects
 *      handler,                       // fires the DRF endpoint
 *    };
 *
 *  …is registered here with no registry to edit. DataTable renders record-scope
 *  buttons per row and bulk-scope buttons over the selection; ModelPage owns
 *  the confirm dialog, the toast and the refresh of the record + audit
 *  sub-view. Handlers return the audit entries the server wrote.
 */
import type { AppConfig, AuditEntry, ModelSpec, RecordRow } from "../types";

export type ActionScope = "record" | "bulk";

export interface ActionContext {
  cfg: AppConfig;
  token: string | null;
  model: ModelSpec;
  /** record scope: exactly one row; bulk scope: the selected rows */
  rows: RecordRow[];
  /** collected from the dialog when `meta.input` is set (e.g. the flag reason) */
  input?: string;
}

export interface ActionMeta {
  label: string;
  scope: ActionScope;
  model?: string;
  confirm?: string;
  input?: string;
  handler: (ctx: ActionContext) => Promise<AuditEntry[]>;
}

export interface RegisteredAction {
  id: string;
  meta: ActionMeta;
}

const actionModules = import.meta.glob<{ meta: ActionMeta }>("../../actions/*.ts", {
  eager: true,
});

/** All discovered actions, keyed by filename (without .ts). */
export const actions: Record<string, RegisteredAction> = Object.fromEntries(
  Object.entries(actionModules).map(([path, mod]) => {
    const id = path.split("/").pop()!.replace(/\.ts$/, "");
    return [id, { id, meta: mod.meta }];
  }),
);

/** Actions of one scope that apply to a model (global ones carry no `model`). */
export function actionsFor(
  modelId: string,
  scope: ActionScope,
  source: Record<string, RegisteredAction> = actions,
): RegisteredAction[] {
  return Object.values(source)
    .filter((a) => a.meta.scope === scope && (!a.meta.model || a.meta.model === modelId))
    .sort((a, b) => a.meta.label.localeCompare(b.meta.label));
}

/** A rejected action is reported by its guard `reason` when the server sent
 *  one (the R-001/R-003 400+{reason} shape), so the UI never shows a bare 400. */
export function actionFailureReason(err: any): string | null {
  const detail = err?.detail;
  if (detail && typeof detail === "object" && typeof detail.reason === "string") return detail.reason;
  if (typeof detail === "string" && detail.trim()) return detail;
  return null;
}
