#!/usr/bin/env python3
"""csv_twin_diff.py — re-run the FR-R005 cross-twin byte diff in one command.

docs/csv-export.md §6 claims the two CSV writers (app/src/lib/csv.ts, layer 1,
and demo-backend/shop/csv_export.py, layer 2) are byte-identical for the same
rows. That claim was proven by hand twice and then lost — the harness lived
only in the segment that wrote it. This script is the harness: it feeds one
generated matrix through BOTH writers as each one actually produces a
download, then compares raw bytes.

Pipeline symmetry is the whole point (the first hand-run got it wrong twice,
see docs/DEVGUIDE.md):
  layer 2 = csv_cell(value) per cell -> csv_text(rows)   (the writer quotes)
  layer 1 = buildCsv(header, rawValues)                   (csvCell = cell+quote)
Comparing csv_cell output to csvCell output reports phantom divergences,
because the guard-then-quote stages are interleaved differently.

Usage (from the repo root):
  python3 scripts/csv_twin_diff.py                 # full battery
  python3 scripts/csv_twin_diff.py --rows 400      # bigger random matrix
  python3 scripts/csv_twin_diff.py --python <exe>  # force the layer-2 interpreter

Layer 2 needs an interpreter that can import the rig's dependencies. The rig
venv (`demo-backend/.venv/bin/python`) is used when it exists, otherwise the
interpreter running this script is PROBED and used — the same no-venv behaviour
scripts/brand_twin_diff.py has always had, and the reason this harness can now
be re-run by the CI landing gate, which pip-installs the plugin into its own
environment and never builds a venv (a venv demanded BY PATH made the whole
FR-R005 live-rig claim read "cannot run" on a dependency-complete box;
measured 2026-10-21). A candidate that fails as-is is probed a second time with
this checkout's `plugin/src` on PYTHONPATH, because an image without setuptools
cannot build that install at all (measured 2026-10-24 on the duty-review lane) —
the note says which of the two carried the import, so a pass always names the
environment that proved it. The chosen interpreter is printed in the verdict, so a
pass always says WHICH python proved it.

Exit 0 = byte-identical; exit 1 = divergence (first differing lines printed);
exit 2 = the rig could not be run (missing node / node_modules / no interpreter
that can import the rig's deps) OR the harness no longer understands its own
matrix (a pinned population that disagrees with the lists it describes) — the
second is never reported as a pass, because both writers read the SAME matrix
and a shrunken matrix therefore cannot make them disagree. See docs/DEVGUIDE.md
ELEVENTH harness law.
"""
import argparse
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
RIG = ROOT / "demo-backend"
PLUGIN_SRC = ROOT / "plugin" / "src"
VENV_PY = RIG / ".venv" / "bin" / "python"

# What SERVER_SPEC actually needs: django.setup() on core.settings plus the
# writer's own imports. Probing exactly this is what lets a non-venv interpreter
# be USED rather than assumed — an interpreter that passes this probe but still
# fails the real run exits 2 with the probe's stderr, never a false verdict.
RIG_DEPS = ("django", "rest_framework", "drf_spectacular", "admincraft")

# Fixed strings chosen to force every guard/quoting branch at once.
SENTINELS = [
    "", " ", "a", "hello, world", 'say "hi"', "line1\nline2", "line1\r\nline2",
    "cr\rhere", "=SUM(A1:A9)", "+cmd", "-cmd", "@SUM(1)", "\ttab-lead",
    "\r cr-lead", "-5.00", "+5", "-.5", "1e-9", "-0", "007", "9" * 30,
    "naïve ✓", "﻿bom", "-" * 1, "+", "=", "@", "\t", "\r", "- ",
    "1,2", '"', "\n", "x\n", "-2+3", '-IF(1=1,cmd,safe)', "=1+1", "1e7",
    "0.1000000000000000055511151231257827", "a" * 300,
    "\x00nul-inside", "\U0001F600 emoji", "中文テキスト",
]


