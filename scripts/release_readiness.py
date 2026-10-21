#!/usr/bin/env python3
"""release_readiness.py — re-run the AGENTS.md "Releases" prose as one command.

The Releases section is a list of claims no check used to enforce:

  * "bump the version in ALL FOUR carriers first" — pyproject, package.json,
    tauri.conf.json (drives the apk versionCode) and Cargo.toml + its lock
    entry. Four files, one truth, and the tag must match them.
  * every path a doc cites must exist. This harness found the counter-example
    while it was being written: `scripts/cut_v010_release.sh` is cited as the
    reference implementation for release assembly in AGENTS.md, docs/DEVGUIDE.md
    and three places in .github/workflows/build-all.yml — and exists in none of
    the repo's git objects (measured with `git rev-list --all --objects`).
  * a `file:line` citation must land INSIDE the file it names. Existence alone is
    half the claim: a refactor that shortens a file turns every `:127` into a
    lie while the path still resolves, and the citation leg would stay green.
    Citations are therefore also bounds-checked against the real file length,
    which is why bare-name citations (`hooks.py:50-58`) are NOT verified — the
    same basename exists both in this repo and in site-packages, and guessing
    which one a doc meant would produce a confident verdict about the wrong file
    (measured: `settings.py:120` resolves to demo-backend/core/settings.py, which
    has 110 lines, while the doc means drf_spectacular's). Write the directory.
  * "no PEP 604 annotations in scripts/*.py" (DEVGUIDE FIFTH law, commit
    1ce3045) — a harness that dies at import on a Python < 3.10 box exits 1,
    which in this family means "the two writers DIVERGE". `ast.parse` cannot
    see it (the syntax is valid); only walking annotation nodes can.

Exit codes follow docs/DEVGUIDE.md FIFTH law: 0 = release story coherent,
1 = a leg is genuinely RED, 2 = the leg could not be RUN. A tool that cannot
start has no opinion about your tree.

Usage (from the repo root):
  python3 scripts/release_readiness.py                  # carriers + citations
  python3 scripts/release_readiness.py --expect 0.2.0   # also: do carriers say this
"""
import argparse
import ast
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GREEN, RED, CANNOT = 0, 1, 2

# Paths the docs quote ON PURPOSE while they are dead (a "the old X is gone"
# note) or imaginary (an illustrative example). Each entry is a claim that the
# path is STILL absent — if it reappears, the allowlist itself is rot and the
# citations leg says so.
CITE_ALLOWLIST = {
    "app/src/lib/widgets.ts": "AGENTS.md:450 quotes it as deliberately deleted",
    "app/src/pages/Thing.svelte": "docs/page-registration.md example, not a file",
    "scripts/cut_v010_release.sh": "AGENTS.md/DEVGUIDE Releases now state it was "
                                   "never committed; if it appears, the citation "
                                   "and this entry both need updating",
}

# Same reverse bite as CITE_ALLOWLIST, for the NUMBER rather than the path: a
# citation whose line is legitimately out of range because it quotes a TOOL
# MESSAGE instead of naming a location. An entry goes RED when the line starts
# to land inside the file, so the exemption cannot outlive its reason.
CITE_LINE_ALLOWLIST = {
    "docs/widget-data.md:127": "docs/DEVGUIDE.md quotes this harness's own reject "
                               "message from a control run — a quoted string, not "
                               "a location claim",
}

# Third-party families whose citations CAN be verified when the package is
# installed in the interpreter running this check (docs/independent-enums.md
# measures drf-spectacular behaviour line by line).
EXTERNAL_PKGS = ("drf_spectacular", "rest_framework", "django")

CITE_DOCS = ["AGENTS.md", "README.md", "docs/DEVGUIDE.md", "docs/csv-export.md",
             "docs/rbac.md", "docs/widget-data.md", "docs/page-registration.md",
             "docs/order-lifecycle.md", "docs/custom-actions.md",
             "docs/independent-enums.md"]

TOP_DIRS = {p.name for p in ROOT.iterdir() if p.is_dir()}
CITE_TOK = re.compile(r"`([^`\n]+)`")
CITE_SHAPE = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)+$")
# path[:lo[-hi]] — a bare ":125" continuation never matches (path is required),
# because the only other thing that shape catches is a PORT (`:11435`,
# `127.0.0.1:8042`) and a port inherited from the neighbouring token would be
# read as a line number and reported as a false citation.
CITE_FULL = re.compile(r"^(?P<path>[\w.\-]+(?:/[\w.\-]+)*)"
                       r"(?::(?P<lo>\d+)(?:-(?P<hi>\d+))?)?$")

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "target",
             "__pycache__", ".pytest_cache", "sessions", "site-packages",
             "build", ".next"}


