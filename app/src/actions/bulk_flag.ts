/** Bulk-scope reference action (FR-R003): flag every selected order at once.
 *  Fires POST /api/orders/bulk_flag/ — the server writes one audit entry per
 *  order with bulk provenance {reason, bulk: true, batch: N} in `data`, and
 *  answers 400 + {reason} listing unknown ids without writing anything. */
import { callBulkAction } from "../lib/api";
import type { ActionMeta } from "../lib/actions/index";

export const meta: ActionMeta = {
  label: "Flag batch",
  scope: "bulk",
  model: "orders",
  confirm: "Flag the selected records? The server writes one audit entry per record.",
  input: "Reason",
  // FR-R007 reference gating: batch flagging is a managers-only button.
  // Presentation only — the endpoint stays open to any authenticated
  // caller; a real deployment mirrors the role in server permission.
  roles: ["managers"],
  handler: ({ cfg, token, model, rows, input }) =>
    callBulkAction(cfg, token, model, "bulk_flag", {
      ids: rows.map((row) => row.id),
      reason: input ?? "",
    }),
};