class HarnessError(Exception):
    """The harness does not understand its own inputs: no verdict may be
    reported, which is exit 2, never 0 and never 1."""


FLOATS = [
    0.0, -0.0, 1.0, -1.0, 0.1, 19.99, 1e-5, 1e-6, 1e-7, 9.99e-7, 1e21, 1e22,
    1.7976931348623157e308, 5e-324, 2.5e-13, -1e-9, 1e15, 1e16, 1e17, 1e18,
    123456789012345678.0, 1 / 3, 0.1 + 0.2, 2.0, 100.0, 1e6, -0.00042,
]

# The alphabet for random rows, weighted toward the shapes that break writers.
ALPHABET = SENTINELS + [True, False, None, 0, 1, -1, 2**53, "19.99", "-7.25"]

# ---------------------------------------------------------------------------
# ELEVENTH harness law (docs/DEVGUIDE.md): a printed COUNT is not an EXPECTATION.
# The matrix above is the whole coverage of this check, and both writers read the
# SAME matrix — so a truncated list cannot make them disagree, it only makes them
# agree over less. Measured on this tree before these pins existed: deleting 5
# sentinels answered `BYTE-IDENTICAL — 3065 cells` with rc 0 (the honest run is
# 3070), and the deleted rows included the formula-guard and both line-breaker
# cases, i.e. the cells docs/csv-export.md §2 credits with catching divergence #1
# and #2. A pass must therefore be conditional on the population it was earned
# over, and on BOTH sides having rendered every one of those cells.
# ---------------------------------------------------------------------------

# Pinned twice: a literal here AND len() of the list it describes. Changing the
# matrix deliberately is a two-place edit; shrinking it silently is exit 2.
EXPECTED_SENTINELS = 43
EXPECTED_FLOATS = 27

# Coverage that must never vanish, each with the promise it holds. Matched by
# identity against the lists, never by position or count.
REQUIRED_SENTINELS = {
    "": "an empty cell stays empty, never quoted",
    " ": "a lone space survives quoting",
    "hello, world": "QUOTE_MINIMAL — a comma forces quotes",
    'say "hi"': "an embedded double quote doubles",
    "line1\nline2": "a bare LF inside a quoted cell (divergence #1 class)",
    "line1\r\nline2": "a CRLF inside a quoted cell",
    "cr\rhere": "a lone CR is content, not a terminator",
    "=SUM(A1:A9)": "the formula guard on a text cell",
    "+cmd": "guard lead character +",
    "-cmd": "guard lead character -",
    "@SUM(1)": "guard lead character @",
    "-5.00": "guard is keyed by NUMERIC SHAPE, not by text (a decimal-looking string)",
    "-0": "the same guard decision for a numeric-shaped zero",
    "007": "leading-zero text is not re-flowed",
    "\ttab-lead": "a tab lead is not whitespace-stripped away",
    "\r cr-lead": "a CR lead is not whitespace-stripped away",
    "﻿bom": "a BOM inside data is written once, at the front",
    "naïve ✓": "non-ASCII survives the round trip",
    "\x00nul-inside": "a NUL byte inside a cell",
    "\U0001F600 emoji": "a surrogate-pair-bearing cell",
    "中文テキスト": "CJK content",
    "0.1000000000000000055511151231257827": "a decimal literal is never re-flowed",
    "1e-9": "exponent text stays text",
    "9" * 30: "a long run of digits",
    "a" * 300: "a long run of letters",
}