class CannotRun(Exception):
    pass


class LegRed(Exception):
    pass


def launch(argv, cwd=None):
    try:
        return subprocess.run([str(a) for a in argv], cwd=str(cwd or ROOT),
                              capture_output=True, text=True)
    except OSError as exc:
        raise CannotRun("cannot launch %r: %s" % (argv[0], exc))


def read(rel):
    p = ROOT / rel
    if not p.is_file():
        raise CannotRun("%s is missing — the release story has no input to read" % rel)
    return p.read_text()


def line_of(text, needle):
    for n, ln in enumerate(text.split("\n"), 1):
        if needle in ln:
            return n, ln.strip()
    return None, None


def carriers():
    """The four carriers as (name, file:line, value)."""
    found = []
    for rel, needle in (("plugin/pyproject.toml", "version ="),
                        ("app/package.json", '"version"'),
                        ("app/src-tauri/tauri.conf.json", '"version"'),
                        ("app/src-tauri/Cargo.toml", "version =")):
        text = read(rel)
        n, ln = line_of(text, needle)
        if n is None:
            raise LegRed("%s: no %r line — the carrier cannot be read" % (rel, needle))
        m = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][\w.]+)?)", ln)
        if not m:
            raise LegRed("%s:%d carries no version: %s" % (rel, n, ln))
        found.append(("cargo" if rel.endswith("Cargo.toml") else rel,
                      "%s:%d" % (rel, n), m.group(1)))
    lock = read("app/src-tauri/Cargo.lock")
    m = re.search(r'name = "admincraft"\nversion = "([^"]+)"', lock)
    if not m:
        raise LegRed("Cargo.lock: no admincraft entry — `cargo` builds cannot be "
                     "trusted to match Cargo.toml")
    found.append(("cargo-lock", "app/src-tauri/Cargo.lock (admincraft entry)",
                  m.group(1)))
    return found


def leg_carriers(expect, log):
    found = carriers()
    values = {v for _, _, v in found}
    if len(values) != 1:
        raise LegRed("version carriers disagree: %s"
                     % ", ".join("%s=%s" % (name, v) for name, _, v in found))
    version = values.pop()
    if expect and expect != version:
        raise LegRed("carriers all say %s but --expect asked for %s (%s)"
                     % (version, expect, found[0][1]))
    log("carriers %s in %d carriers (%s)"
        % (version, len(found), ", ".join(loc for _, loc, _ in found)))
    return version


def leg_tag(log):
    proc = launch(["git", "tag", "--points-at", "HEAD"])
    if proc.returncode != 0:
        raise CannotRun("git tag failed: %s" % proc.stderr.strip())
    tags = [t for t in proc.stdout.split() if t.startswith("v")]
    values = {v for _, _, v in carriers()}
    if len(values) != 1:
        raise LegRed("carriers disagree, so there is no version to match a tag "
                     "against: %s" % values)
    version = values.pop()
    if not tags:
        log("tag       HEAD carries no vX.Y.Z tag (carriers still binding: %s)"
            % version)
        return
    bad = [t for t in tags if t[1:] != version]
    if bad:
        raise LegRed("tag(s) %s do not match the carriers' %s — AGENTS.md: "
                     "\"the tag should match them\"" % (", ".join(bad), version))
    log("tag       %s == carriers %s" % (", ".join(tags), version))


