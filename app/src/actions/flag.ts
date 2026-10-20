/** Record-scope reference action (FR-R003): flag one order for review.
 *  Fires POST /api/orders/<id>/flag/ — changes no order fields, appends one
 *  audit entry server-side (actor derived from the request). */
import { callRecordAction } from "../lib/api";
import type { ActionMeta } from "../lib/actions/index";

export const meta: ActionMeta = {
  label: "Flag",
  scope: "record",
  model: "orders",
  confirm: "Flag this record for review? The reason is written to the append-only audit log.",
  input: "Reason",
  handler: ({ cfg, token, model, rows, input }) =>
    callRecordAction(cfg, token, model, rows[0].id as string | number, "flag", { reason: input ?? "" }),
};