# A LIST, not a dict: 0.0 and -0.0 are equal in Python, so a dict would collapse
# them into one entry and the negative-zero pin would silently ride on the zero.
# Each is checked by its own IEEE-754 bytes below.
REQUIRED_FLOATS = [
    (0.0, "zero renders 0, not 0.0"),
    (-0.0, 'negative zero is the ECMAScript "0"'),
    (1.0, "the commonest divergence: str(1.0) is 1.0, String(1.0) is 1"),
    (1e-7, "Python pads the exponent (1e-07), JS does not"),
    (1e17, "Python switches to 1e+17 at the 17-digit boundary"),
    (1e21, "above 1e21 both sides use exponent form"),
    (5e-324, "the smallest subnormal"),
    (1.7976931348623157e308, "the largest finite double"),
    (1 / 3, "a 17-significant-digit shortest round trip"),
    (0.1 + 0.2, "0.30000000000000004 — the same rounding on both sides"),
    (-0.00042, "the seed value the demo rig actually carries (seed_demo)"),
    (123456789012345678.0, "an integer-valued double past 2^53"),
]


def check_population(cells: list, rows: int) -> None:
    """Refuse to render a verdict over a matrix this script no longer
    understands. Every failure here is exit 2 — the harness is broken, which is
    not evidence about the two writers either way."""
    if len(SENTINELS) != EXPECTED_SENTINELS or len(FLOATS) != EXPECTED_FLOATS:
        raise HarnessError(
            "the matrix disagrees with itself: %d sentinels in the literal, %d built; "
            "%d floats in the literal, %d built"
            % (EXPECTED_SENTINELS, len(SENTINELS), EXPECTED_FLOATS, len(FLOATS)))
    for value, promise in REQUIRED_SENTINELS.items():
        if value not in SENTINELS:
            raise HarnessError("SENTINEL COVERAGE LOST: %r (%s) is no longer in the matrix"
                               % (value[:24], promise))
    for value, promise in REQUIRED_FLOATS:
        # Keyed by IEEE-754 BYTES, not by `in`: 0.0 == -0.0 in Python, so an
        # equality test cannot tell a matrix that kept both from one that lost
        # negative zero — and "String(-0) is 0, not -0" is exactly why both are here.
        if struct.pack(">d", value) not in {struct.pack(">d", f) for f in FLOATS}:
            raise HarnessError("FLOAT COVERAGE LOST: %r (%s) is no longer in the matrix"
                               % (value, promise))
    # The builder is checked too, not only the lists: a bug in build_matrix
    # would shrink the sample while both lists stayed honest.
    want = len(SENTINELS) + len(FLOATS) + rows
    if len(cells) != want:
        raise HarnessError("MATRIX TRUNCATED: %d cells built against %d expected "
                           "(%d sentinels + %d floats + %d random)"
                           % (len(cells), want, len(SENTINELS), len(FLOATS), rows))
    seen = set(cells)
    for value in SENTINELS + FLOATS:
        text = cell_text(value)
        if text not in seen:
            raise HarnessError("MATRIX NOT RENDERED: %s never reached the matrix file"
                               % text[:40])


def cell_text(v):
    """The matrix is a set of JSON TEXTS, and both sides parse those bytes. One
    renderer for the builder and for the coverage check below, because a check
    that re-implements the builder's spelling drifts and reports its own drift as
    a truncation. `-0.0` is written literally because Python equality says
    0.0 == -0.0 while the two render differently in ECMAScript."""
    if isinstance(v, float) and struct.pack(">d", v) == struct.pack(">d", -0.0):
        return "-0.0"
    return json.dumps(v, ensure_ascii=False)


def build_matrix(rows: int, seed: int) -> list:
    """A column of sentinel values, then `rows` random ones. Values are emitted
    as JSON text so both sides parse the SAME bytes — a float that only exists
    as a Python repr is not something a browser ever saw."""
    rnd = random.Random(seed)
    cells = [cell_text(v) for v in SENTINELS]
    cells += [cell_text(v) for v in FLOATS]
    for _ in range(rows):
        if rnd.random() < 0.4:
            mag = rnd.choice([1e-9, 1e-7, 1.0, 1e6, 1e17, 1e21, 1e100])
            v = mag * rnd.randint(1, 999) / 100
            cells.append(json.dumps(v))
        else:
            v = rnd.choice(ALPHABET)
            cells.append(cell_text(v))
    return cells


