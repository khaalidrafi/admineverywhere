#!/usr/bin/env python3
"""brand_twin_diff.py — re-run the runtime/build-time brand CSS twin byte diff in one command.

AGENTS.md promises "brandToCss() mirrors branding.render_css() output — keep
them in sync" and that applyBrand() injects "a <style> with the same --brand-*
variables". Both were prose, checked by hand and never committed — the same
expiry disease the CSV twins had (scripts/csv_twin_diff.py, docs/DEVGUIDE.md).

Two writers, one contract, and the artifact that bridges them, so five checks:
  1. POPULATION: the matrix is what this script says it is. A sentinel list that
     loses rows shrinks the coverage and used to still print BYTE-IDENTICAL
     (measured: cutting 7 legal fonts left the harness green over a matrix that no
     longer contained the double-space case docs/DEVGUIDE.md records as a past
     divergence). So the sentinel count is pinned by a literal AND by the lists,
     and the two must agree — a silent truncation is impossible, a deliberate one
     is a two-place edit.
  2. DOMAIN: every brand the closed schema must refuse is refused, and every legal
     one is accepted, each pinned by identity. Refusing to trust a printed count:
     loosening the radius rule made 3 illegal radii legal and the twins still
     agreed, so the harness said BYTE-IDENTICAL over a softened schema.
  3. TWINS: for every brand the SERVER accepts (validate_brand == []), the
     build-time writer render_css() and the runtime writer brandToCss() must
     produce the same declarations, byte for byte.
  4. BUNDLE: the shipped app/public/brand.css must equal render_css of the
     brand.json sitting beside it — that pair is first paint.
  5. HANDOFF: brandToCss of that same brand.json must equal the bundle, because
     applyBrand() re-injects it at boot. bundle != runtime means a visible
     re-theme flicker, the exact thing the static bundle exists to prevent. The
     shipped brand is found BY IDENTITY in the accepted set, never by position:
     it used to be `runtime_css[-1]`, which silently grabbed a neighbour when the
     shipped brand was refused and reported "HANDOFF DIVERGENCE — a visible
     re-theme flicker" about a pair of brands that were never the same brand.

Normalization, and why it is honest: the two carry DIFFERENT banner comments on
purpose (a generated file says "do not edit", a runtime <style> says
"injected"), so the compared region runs from the first "@import" to the end,
trailing whitespace stripped. Everything under that marker is the promise; both
headers are printed rather than hidden.

Usage (from the repo root):
  python3 scripts/brand_twin_diff.py                  # full battery
  python3 scripts/brand_twin_diff.py --brands 400     # bigger random matrix
  python3 scripts/brand_twin_diff.py --show           # print the accepted CSS

Exit 0 = byte-identical over the full pinned population; exit 1 = divergence, or a
refusal expectation broken (the closed schema softened / a legal brand refused);
exit 2 = the rig could not be run (missing node / app/node_modules / plugin) or the
matrix disagrees with its own literal, in which case there is no verdict to report.
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
PLUGIN_SRC = ROOT / "plugin" / "src"
PUBLIC_CSS = APP / "public" / "brand.css"
PUBLIC_JSON = APP / "public" / "brand.json"
PAYLOAD_MARKER = "@import"

# The client side runs the REAL module under vitest: node here (v20) cannot load
# a .ts, and a transpiled copy would not be the code the browser executes. The
# probe spec must live inside app/src because that is vitest's include root; it
# is written per run and unlinked in the same breath, so no suite pollution.
CLIENT_SPEC = """
import { readFileSync, writeFileSync } from "node:fs";
import { it } from "vitest";
import { brandToCss } from "../branding";
const [brands, out] = process.env.TWIN_PATHS.split(",");
it("brand twin probe", () => {
  const list = JSON.parse(readFileSync(brands, "utf8"));
  writeFileSync(out, JSON.stringify(list.map((b) => brandToCss(b))));
});
"""


def load_server_writer():
    """render_css/validate_brand — installed package first, source tree
    otherwise, so this runs with a bare `python3` and no venv."""
    try:
        from admincraft.branding import render_css, validate_brand
    except ImportError:
        sys.path.insert(0, str(PLUGIN_SRC))
        from admincraft.branding import render_css, validate_brand
    return render_css, validate_brand


# --------------------------------------------------------------------------
# The matrix: sentinel brands one axis at a time (so a divergence names the
# field that caused it), then random combinations.

BASE = {
    "appName": "Freshorama",
    "tagline": "Fresh, fast, fair",
    "colors": {
        "primary": "#7c3aed",
        "accent": "#22c55e",
        "bg": "#0f172a",
        "surface": "#1e293b",
        "text": "#f1f5f9",
    },
    "radius": "0.75rem",
    "font": "Inter",
}

# Fonts are where two encoders can part ways: render_css does
# font.replace(" ", "+") on the raw string, brandToCss runs encodeURIComponent()
# and turns %20 back into "+". A double space, a digit, or the length ceiling is
# where a naive "just replace spaces" diverges.
# Legal-on-both-sides alphabets: a random brand built from these must be
# ACCEPTED by the server, so the accepted half of the matrix is hundreds of
# combinations rather than a handful of survivors.
VALID_FONTS = [
    "Inter",
    "Space Grotesk",
    "IBM Plex Mono",
    "Roboto Flex",
    "Noto Sans 2",
    "Space  Grotesk",       # double space -> "Space++Grotesk" on both sides
    "  Inter  ",            # python .strip() vs TS sanitize + trim
    "\tTabbed Font\t",      # LEGAL, not illegal: both sides strip() before the
                            # regex, so the tabs are eaten identically. It sat in
                            # BAD_FONTS and the server accepted it — measured, and
                            # it is a real twin case, so it stays, on the right side.
    "A" * 60,               # the SAFE_FONT_RE ceiling
    "a",
    "Font With 1 2 3 Digits",
    "Zz",
]

VALID_RADIUS = ["0.75rem", "12px", "2em", "0px", "12.5rem", "999px", "1rem", "0.1em"]

VALID_HEX = ["#7c3aed", "#AABBCC", "#000000", "#ffffff", "#7C3aEd", "#123456",
             "#FF00FF", "#0F1F2E"]

# Illegal-on-the-server values: each one is pinned below as MUST be refused, by
# identity — the count is not trusted, because a printed count with no expectation
# attached is how a softened closed schema passed green.
BAD_FONTS = ["Inter!", "A" * 61, "Naïve Font", "", "   "]
BAD_RADIUS = ["0.5", "0.75rem; }", "1.5", "big", "12 pt", "-4px"]
BAD_HEX = ["#ff00", "red", "#zzzzzz", "#7c3aed ", "7c3aed", "#7c3aed6"]


def _brand(**over):
    b = json.loads(json.dumps(BASE))
    for k, v in over.items():
        if k.startswith("color_"):
            b["colors"][k[6:]] = v
        else:
            b[k] = v
    return b


# The sentinel population, written down as a literal as well as derived from the
# lists above. Both must equal the built matrix or the script refuses to run: that
# is the only way a truncated list becomes a loud failure instead of a smaller,
# still-green verdict. A deliberate change to the matrix is a two-place edit.
EXPECTED_SENTINELS = 49
EXPECTED_DERIVED = (1 + len(VALID_FONTS) + len(BAD_FONTS) + len(VALID_RADIUS)
                    + len(BAD_RADIUS) + len(VALID_HEX) + len(BAD_HEX) + 3)


def build_sentinels():
    """(brand, must_refuse, label) for every deterministic row. `must_refuse` is a
    claim about the SERVER, checked per row in main() — not a filter."""
    rows = [(_brand(), False, "baseline")]
    rows += [(_brand(font=f), False, f"font={f!r}") for f in VALID_FONTS]
    rows += [(_brand(font=f), True, f"font={f!r}") for f in BAD_FONTS]
    rows += [(_brand(radius=r), False, f"radius={r!r}") for r in VALID_RADIUS]
    rows += [(_brand(radius=r), True, f"radius={r!r}") for r in BAD_RADIUS]
    rows += [(_brand(color_primary=h), False, f"primary={h!r}") for h in VALID_HEX]
    rows += [(_brand(color_primary=h), True, f"primary={h!r}") for h in BAD_HEX]
    rows += [(_brand(colors=None), True, "colors=None"),
             (_brand(colors={}), True, "colors={}"),
             (_brand(font=None), True, "font=None")]
    return rows


def build_random(extra: int, seed: int):
    rnd = random.Random(seed)
    out = []
    for _ in range(extra):
        b = _brand(font=rnd.choice(VALID_FONTS), radius=rnd.choice(VALID_RADIUS))
        for k in BASE["colors"]:
            if rnd.random() < 0.6:
                b["colors"][k] = rnd.choice(VALID_HEX)
        if rnd.random() < 0.1:  # one poisoned field per ~10 rows keeps the
            b["colors"][rnd.choice(list(BASE["colors"]))] = rnd.choice(BAD_HEX)
        out.append(b)
    return out


def payload(css: str) -> str:
    """The compared region — from the first @import to the end, trailing
    whitespace stripped (the banners differ by design)."""
    i = css.find(PAYLOAD_MARKER)
    return (css[i:] if i >= 0 else css).rstrip()


def first_diff(a: str, b: str):
    la, lb = a.split("\n"), b.split("\n")
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return i, x, y
    if len(la) != len(lb):
        i = min(len(la), len(lb))
        return i, (la[i] if i < len(la) else "<eof>"), (lb[i] if i < len(lb) else "<eof>")
    return None


def run_client_probe(brand_list, out: Path):
    matrix = out.parent / "brands.json"
    matrix.write_text(json.dumps(brand_list), encoding="utf-8")
    spec = APP / "src" / "lib" / "__tests__" / "zzBrandTwinProbe.tmp.test.ts"
    spec.write_text(CLIENT_SPEC, encoding="utf-8")
    try:
        return subprocess.run(
            ["npx", "vitest", "run", "src/lib/__tests__/zzBrandTwinProbe.tmp.test.ts",
             "--maxWorkers=1"],
            cwd=str(APP), capture_output=True, text=True,
            env={**os.environ, "TWIN_PATHS": f"{matrix},{out}",
                 "NODE_OPTIONS": "--max-old-space-size=1024"},
        )
    except OSError as exc:
        # A missing launcher is exit 2 (rig not runnable), never exit 1
        # (writers disagree) — see the same guard in csv_twin_diff.py.
        return subprocess.CompletedProcess(["npx"], 127, "", f"cannot launch: {exc}\n")
    finally:
        spec.unlink(missing_ok=True)


def describe(b) -> str:
    colors = b.get("colors") if isinstance(b.get("colors"), dict) else {}
    return (f"font={b.get('font')!r} radius={b.get('radius')!r} "
            f"primary={colors.get('primary')!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brands", type=int, default=300, help="random brands (default 300)")
    ap.add_argument("--seed", type=int, default=20261021)
    ap.add_argument("--show", action="store_true", help="print the accepted CSS payload")
    ap.add_argument("--keep", action="store_true", help="keep the work dir")
    args = ap.parse_args()

    if shutil.which("node") is None:
        print("node is required (the runtime side runs the real branding.ts under vitest)",
              file=sys.stderr)
        return 2
    if not (APP / "node_modules").exists():
        print("app/node_modules missing — run `cd app && npm install` first", file=sys.stderr)
        return 2
    try:
        render_css, validate_brand = load_server_writer()
    except Exception as e:
        print(f"cannot import admincraft.branding from {PLUGIN_SRC}: {e}", file=sys.stderr)
        return 2
    if not (PUBLIC_CSS.exists() and PUBLIC_JSON.exists()):
        print("app/public/brand.css or brand.json missing — nothing to hand off", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="brand-twin-"))
    try:
        shipped_brand = json.loads(PUBLIC_JSON.read_text(encoding="utf-8"))
        # A matrix that cannot agree with its own literal has no standing to
        # certify anything, so it refuses (exit 2) instead of reporting a verdict.
        if EXPECTED_SENTINELS != EXPECTED_DERIVED:
            print(f"the matrix disagrees with itself: {EXPECTED_SENTINELS} sentinels in the "
                  f"literal, {EXPECTED_DERIVED} derived from VALID_*/BAD_* — change BOTH when "
                  "the matrix changes on purpose", file=sys.stderr)
            return 2
        sentinels = build_sentinels()
        randoms = build_random(args.brands, args.seed)
        if len(sentinels) != EXPECTED_SENTINELS or len(randoms) != args.brands:
            print(f"MATRIX TRUNCATED: {len(sentinels)} sentinels built against a literal of "
                  f"{EXPECTED_SENTINELS}, {len(randoms)} random rows against --brands "
                  f"{args.brands} — refusing to certify a smaller matrix", file=sys.stderr)
            return 2

        # One pass through the server's own schema, keeping each row's verdict
        # EXPECTATION alongside its result.
        checked = [(b, must_refuse, label, validate_brand(json.loads(json.dumps(b))))
                   for b, must_refuse, label in sentinels]
        checked += [(b, None, "random", validate_brand(json.loads(json.dumps(b))))
                    for b in randoms]
        checked.append((shipped_brand, False, "SHIPPED app/public/brand.json",
                        validate_brand(json.loads(json.dumps(shipped_brand)))))

        # The domain leg: the closed schema must bite exactly where it is pinned.
        softened = [(label, b) for b, mr, label, errs in checked if mr is True and not errs]
        tightened = [(label, errs) for b, mr, label, errs in checked if mr is False and errs]
        if softened or tightened:
            for label, b in softened:
                print(f"SCHEMA SOFTENED — the server now ACCEPTS a brand it must refuse: "
                      f"{label}", file=sys.stderr)
            for label, errs in tightened:
                print(f"LEGAL BRAND REFUSED — {label}: {errs}", file=sys.stderr)
            return 1

        accepted = [brand for brand, _, _, errs in checked if not errs]
        refused = len(checked) - len(accepted)
        pinned = sum(1 for _, mr, _, _ in checked if mr is not None)
        matched = sum(1 for _, mr, _, errs in checked
                      if mr is not None and bool(errs) == mr)
        print(f"population: {len(checked)} candidates = {len(sentinels)} sentinels "
              f"(literal {EXPECTED_SENTINELS}) + {len(randoms)} random + shipped; "
              f"{matched}/{pinned} pinned server verdicts matched")
        print(f"  -> {len(accepted)} accepted by the server, {refused} refused "
              f"(both writers only ever run on the accepted set)")

        client_out = work / "client.json"
        p = run_client_probe(accepted, client_out)
        if p.returncode != 0 or not client_out.exists():
            print(f"client probe failed:\n{p.stdout[-2000:]}{p.stderr[-2000:]}", file=sys.stderr)
            return 2
        runtime_css = json.loads(client_out.read_text(encoding="utf-8"))
        if len(runtime_css) != len(accepted):
            print(f"probe answered {len(runtime_css)} items for {len(accepted)} brands",
                  file=sys.stderr)
            return 2

        # 3. the twins, over every brand the server accepts
        bad = []
        for b, runtime in zip(accepted, runtime_css):
            try:
                built = render_css(json.loads(json.dumps(b)))
            except Exception as e:
                bad.append((b, f"render_css raised {e!r}", None))
                continue
            a, c = payload(built), payload(runtime)
            if a != c:
                bad.append((b, first_diff(a, c), runtime))
        if bad:
            print(f"TWIN DIVERGENCE — {len(bad)} of {len(accepted)} accepted brands",
                  file=sys.stderr)
            for b, d, _ in bad[:20]:
                print(f"  {describe(b)}", file=sys.stderr)
                if isinstance(d, tuple):
                    i, x, y = d
                    print(f"    line {i}: build={x!r} runtime={y!r}", file=sys.stderr)
                else:
                    print(f"    {d}", file=sys.stderr)
            return 1

        # 4 + 5. the bundle the browser paints first, and the boot handoff. The
        # shipped brand is found BY IDENTITY: `runtime_css[-1]` was a position, so a
        # refused brand.json compared its CSS against an unrelated random brand and
        # the verdict named a re-theme flicker that never existed.
        shipped_at = [i for i, b in enumerate(accepted) if b == shipped_brand]
        if not shipped_at:
            print("shipped brand not found in the accepted set by identity — no pair "
                  "to compare (its refusal should already have failed the domain leg)",
                  file=sys.stderr)
            return 2
        bundle_css = PUBLIC_CSS.read_text(encoding="utf-8")
        rebuilt = payload(render_css(json.loads(json.dumps(shipped_brand))))
        injected = payload(runtime_css[shipped_at[-1]])
        if payload(bundle_css) != rebuilt:
            d = first_diff(rebuilt, payload(bundle_css))
            print("BUNDLE STALE — app/public/brand.css is not render_css(brand.json); "
                  "re-run build_admin", file=sys.stderr)
            report(d)
            return 1
        if injected != rebuilt:
            d = first_diff(rebuilt, injected)
            print("HANDOFF DIVERGENCE — the boot-time inject differs from the bundle, "
                  "i.e. a visible re-theme flicker", file=sys.stderr)
            report(d)
            return 1

        print(f"BYTE-IDENTICAL — {len(accepted)} accepted brands over a pinned population "
              f"of {len(checked)}; twins agree under the @import marker; "
              f"bundle == render_css == brandToCss")
        print(f"  build-time banner: {bundle_css.splitlines()[0]}")
        print(f"  runtime banner:    {runtime_css[shipped_at[0]].splitlines()[0]}")
        if args.show:
            print(rebuilt)
        return 0
    finally:
        if args.keep:
            print(f"(--keep) work dir: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


def report(d):
    if isinstance(d, tuple):
        i, x, y = d
        print(f"    line {i}: a={x!r} b={y!r}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
