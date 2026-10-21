/** DataTable cell-display wire proof. DataTable.test.ts stubs the whole
 *  ../lib/utils module (its vi.mock replaced formatCell with String(v ?? "")
 *  and was never even exercised — those tests judge each-keys in plain code),
 *  so until now NO test rendered a cell through the real formatter. A stub
 *  cannot fail when the shipped rules drift (chat 16:11Z: a disconnected
 *  builder plus a stripped legend stayed green), so this mounts the actual
 *  component and asserts the DOM: the em dash, the FK "#", the enum pill, the
 *  60-char ellipsis, the never-re-flowed decimal, and the json column that
 *  must not appear at all. */
import { afterEach, describe, expect, it } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import DataTable from "../../components/DataTable.svelte";
import { formatCell } from "../utils";
import type { FieldSpec, ModelSpec, RecordRow } from "../types";

const mounted: Array<Record<string, any>> = [];

afterEach(() => {
  while (mounted.length) unmount(mounted.pop()!);
  document.body.innerHTML = "";
});

const f = (name: string, type: string, extra: Partial<FieldSpec> = {}): FieldSpec =>
  ({ name, type: type as FieldSpec["type"], required: false, readOnly: false, ...extra });

const MODEL: ModelSpec = {
  id: "orders",
  name: "Order",
  singular: "order",
  listPath: "/api/orders/",
  detailPath: "/api/orders/{id}/",
  labelField: "notes",
  fields: [
    f("id", "number", { readOnly: true }),
    f("status", "enum", { choices: ["pending", "paid"] }),
    f("meta", "json"), // mid-list on purpose: a dropped filter cannot hide
    // behind the 6-column slice if json sits LAST — it must be refused by the
    // filter itself, and the seven-field row below proves the slice still cut.
    f("total", "decimal", { format: "decimal" }),
    f("created_at", "datetime", { readOnly: true }),
    f("customer", "fk", { fkModel: "customers" }),
    f("notes", "text"),
  ],
  byName: {},
};

const LONG = "n".repeat(80);
const ROW: RecordRow = {
  id: 7,
  status: "paid",
  total: "19.9900",
  created_at: "2026-10-21T08:30:00.123456Z",
  customer: 42,
  notes: LONG,
};

function render(rows: RecordRow[]): HTMLElement {
  const host = document.createElement("div");
  document.body.appendChild(host);
  mounted.push(
    mount(DataTable, {
      target: host,
      props: { model: MODEL, rows, onedit: () => {}, ondelete: () => {} },
    }),
  );
  flushSync();
  return host;
}

describe("DataTable renders cells through the REAL formatCell", () => {
  it("shows the trimmed datetime, the intact decimal and the ellipsis", () => {
    const text = render([ROW]).textContent ?? "";
    expect(text).toContain("2026-10-21 08:30"); // trimmed, seconds+Z gone
    expect(text).not.toContain("08:30:00");
    expect(text).toContain("19.9900"); // never re-flowed to 19.99
    expect(text).toContain("n".repeat(57) + "…");
    expect(text).not.toContain(LONG);
  });

  it("marks the FK cell with its # and the enum cell as a pill", () => {
    const host = render([ROW]);
    expect(host.textContent).toContain("#42");
    const pill = Array.from(host.querySelectorAll("span")).find((el) => el.textContent?.trim() === "paid");
    expect(pill?.className).toContain("rounded-full");
  });

  it("draws the em dash for an absent value, not the stub's empty string", () => {
    const row: RecordRow = { ...ROW, notes: null };
    expect(render([row]).textContent).toContain("—");
  });

  it("the json field is filtered out of the visible columns", () => {
    const headers = Array.from(render([ROW]).querySelectorAll("th")).map((th) => th.textContent?.trim());
    // Exact set, not just an absence: json sits mid-list in MODEL.fields, so
    // deleting the filter would surface "meta" AND push "notes" past the
    // six-column slice — both fail here, not silently re-shuffle.
    expect(headers).toEqual(["id", "status", "total", "created at", "customer", "notes", "Actions"]);
  });

  it("what the DOM shows is exactly what formatCell returns — stub and real cannot diverge here", () => {
    const text = render([ROW]).textContent ?? "";
    for (const value of [ROW.total, ROW.created_at, ROW.notes] as const) {
      expect(text).toContain(formatCell(value));
    }
  });
});