CRLF = b"\r\n"

CLIENT_SPEC = """
import { readFileSync, writeFileSync } from "node:fs";
import { it } from "vitest";
import { buildCsv } from "../csv";
const [matrix, out] = process.env.TWIN_PATHS.split(",");
it("twin probe", () => {
  const cells = readFileSync(matrix, "utf8").split("\\n").filter(Boolean);
  const rows = cells.map((l, i) => [i, JSON.parse(l)]);
  writeFileSync(out, buildCsv(["i", "v"], rows));
});
"""

SERVER_SPEC = '''
import json, os, sys
sys.path.insert(0, os.getcwd())   # core.settings lives at the rig root
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
os.environ.setdefault("DEMO_DEV", "1")
import django
django.setup()
from shop.csv_export import csv_cell, csv_text
matrix, out = sys.argv[1], sys.argv[2]
cells = [l for l in open(matrix, encoding="utf-8").read().split("\\n") if l]
rows = [[i, csv_cell(json.loads(c))] for i, c in enumerate(cells)]
open(out, "w", encoding="utf-8", newline="").write(csv_text([["i", "v"]] + rows))
'''


def run(cmd, cwd=None, **env):
    """Run a probe. A tool that is NOT THERE (no node on PATH) must not read as
    a divergence: exit 1 is reserved for "the two writers disagree", so a launch
    failure becomes a synthetic 127 result and the callers report exit 2.
    Without this, `PATH=/nonexistent python3 scripts/csv_twin_diff.py` died with
    a FileNotFoundError traceback and exit 1 — a false DIVERGENT from a rig that
    never ran (measured 2026-10-21)."""
    e = {**os.environ, **env}
    try:
        return subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", f"cannot launch {cmd[0]!r}: {exc}\n")