def repo_files():
    """Every tracked-ish file, as paths relative to ROOT (caches per call)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(str(ROOT)):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            out.append(str(Path(dirpath, f).relative_to(ROOT)).replace(os.sep, "/"))
    return out


def site_file(path):
    """Resolve `drf_spectacular/hooks.py` through the installed package.

    Returns (abs_path_or_None, version_or_None, state) where state is "ok",
    "not-external", "not-installed" or "not-in-package" — the caller must not
    turn the last three into a verdict about the doc.
    """
    pkg = path.split("/")[0]
    if pkg not in EXTERNAL_PKGS:
        return None, None, "not-external"
    try:
        mod = importlib.import_module(pkg)
    except Exception:
        return None, None, "not-installed"
    root = os.path.dirname(getattr(mod, "__file__", "") or "")
    candidate = os.path.join(root, *path[len(pkg) + 1:].split("/"))
    if not root or not os.path.isfile(candidate):
        return None, getattr(mod, "__version__", "?"), "not-in-package"
    return candidate, getattr(mod, "__version__", "?"), "ok"


_line_counts = {}


def line_count(absolute):
    key = str(absolute)
    if key not in _line_counts:
        _line_counts[key] = len(Path(key).read_text(errors="replace").splitlines())
    return _line_counts[key]


def citations():
    """One scanner, two assertions: every backticked citation in CITE_DOCS.

    Yields (path, lo, hi, token, where). The noise filters are the reason this
    can be strict at all — `+00:00`, `:11435`, `127.0.0.1:8042` and `StatusEnum`
    must never reach the checks, so a token only counts when its last segment
    carries a plausible (non-numeric, short) extension.
    """
    for rel in CITE_DOCS:
        p = ROOT / rel
        if not p.is_file():
            continue
        for n, line in enumerate(p.read_text().split("\n"), 1):
            for tok in CITE_TOK.findall(line):
                m = CITE_FULL.match(tok.strip())
                if not m:
                    continue
                path = m.group("path")
                stem = path.rsplit("/", 1)[-1]
                if "." not in stem:
                    continue
                ext = stem.rsplit(".", 1)[-1]
                if not ext or len(ext) > 6 or ext.isdigit():
                    continue
                yield (path, m.group("lo"), m.group("hi"), tok.strip(),
                       "%s:%d" % (rel, n))


def leg_citations(log):
    missing, revived = [], []
    scanned, resolved = [], set()
    for rel in CITE_DOCS:
        if (ROOT / rel).is_file():
            scanned.append(rel)
    for path, lo, hi, tok, where in citations():
        if path.split("/")[0] not in TOP_DIRS:
            continue
        if not CITE_SHAPE.match(path):
            continue
        exists = (ROOT / path).exists()
        if exists:
            resolved.add(path)
        if not exists and path not in CITE_ALLOWLIST:
            missing.append((path, where))
        elif exists and path in CITE_ALLOWLIST:
            revived.append((path, where))
    if revived:
        raise LegRed("allowlist is stale — %s now EXISTS, so quoting it as "
                     "deliberately-dead is false: %s"
                     % (", ".join(sorted({t for t, _ in revived})),
                        "; ".join(sorted({c for _, c in revived}))))
    if missing:
        raise LegRed("%d doc citation(s) point at paths that do not exist: %s"
                     % (len(set(t for t, _ in missing)),
                        "; ".join("%s <- %s" % (t, c) for t, c in sorted(set(missing)))))
    log("citations %d doc(s), %d repo path citation(s) resolve, %d allowed dead"
        % (len(scanned), len(resolved), len(CITE_ALLOWLIST)))


def leg_citation_lines(log):
    """Every citation that names a line must land inside that file.

    Verified only when the target is unambiguous: an exact repo path, or a
    repo path whose directory suffix matches exactly one file, or a site-packages
    path that the running interpreter can find. A bare filename is NOT guessed.
    """
    files = repo_files()
    verified = 0
    repo_ok, site_ok = 0, 0
    site_versions = set()
    bare, unresolved, allowed = [], [], []
    past = []
    stale_allow = []
    for path, lo, hi, tok, where in citations():
        if lo is None:
            continue
        absolute, kind = None, None
        if (ROOT / path).is_file():
            absolute, kind = str(ROOT / path), "repo"
        elif "/" in path:
            suffix = [f for f in files if f.endswith("/" + path)]
            if len(suffix) == 1:
                absolute, kind = str(ROOT / suffix[0]), "repo"
            else:
                cand, ver, state = site_file(path)
                if state == "ok":
                    absolute, kind = cand, "site"
                    site_versions.add("%s %s" % (path.split("/")[0], ver))
                elif state in ("not-installed", "not-in-package"):
                    unresolved.append((tok, where, state))
                    continue
                else:
                    unresolved.append((tok, where, "ambiguous" if len(suffix) > 1
                                       else "absent"))
                    continue
        else:
            hits = [f for f in files if f.rsplit("/", 1)[-1] == path]
            bare.append((tok, where, len(hits)))
            continue
        if absolute is None:
            continue
        total = line_count(absolute)
        upper = int(hi or lo)
        verified += 1
        if kind == "repo":
            repo_ok += 1
        else:
            site_ok += 1
        if upper > total or upper < 1:
            if tok in CITE_LINE_ALLOWLIST:
                allowed.append(tok)
            else:
                past.append("%s cited at %s, but %s has %d line(s)"
                            % (tok, where, path, total))
        elif tok in CITE_LINE_ALLOWLIST:
            stale_allow.append("%s: line %d is INSIDE %s (%d lines), so the "
                               "quoted-message exemption no longer applies — %s"
                               % (tok, upper, path, total, CITE_LINE_ALLOWLIST[tok]))
    if stale_allow:
        raise LegRed("line allowlist is stale — %s" % "; ".join(sorted(stale_allow)))
    if past:
        raise LegRed("%d citation(s) point past the end of the file they name — "
                     "the path still resolves, so the citations leg cannot see "
                     "this: %s" % (len(past), "; ".join(sorted(set(past)))))
    log("lines     %d citation(s) bounds-checked (%d repo, %d site-packages%s), "
        "%d bare-name not verified, %d unresolvable, %d allowed quoted-message "
        "out-of-range — a bare citation is a guess, so write the directory"
        % (verified, repo_ok, site_ok,
           " against " + ", ".join(sorted(site_versions)) if site_versions else "",
           len(bare), len(unresolved), len(allowed)))


def leg_scripts_ast(log):
    d = ROOT / "scripts"
    if not d.is_dir():
        raise CannotRun("scripts/ is missing")
    files = sorted(d.glob("*.py"))
    if not files:
        raise CannotRun("scripts/*.py: nothing to check")
    offenders = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(), filename=str(f))
        except SyntaxError as exc:
            raise LegRed("%s does not parse: line %s: %s"
                         % (f.name, exc.lineno, exc.msg))
        for node in ast.walk(tree):
            anns = []
            if isinstance(node, ast.AnnAssign):
                anns.append(node.annotation)
            elif isinstance(node, (ast.arg, ast.FunctionDef, ast.AsyncFunctionDef)):
                anns += [node.annotation] if isinstance(node, ast.arg) else []
                anns += [getattr(node, "returns", None)]
            for a in anns:
                if isinstance(a, ast.BinOp) and isinstance(a.op, ast.BitOr):
                    offenders.append("%s:%d" % (f.name, a.lineno))
    if offenders:
        raise LegRed("PEP 604 `X | None` annotation(s) in a harness — on a Python "
                     "< 3.10 box this raises at def time and exits 1, which this "
                     "family means \"the writers DIVERGE\": %s"
                     % ", ".join(sorted(set(offenders))))
    log("scripts   %d .py file(s) parse, no PEP 604 annotation in any signature"
        % len(files))


def leg_inputs(log):
    needed = ["plugin/pyproject.toml", "app/src-tauri/signing/debug.keystore",
              "flake.nix", "guix.scm", ".github/workflows/build-all.yml"]
    missing = [n for n in needed if not (ROOT / n).exists()]
    if missing:
        raise LegRed("release input(s) absent, so the workflow cannot assemble "
                     "assets: %s" % ", ".join(missing))
    log("inputs    %d release input(s) present (%s)"
        % (len(needed), ", ".join(n.split("/")[-1] for n in needed)))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expect", help="the version the carriers must all say")
    opts = parser.parse_args(argv)

    def log(line):
        print(line)

    legs = [(leg_carriers, (opts.expect, log)), (leg_tag, (log,)),
            (leg_citations, (log,)), (leg_citation_lines, (log,)),
            (leg_scripts_ast, (log,)), (leg_inputs, (log,))]
    failures = []
    for fn, args in legs:
        try:
            fn(*args)
        except CannotRun as exc:
            print("CANNOT RUN — %s" % exc)
            return CANNOT
        except LegRed as exc:
            failures.append(str(exc))
    for f in failures:
        print("RED — %s" % f)
    if failures:
        print("RELEASE READINESS RED (%d leg(s))" % len(failures))
        return RED
    print("RELEASE READINESS GREEN — carriers, tag, citations (paths and line "
          "numbers), harness grammar and release inputs each asserted their own "
          "fact")
    return GREEN


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # a crash is not a verdict: 2, never 1
        print("CANNOT RUN — harness failure %s: %s" % (type(exc).__name__, exc))
        sys.exit(CANNOT)
