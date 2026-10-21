#!/usr/bin/env python3
"""parity_table_diff.py — re-run the FR-R005 SHARED-TABLE claim in one command.

docs/csv-export.md §6 and AGENTS.md assert that two artifacts of the CSV twin
proof are literally the SAME on both sides of the language boundary:

  1. FLOAT_PARITY — the float table in plugin/tests/test_csv_export.py
     (`csv_cell`) and app/src/lib/__tests__/csv.test.ts (`csvCell`).
  2. the golden document — one byte string, asserted twice, produced by
     `csv_text([header] + [[csv_cell(v) …]])` on one side and
     `buildCsv(header, rows)` on the other.

Both claims were prose. Each side's suite is green against ITS OWN copy of the
table, so a seat that edits one copy (adds a value, retypes an expectation,
re-wraps a golden literal) keeps 299 pytest + 416 vitest green while the "shared"
adjective silently dies — and the twin proof then quietly stops covering the case
the table was written for. This script parses both files (no imports, no Django,
no node_modules) and diffs the artifacts themselves.

Two rules from docs/DEVGUIDE.md decide the design, so read them before changing it:

  * NORMALIZE ONLY WHAT IS DOCUMENTED TO DIFFER (SIXTH law). The golden ROWS may
    legitimately differ in spelling — the server receives `Decimal("19.99")` and
    an aware `datetime`, the browser receives the text/JSON number DRF actually
    sent (both docstrings say so). The comparable artifact is the asserted BYTE
    STRING, which is what both writers must produce. That is what this compares.
  * A cross-language float must be keyed by VALUE IDENTITY, not by either
    language's rendering — because the rendering is the thing under test. So each
    float becomes its IEEE-754 big-endian bytes (`struct.pack(">d")` on the Python
    side, `Float64Array`/`Uint32Array` on the JS side). `str(1e17)` and
    `String(1e17)` disagree by design; the 8 bytes behind them do not.

The JS expressions are evaluated by node itself, so no ECMAScript semantics are
re-implemented here.

Usage (from the repo root):
  python3 scripts/parity_table_diff.py

Exit 0 = both tables identical; exit 1 = divergence (the one-sided rows / the
first differing bytes are printed); exit 2 = the check could not be RUN (a file
or a subject is missing, node absent, an expression failed to evaluate). A
harness that silently greys out when it cannot find its subject is a false
green, so every "not there" case is exit 2, never 0 — and a launch failure is
exit 2, never 1 (that trap is what cost csv_twin_diff.py its exit-code contract).
"""
import argparse
import ast
import base64
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_TABLE = ROOT / "plugin" / "tests" / "test_csv_export.py"
TS_TABLE = ROOT / "app" / "src" / "lib" / "__tests__" / "csv.test.ts"


# --------------------------------------------------------------------------
# python side — parsed with `ast`, never imported (importing pulls in Django)
# --------------------------------------------------------------------------