def resolve_server_python(explicit):
    """Pick the interpreter that runs layer 2. Returns (exe, note, env) or
    (None, why, None) — never a guess, never a silent skip.

    `--python` is honoured exclusively: if a seat names an interpreter, a
    failure there is the answer, not a licence to fall back to another one and
    report a pass from a different environment than was asked about.

    Each candidate is probed twice — as it is, then with this checkout's
    `plugin/src` on PYTHONPATH — because an image without setuptools cannot
    build the editable install the CI boot script swallows, and the plugin is
    pure python: a lane that has django but no install can still run the real
    writer, and the note says which of the two carried the import.
    """
    if explicit:
        candidates = [explicit]
    else:
        candidates = [str(c) for c in (VENV_PY, Path(sys.executable)) if Path(c).exists()]
    if not candidates:
        return None, ("no interpreter can run layer 2 — build the rig venv "
                      f"(see AGENTS.md Commands) or pass --python <exe> with one that "
                      f"imports {', '.join(RIG_DEPS)}"), None
    source_env = {"PYTHONPATH": os.pathsep.join(
        [str(PLUGIN_SRC)] + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p])}
    tried = []
    for exe in candidates:
        for probe_env, note in ((None, "probed OK"),
                                (source_env, "probed OK — plugin from plugin/src, "
                                             "no editable install")):
            probe = run([exe, "-c", "import " + ", ".join(RIG_DEPS)], cwd=str(RIG),
                        **(probe_env or {}))
            if probe.returncode == 0:
                return exe, note, probe_env
        lines = (probe.stderr or probe.stdout or "").strip().splitlines()
        tried.append(f"{exe} -> {lines[-1] if lines else 'no output'}")
    return None, ("no candidate interpreter can import the rig's deps — tried: "
                  + "; ".join(tried) + f". Need {', '.join(RIG_DEPS)}."), None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rows", type=int, default=3000, help="random cells (default 3000)")
    ap.add_argument("--seed", type=int, default=20261021)
    ap.add_argument("--keep", action="store_true", help="keep the work dir for inspection")
    ap.add_argument("--python", default=None, metavar="EXE",
                    help="interpreter for layer 2 (default: the rig venv, else this one, if it imports the rig's deps)")
    args = ap.parse_args()

    if not shutil.which("node") and not (APP / "node_modules").exists():
        print("node is required (the client side runs the real csv.ts under vitest)", file=sys.stderr)
        return 2
    if not (APP / "node_modules").exists():
        print(f"app/node_modules missing — run `cd app && npm install` first", file=sys.stderr)
        return 2
    server_py, note, server_env = resolve_server_python(args.python)
    if server_py is None:
        print(note, file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="csv-twin-"))
    try:
        matrix = work / "matrix.txt"
        cells = build_matrix(args.rows, args.seed)
        check_population(cells, args.rows)
        matrix.write_text("\n".join(cells) + "\n", encoding="utf-8")
        client_doc, server_doc = work / "client.csv", work / "server.csv"

        # vitest's include is `src/**/*.test.ts`, so the probe spec has to live
        # inside app/src — it is written per run and removed in the same breath.
        spec = APP / "src" / "lib" / "__tests__" / "zzTwinProbe.tmp.test.ts"
        spec.write_text(CLIENT_SPEC, encoding="utf-8")
        p = run(
            ["npx", "vitest", "run", "src/lib/__tests__/zzTwinProbe.tmp.test.ts", "--maxWorkers=1"],
            cwd=str(APP),
            TWIN_PATHS=f"{matrix},{client_doc}",
            NODE_OPTIONS="--max-old-space-size=1024",
        )
        spec.unlink(missing_ok=True)
        if p.returncode != 0 or not client_doc.exists():
            print("client probe failed:\n" + p.stdout[-2000:] + p.stderr[-2000:], file=sys.stderr)
            return 2

        spec_py = work / "server_probe.py"
        spec_py.write_text(SERVER_SPEC, encoding="utf-8")
        p = run([server_py, str(spec_py), str(matrix), str(server_doc)], cwd=str(RIG),
                **(server_env or {}))
        if p.returncode != 0:
            print("server probe failed:\n" + p.stdout[-2000:] + p.stderr[-2000:], file=sys.stderr)
            return 2

        a = client_doc.read_bytes()
        b = server_doc.read_bytes()
        n = len(matrix.read_text(encoding="utf-8").splitlines())
        print(f"  layer 2 interpreter: {server_py} ({note})")
        # Coverage of the COMPARE, not only of the matrix. A line COUNT cannot pin
        # it (quoted cells carry CRLF: the honest run is 3070 cells over 3097 lines),
        # so the check is identity instead: column 0 is the row index the probe was
        # given, so the last cell of the matrix must appear as its own line. A
        # document that stopped short says so. Both sides agree by the byte compare
        # below, so one check covers both.
        if CRLF + f"{n - 1},".encode() not in a + CRLF:
            raise HarnessError(
                "the compared document never reaches matrix row %d — the compare ran over "
                "a truncated write, so it has no verdict about the writers" % (n - 1))
        if a == b:
            print(f"BYTE-IDENTICAL — {n} cells, {len(a)} bytes, seed={args.seed}")
            print(f"  {a.count(CRLF)} CRLF-terminated lines on both sides")
            return 0
        print(f"DIVERGENT — {n} cells, client {len(a)} B vs server {len(b)} B")
        # Read in BINARY on purpose: text mode translates \r\n to \n and turns a
        # clean diff into a fake one (docs/DEVGUIDE.md, FIFTH twin-diff law).
        la, lb = a.split(b"\r\n"), b.split(b"\r\n")
        shown = 0
        for i, (x, y) in enumerate(zip(la, lb)):
            if x != y:
                print(f"  line {i}: client={x[:120]!r} server={y[:120]!r}")
                shown += 1
                if shown >= 20:
                    break
        print(f"  work dir kept: {work}")
        return 1
    finally:
        if args.keep:
            print(f"(--keep) work dir: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HarnessError as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        sys.exit(2)
