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
measured 2026-10-21). The chosen interpreter is printed in the verdict, so a
pass always says WHICH python proved it.

Exit 0 = byte-identical; exit 1 = divergence (first differing lines printed);
exit 2 = the rig could not be run (missing node / node_modules / no interpreter
that can import the rig's deps).
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
RIG = ROOT / "demo-backend"
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

FLOATS = [
    0.0, -0.0, 1.0, -1.0, 0.1, 19.99, 1e-5, 1e-6, 1e-7, 9.99e-7, 1e21, 1e22,
    1.7976931348623157e308, 5e-324, 2.5e-13, -1e-9, 1e15, 1e16, 1e17, 1e18,
    123456789012345678.0, 1 / 3, 0.1 + 0.2, 2.0, 100.0, 1e6, -0.00042,
]

# The alphabet for random rows, weighted toward the shapes that break writers.
ALPHABET = SENTINELS + [True, False, None, 0, 1, -1, 2**53, "19.99", "-7.25"]


def build_matrix(rows: int, seed: int) -> list:
    """A column of sentinel values, then `rows` random ones. Values are emitted
    as JSON text so both sides parse the SAME bytes — a float that only exists
    as a Python repr is not something a browser ever saw."""
    rnd = random.Random(seed)
    cells = [json.dumps(v, ensure_ascii=False) for v in SENTINELS]
    cells += [json.dumps(v) if v != -0.0 else "-0.0" for v in FLOATS]
    for _ in range(rows):
        if rnd.random() < 0.4:
            mag = rnd.choice([1e-9, 1e-7, 1.0, 1e6, 1e17, 1e21, 1e100])
            v = mag * rnd.randint(1, 999) / 100
            cells.append(json.dumps(v))
        else:
            v = rnd.choice(ALPHABET)
            cells.append(json.dumps(v, ensure_ascii=False))
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


def resolve_server_python(explicit: str | None):
    """Pick the interpreter that runs layer 2. Returns (exe, note) or
    (None, why) — never a guess, never a silent skip.

    `--python` is honoured exclusively: if a seat names an interpreter, a
    failure there is the answer, not a licence to fall back to another one and
    report a pass from a different environment than was asked about.
    """
    if explicit:
        candidates = [explicit]
    else:
        candidates = [str(c) for c in (VENV_PY, Path(sys.executable)) if Path(c).exists()]
    if not candidates:
        return None, ("no interpreter can run layer 2 — build the rig venv "
                      f"(see AGENTS.md Commands) or pass --python <exe> with one that "
                      f"imports {', '.join(RIG_DEPS)}")
    tried = []
    for exe in candidates:
        probe = run([exe, "-c", "import " + ", ".join(RIG_DEPS)], cwd=str(RIG))
        if probe.returncode == 0:
            return exe, "probed OK"
        lines = (probe.stderr or probe.stdout or "").strip().splitlines()
        tried.append(f"{exe} -> {lines[-1] if lines else 'no output'}")
    return None, ("no candidate interpreter can import the rig's deps — tried: "
                  + "; ".join(tried) + f". Need {', '.join(RIG_DEPS)}.")


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
    server_py, why = resolve_server_python(args.python)
    if server_py is None:
        print(why, file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="csv-twin-"))
    try:
        matrix = work / "matrix.txt"
        matrix.write_text("\n".join(build_matrix(args.rows, args.seed)) + "\n", encoding="utf-8")
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
        p = run([server_py, str(spec_py), str(matrix), str(server_doc)], cwd=str(RIG))
        if p.returncode != 0:
            print("server probe failed:\n" + p.stdout[-2000:] + p.stderr[-2000:], file=sys.stderr)
            return 2

        a = client_doc.read_bytes()
        b = server_doc.read_bytes()
        n = len(matrix.read_text(encoding="utf-8").splitlines())
        print(f"  layer 2 interpreter: {server_py}")
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
    sys.exit(main())