def const_num(node, where):
    """Number expressions in these tables are literals, +/- and the odd
    `1 / 3` / `0.1 + 0.2`. Anything richer means the table changed shape and the
    harness must stop rather than guess."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = const_num(node.operand, where)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a = const_num(node.left, where)
        b = const_num(node.right, where)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / b
    raise ValueError(f"{where}: unsupported numeric expression {ast.dump(node)}")


def py_float_table(src, path):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "FLOAT_PARITY" for t in node.targets):
            rows = []
            for item in node.value.elts:
                if not isinstance(item, ast.Tuple) or len(item.elts) != 2:
                    raise ValueError(f"{path}:{node.lineno}: row is not a 2-tuple")
                expected = item.elts[1]
                if not (isinstance(expected, ast.Constant)
                        and isinstance(expected.value, str)):
                    raise ValueError(f"{path}:{item.lineno}: expectation is not a plain string")
                rows.append((struct.pack(">d", const_num(item.elts[0], path)).hex(),
                             expected.value))
            return rows
    raise LookupError(f"{path}: no FLOAT_PARITY assignment")


def py_golden_doc(src, path):
    """The ONE assert that writes a whole document cell-by-cell.

    `csv_text(` alone is not the golden: the small unit asserts (line 145 onward,
    `csv_text([['id','name'],[1,'a']]) == "id,name\\r\\n…"`) match it too, and
    taking the first would silently compare a 19-byte toy against the real
    226-byte golden and report DIVERGENT. The golden is the only assert built with
    `csv_cell(` per value, so that is the discriminator — and exactly one match is
    required, because an ambiguous subject is a harness that stops working the
    moment somebody refactors.
    """
    tree = ast.parse(src)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        cmp_ = node.test
        if len(cmp_.comparators) != 1:
            continue
        lhs = ast.unparse(cmp_.left)
        if "csv_text(" not in lhs or "csv_cell(" not in lhs:
            continue
        rhs = cmp_.comparators[0]
        if not (isinstance(rhs, ast.Constant) and isinstance(rhs.value, str)):
            # The writer call IS there but its expected bytes are not one merged
            # literal (a join, a variable, a comprehension) — the harness cannot
            # read the claim, which is exit 2, not a divergence and not a grey.
            raise LookupError(
                f"{path}:{rhs.lineno}: golden document is not a plain string literal "
                f"(lhs was: {lhs[:120]})")
        hits.append((node.lineno, rhs.value))
    if not hits:
        raise LookupError(f"{path}: no `assert csv_text([header] + [[csv_cell(…) …]]) == \"…\"`")
    if len(hits) > 1:
        raise LookupError(f"{path}: {len(hits)} golden-document asserts "
                          f"(lines {[h[0] for h in hits]}) — the subject is ambiguous")
    return hits[0][1]


# --------------------------------------------------------------------------
# JS side — substring scan, then node evaluates the real expressions
# --------------------------------------------------------------------------

def js_matching(src, start, opener, closer):
    """Index just past the bracket matching src[start], skipping strings,
    template literals and comments. Needed because the golden literal CONTAINS
    `)` and `]` characters (`'=HYPERLINK(…'`), so a naive count closes early and
    would hand node a truncated expression."""
    depth, i, n = 0, start, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            quote = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    break
                i += 1
            if i >= n:
                raise ValueError("unterminated string literal")
        elif src[i:i + 2] == "//":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        elif src[i:i + 2] == "/*":
            j = src.find("*/", i + 2)
            if j < 0:
                raise ValueError("unterminated block comment")
            i = j + 2
            continue
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError(f"no matching {closer!r} after offset {start}")


def js_span(src, anchor, path):
    """The INNER text of the bracketed expression that follows `anchor` (anchor
    ends ON the opener). Trailing commas are stripped: `toBe( "a" + "b", )` is
    legal call-argument syntax but re-wrapping those parens as a parenthesized
    expression is not — `( "a" + "b", )` is a SyntaxError. Measured: the shipped
    golden literal carries exactly that trailing comma, and the first run of this
    script tripped it (node probe failure, reported as exit 2, not as a fake
    divergence)."""
    pos = src.find(anchor)
    if pos < 0:
        raise LookupError(f"{path}: anchor {anchor!r} not found")
    if src.count(anchor) > 1:
        raise LookupError(f"{path}: anchor {anchor!r} found {src.count(anchor)} times "
                          f"— the subject is ambiguous")
    opener = anchor[-1]
    start = pos + len(anchor) - 1
    span = src[start:js_matching(src, start, opener, {"[": "]", "(": ")"}[opener])]
    inner = span[1:-1] if opener == "(" else span
    while True:
        inner = inner.rstrip()
        if not inner.endswith(","):
            return inner
        inner = inner[:-1]


def js_float_table(src, path):
    # Exact identifier, then the `=`: the type annotation `[number, string][]`
    # also contains `[`, and a bare substring search would happily match a
    # `FLOAT_PARITY_SOMETHING_ELSE` declaration (measured: renaming the shipped
    # table still read green, because the prefix hit pulled the renamed array —
    # the wrong-subject class the exit-2 law exists to make loud).
    m = re.search(r"\bconst\s+FLOAT_PARITY\s*(?::[^=\n]*)?=", src)
    if not m:
        raise LookupError(f"{path}: no `const FLOAT_PARITY … =` declaration")
    start = src.find("[", m.end())
    if start < 0:
        raise LookupError(f"{path}: FLOAT_PARITY assignment has no array literal")
    return src[start:js_matching(src, start, "[", "]")]


NODE_PROBE = """
const src = Buffer.from(process.argv[2], "base64").toString("utf8");
const fns = new Function(src + "; return { T: FLOAT_PARITY, D: GOLDEN };");
const { T, D } = fns();
const bits = (v) => {
  if (typeof v !== "number" || !Number.isFinite(v)) throw new Error("row value is not a finite number: " + v);
  const f = new Float64Array([v]);
  const u = new Uint32Array(f.buffer);
  // little-endian word order: high word first for a big-endian hex key
  return ((u[1] >>> 0).toString(16).padStart(8, "0") + (u[0] >>> 0).toString(16).padStart(8, "0"));
};
if (typeof D !== "string") throw new Error("golden document is not a string");
const table = T.map((row, i) => {
  if (!Array.isArray(row) || row.length !== 2) throw new Error("row " + i + " is not a 2-entry array");
  if (typeof row[1] !== "string") throw new Error("row " + i + " expectation is not a string");
  return [bits(row[0]), row[1]];
});
process.stdout.write(JSON.stringify({ table, doc: Buffer.from(D, "utf8").toString("hex") }));
"""


def run(cmd, cwd=None):
    """A missing tool must never read as a divergence: exit 1 is reserved for
    "the two copies disagree", so a launch failure returns a synthetic 127 and
    the caller reports exit 2 (same trap csv_twin_diff.py had)."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 127, "", f"cannot run {cmd[0]!r}: {exc}\n")


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------

