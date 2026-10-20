/** csv.ts — the canonical CSV writer (FR-R005, layer 1: visible columns).

Two rules decide everything here:

1. The file is DATA, not a screenshot of the table. `formatCell` truncates at
   60 chars, renders nulls as "—" and booleans as Yes/No — right for a cell,
   wrong for an export, so the export path never calls it. Values reach the
   file as the API sent them: a decimal stays the string "19.99" (never
   re-flowed through Number -> 19.990000000000002), a datetime keeps its full
   ISO form, a long note keeps every character.
2. RFC 4180 quoting, CRLF line endings, and the SAME rule as the server's
   `csv.writer(..., lineterminator="\r\n")` (Python QUOTE_MINIMAL): quote when
   the field contains a comma, a double quote, CR or LF; embedded quotes double.
   Leading/trailing whitespace is deliberately NOT quoted — that is what makes
   layer 1 (this file) and layer 2 (the `export/` endpoint, docs/csv-export.md)
   byte-identical for the same rows, so two clients of one API can diff a
   download instead of guessing which one lied. (One carve-out Python has and
   this file does not: it quotes a row that is exactly one empty field so the
   line cannot collapse. No real export row is single-column.)

Formula injection is mitigated (OWASP CSV section): a *string* that starts with
= + - @ TAB or CR gets a leading apostrophe, because Excel and Sheets evaluate
such a cell rather than displaying it — `-cmd` in a notes field is a data
exfiltration vector, not a spreadsheet quirk. Real numbers (`typeof "number"`)
are left alone; a negative price is not a formula.
*/
import type { FieldSpec, RecordRow } from "./types";

/** A cell the writer accepts — anything JSON-decodable off a DRF response. */
export type CsvCell = string | number | boolean | null | undefined;

const FORMULA_LEAD = ["=", "+", "-", "@", "\t", "\r"];

function needsQuotes(s: string): boolean {
  return /[",\n\r]/.test(s);
}

/** One cell to its CSV text (already quoted/escaped, no trailing delimiter). */
export function csvCell(value: CsvCell): string {
  if (value === null || value === undefined) return "";
  let s: string;
  if (typeof value === "boolean") s = value ? "true" : "false";
  else if (typeof value === "number") s = String(value); else s = String(value);

  if (typeof value === "string" && FORMULA_LEAD.includes(s[0] as string)) s = `'${s}`;
  return needsQuotes(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** rows as matrix -> RFC 4180 document (CRLF-terminated, final newline included:
 *  Python's csv.writer ends every row with the line terminator, and the two
 *  layers must diff clean). */
export function buildCsv(header: string[], rows: CsvCell[][]): string {
  const lines = [header, ...rows].map((cells) => cells.map(csvCell).join(","));
  return `${lines.join("\r\n")}\r\n`;
}

/** The columns an export carries for a model: every non-JSON field the table
 *  shows, in table order (DataTable's own slice — the export must match what
 *  the user is looking at, so the two read the same derived list). */
export function exportColumns(model: { fields: FieldSpec[] }, limit = 6): FieldSpec[] {
  return model.fields.filter((f) => f.type !== "json").slice(0, limit);
}

/** Visible columns + loaded rows -> CSV. Header is the field names (machine
 *  readable, so a round trip back into the API cannot invent new columns). */
export function tableToCsv(columns: FieldSpec[], rows: RecordRow[]): string {
  const header = columns.map((c) => c.name);
  return buildCsv(
    header,
    rows.map((row) => columns.map((c) => row[c.name] as CsvCell)),
  );
}

/** `Order` + `paid` -> `orders-paid.csv`: lowercase, non-alnum collapsed to a
 *  single dash, no path separators (the name comes from schema data, and a
 *  model named "../../etc/x" must not steer a save path). An existing .csv
 *  suffix is dropped and re-added, so a server-supplied name stays identical
 *  instead of doubling into `orders.csv.csv`. */
export function exportFileName(label: string, suffix = ""): string {
  const slug = slugify(String(label ?? "").replace(/\.csv$/i, ""));
  const tail = slugify(String(suffix ?? ""));
  return `${slug || "export"}${tail ? `-${tail}` : ""}.csv`;
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

const BOM = "\ufeff";

/** Excel on Windows reads a BOM-less UTF-8 file as the local codepage and
 *  mangles every non-ASCII name, so the BOM ships with the document. */
export function csvBlobParts(csv: string): BlobPart[] {
  return [BOM + csv];
}

/** Trigger a browser download. Returns false when there is no DOM to download
 *  through (SSR/tests) — the caller then says so instead of failing silently. */
export function downloadCsv(filename: string, csv: string): boolean {
  if (typeof document === "undefined" || typeof Blob === "undefined") return false;
  const url = URL.createObjectURL(new Blob(csvBlobParts(csv), { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // WebKit needs the click to settle before the object URL dies.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}