def diff_table(name, py_rows, js_rows):
    if py_rows == js_rows:
        print(f"  {name}: {len(py_rows)} rows, identical values AND expectations")
        return True
    print(f"  {name}: DIVERGENT — python {len(py_rows)} rows vs js {len(js_rows)} rows")
    pset, jset = set(py_rows), set(js_rows)
    for row in py_rows:
        if row not in jset:
            print(f"    python-only: value(IEEE-754 BE)={row[0]} expected={row[1]!r}")
    for row in js_rows:
        if row not in pset:
            print(f"    js-only:     value(IEEE-754 BE)={row[0]} expected={row[1]!r}")
    for i, (p, j) in enumerate(zip(py_rows, js_rows)):
        if p != j and p in jset and j in pset and len(py_rows) == len(js_rows) and pset == jset:
            print(f"    order differs at row {i}: python={p} js={j}")
            break
    return False


def diff_doc(py_doc, js_doc):
    a, b = py_doc.encode("utf-8"), js_doc.encode("utf-8")
    crlf = a.count(b"\r\n")
    if a == b:
        print(f"  golden document: {len(a)} B, {crlf} CRLF lines, identical bytes")
        return True
    print(f"  golden document: DIVERGENT — python {len(a)} B vs js {len(b)} B")
    la, lb = a.split(b"\r\n"), b.split(b"\r\n")   # binary split: text mode eats the CRLF
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            print(f"    line {i}: python={x!r}\n             js     ={y!r}")
            break
    else:
        print(f"    one side has {len(la) - len(lb):+d} extra line(s)")
    return False


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    for p in (PY_TABLE, TS_TABLE):
        if not p.exists():
            print(f"cannot run: {p} is missing", file=sys.stderr)
            return 2
    if not shutil.which("node"):
        print("cannot run: node is not on PATH (the JS expressions are evaluated by node)",
              file=sys.stderr)
        return 2
    try:
        py_src = PY_TABLE.read_text(encoding="utf-8")
        ts_src = TS_TABLE.read_text(encoding="utf-8")
        py_rows = py_float_table(py_src, PY_TABLE)
        py_doc = py_golden_doc(py_src, PY_TABLE)
        js_table_expr = js_float_table(ts_src, TS_TABLE)
        js_doc_expr = js_span(ts_src, "buildCsv(header, rows)).toBe(", TS_TABLE)
    except (ValueError, LookupError) as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="parity-table-"))
    try:
        probe = work / "probe.js"
        probe.write_text(NODE_PROBE, encoding="utf-8")
        exprs = f"const FLOAT_PARITY = {js_table_expr};\nconst GOLDEN = {js_doc_expr};\n"
        p = run(["node", str(probe), base64.b64encode(exprs.encode("utf-8")).decode()])
        if p.returncode != 0:
            print(f"cannot run: node probe failed:\n{p.stdout}{p.stderr}", file=sys.stderr)
            return 2
        try:
            got = json.loads(p.stdout)
            js_rows = [(k, v) for k, v in got["table"]]
            js_doc = bytes.fromhex(got["doc"]).decode("utf-8")
        except (ValueError, KeyError, UnicodeDecodeError) as exc:
            print(f"cannot run: unparsable probe output: {exc}\n{p.stdout[:500]}", file=sys.stderr)
            return 2

        print(f"{PY_TABLE.relative_to(ROOT)} <-> {TS_TABLE.relative_to(ROOT)}")
        ok_table = diff_table("FLOAT_PARITY", py_rows, js_rows)
        ok_doc = diff_doc(py_doc, js_doc)
        if ok_table and ok_doc:
            print("BYTE-IDENTICAL — the two suites really do share one table and one document")
            return 0
        print("The claim is prose again: one copy drifted from the other.")
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — a crash is NOT a divergence
        # Measured on the first run of this script: an uncaught AttributeError in
        # the extractor died with a traceback and rc 1, the documented code for
        # "the two copies disagree". Any internal failure is "could not be run".
        print(f"cannot run: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
