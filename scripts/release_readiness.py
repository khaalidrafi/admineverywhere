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
  * inside the file is not yet ON TARGET. A bounds check sees a number that
    lands somewhere, never that it lands where the prose says: DEVGUIDE cited
    `scripts/csv_twin_diff.py:109` for `run()` while 109 was the closing
    triple-quote of `CLIENT_SPEC` and `run()` started at 126 — green, and wrong
    (DEVGUIDE *TENTH
    law*, third door). So a citation whose own doc line also spells a `name()`
    claim must have that name inside the cited range. The claim class is
    deliberately narrow: broadening it to any backticked identifier on the same
    line was measured to produce three FALSE reds — `StatusEnum` is *data*
    produced at `drf_spectacular/hooks.py:91`, never spelled there, and
    `demo-backend/shop/models.py:87` is cited for `Order` by lexical
    containment, not by line text. A leg that fires on a correct citation is
    worse than no leg: it teaches the reader to ignore it.
  * "no PEP 604 annotations in scripts/*.py" (DEVGUIDE FIFTH law, commit
    1ce3045) — a harness that dies at import on a Python < 3.10 box exits 1,
    which in this family means "the two writers DIVERGE". `ast.parse` cannot
    see it (the syntax is valid); only walking annotation nodes can.
  * every suite count AND every control-roster count the docs publish as an
    INSTRUCTION (inside `## Layout` / `## Commands`) must equal the pin the
    harness enforces. The rosters were the last published-but-ungraded number:
    AGENTS.md instructs `12 controls` for scripts/chat_feature_check.py, which
    carried no `EXPECTED_CONTROLS` literal at all, so deleting a control there
    printed a smaller N in its own `SELFTEST OK` while the doc — and every report
    written from it — kept promising 12 with nothing in the tree to notice.

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
import importlib.util
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
# Empty by measurement: its only entry exempted DEVGUIDE's quote of a control
# message naming docs/widget-data.md:127 while that file had 125 lines; a later
# doc edit grew the file past 127, the leg said so, and the prose moved to a
# number-free historical note instead of keeping the exemption alive.
CITE_LINE_ALLOWLIST = {}

# The same reverse bite for the TARGET leg, from BOTH ends (each measured as a
# control, and both doors were found BY the controls — the first version of this
# leg had only the second and passed rc 0 over the first):
#  * an exemption whose citation token is no longer scanned is RED: the historical
#    quote it exempted has been rewritten, and an unused exemption reads as
#    "handled" while silently covering whatever is written into its place
#    (measured: retargeting the quoted `:109` to `:248` left a hits-only leg
#    GREEN, rc 0);
#  * an exemption whose token is still scanned but whose cited range NOW carries
#    the symbol is RED, because the prose is a true live pointer and needs no
#    exemption.
# The token (path + line), not the path, because one file can carry both the
# historical quote and a live pointer: exempting `csv_twin_diff.py` wholesale
# would exempt the `:248` witness claim too and delete the leg's whole subject.
CITE_TARGET_ALLOWLIST = {
    "scripts/csv_twin_diff.py:109": "AGENTS.md *Releases* and docs/DEVGUIDE.md "
                                    "*TENTH law* third door both quote the PRE-FIX "
                                    "file, whose line 109 was the closing "
                                    "triple-quote of CLIENT_SPEC — a historical "
                                    "claim about a number that was wrong, not a "
                                    "pointer to today's code",
}

# The witness. This leg exists because of one measured wrong-target citation, so
# that claim is pinned by identity: if the doc ever stops spelling `run()` about
# this file, the leg silently loses the only case it was proven on and would stay
# green over a reintroduced drift (DEVGUIDE *ELEVENTH law* — a comparison cannot
# see its own coverage). Path + symbol, deliberately NOT the line number: the
# number is the thing under test, and a witness keyed by it would fire on every
# wrong-target mutation and mask the very verdict it is there to report
# (measured: control 1 reported "lost witness" instead of "wrong target" until
# the key dropped the number).
REQUIRED_CLAIMS = {
    ("scripts/csv_twin_diff.py", "run"): "the citation this leg was written for: "
                                         "DEVGUIDE points at run() and must keep "
                                         "pointing at run()",
}

# This leg's own population, pinned twice like every other harness in the
# family: the literal below must agree with the number of symbol claims the scan
# actually derived, or the harness does not understand its own input (a regex
# that silently matched nothing would otherwise report a vacuous GREEN). Measured
# the moment it was written: adding the AGENTS.md *Releases* paragraph, which
# quotes the same historical `:109` claim, moved this literal 7 -> 8 — the pin
# fires on its own doc edits, so a deliberate change is a two-place edit and an
# accidental one is a RED. Measured again the same way: the DEVGUIDE paragraph
# documenting the landing_gate population pin cites `population()`
# (scripts/landing_gate.py:158), moving 8 -> 9 in the same commit as the leg. That
# paragraph then grew the roster pin, which is two more `name()` claims of its own —
# the literal moved 9 -> 11 the same deliberate way, measured not guessed. Measured a
# FOURTH time the same way: the machine-gate paragraph documents the spec the merge legs
# EXECUTE, so it cites `leg_pytest()` (scripts/landing_gate.py:233) and `leg_django()`
# (scripts/landing_gate.py:256) — the leg answered 13 against this 11, and 11 -> 13 is
# the remedy it printed, applied in this same commit. Measured a FIFTH time: the
# doc-count paragraph cites this leg's own two entry points, and the leg answered 15 —
# it caught the bump while the prose was still being written, because the citation was
# spelled in plain parens and the scanner only reads backticked ones (see DEVGUIDE
# TENTH law: an unscanned citation is an ungraded claim).
# Measured a SIXTH time: the case-C closure rewrote docs/independent-enums.md §4 and
# answered 14 — the rewritten prose had dropped the live `deref()` claim. The claim was
# RESTORED (the citation is still true, the function still follows a top-level $ref) and
# the section's new `unionMembers()`/`propToField()` citations entered on target, so the
# deliberate population is 16 — a two-place edit, applied in this same commit.
# Measured a SEVENTH time: the control-roster paragraph in docs/DEVGUIDE.md cites
# `leg_control_counts()` and `control_roster()` and the leg answered 17 — it fired on
# the doc being written, exactly as it did the sixth time, so the new population is
# pinned here rather than re-typed from a print.
EXPECTED_CLAIMS = 17

# `name()` spellings only. Control words that are commonly written with parens in
# prose (`if (x)`, `for (let i)`) are not claims about the cited code.
SYM_CLAIM = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(\)")
SYM_STOPWORDS = {"if", "for", "while", "switch", "catch", "return", "await"}

# Third-party families whose citations CAN be verified when the package is
# installed in the interpreter running this check (docs/independent-enums.md
# measures drf-spectacular behaviour line by line).
EXTERNAL_PKGS = ("drf_spectacular", "rest_framework", "django")

CITE_DOCS = ["AGENTS.md", "README.md", "docs/DEVGUIDE.md", "docs/csv-export.md",
             "docs/rbac.md", "docs/widget-data.md", "docs/page-registration.md",
             "docs/order-lifecycle.md", "docs/custom-actions.md",
             "docs/independent-enums.md"]

# ------------------------------------------------------------------ DOC COUNTS
# The docs that publish suite-size numbers as INSTRUCTIONS (the Layout table and
# the Commands block) must state the size the landing gate actually owes. Closed
# table of those live claims: (doc, anchor that must be unique in that doc, kind).
DOC_COUNT_CLAIMS = [
    ("AGENTS.md", "pip package `admincraft`", "pytest"),
    ("AGENTS.md", "thin client — Vite 6", "vitest"),
    ("AGENTS.md", "cd app && npm test", "vitest"),
    ("AGENTS.md", "-m pytest ../plugin/tests", "pytest"),
    ("docs/DEVGUIDE.md", "pip package `admincraft`", "pytest"),
    ("docs/DEVGUIDE.md", "thin client — Vite 6", "vitest"),
    ("docs/DEVGUIDE.md", "cd app && npm test", "vitest"),
    ("docs/DEVGUIDE.md", "-m pytest ../plugin/tests", "pytest"),
]
EXPECTED_DOC_CLAIMS = 8

# Sections whose count claims are LIVE INSTRUCTIONS, i.e. fully graded. Claims
# outside them are narrative records and deliberately out of domain.
DOC_LIVE_SECTIONS = ("## Layout", "## Commands")

# Which pin in scripts/landing_gate.py each kind of claim must equal.
DOC_PIN_NAMES = {"pytest": "EXPECTED_PYTEST", "vitest": "EXPECTED_VITEST"}

# ------------------------------------------------------- CONTROL-ROSTER COUNTS
# `--selftest # 10 controls` is the SAME class as a suite count published as an
# INSTRUCTION: a reader follows the number, a control is deleted, the harness
# prints a smaller N and the doc — and every report written from it — still
# promises the old one. The suite pins live in ONE gate, so the doc-count table
# above can map kind -> landing_gate literal; each harness pins its OWN control
# roster, so a control claim resolves its truth from the script named on the very
# doc line that carries the number. Three views must be one number: the number a
# reader follows, the harness's `EXPECTED_CONTROLS` literal, and the length of the
# `CONTROLS` roster that literal is supposed to be grading.
CONTROL_NUM = re.compile(r"\b(\d+)\s+controls\b")
CONTROL_TOKEN = re.compile(r"\bscripts/([\w.\-]+\.py)\b")
CONTROL_DOCS = ["AGENTS.md", "docs/DEVGUIDE.md"]
CONTROL_SECTIONS = ("## Commands",)
CONTROL_PIN_ASSIGN = re.compile(r"^EXPECTED_CONTROLS\s*=\s*(\d+)\s*$", re.M)
# The pin must be COMPARED by the harness itself, or it is a second number nobody
# reads — the exact shape that let `SELFTEST OK` print a shrunk roster for two
# cycles (DEVGUIDE *ELEVENTH law*, applied to a harness's own legs).
CONTROL_PIN_ASSERTED = "len(CONTROLS) != EXPECTED_CONTROLS"
# 7 claims over 5 harness sites inside `## Commands`: chain_test_check,
# chain_session_check and chat_feature_check in AGENTS.md; chain_test_check and
# chain_session_check again in docs/DEVGUIDE.md. chat_when_check carries the
# third DEVGUIDE line and the fourth in AGENTS.md, so a mirror on ONE side only
# would leave its own roster ungraded by a reader.
EXPECTED_CONTROL_CLAIMS = 7

# "299 pytest" and "pytest 299" both spell a claim; the number may sit on either
# side of the word, so both orientations are read.
DOC_NUM = re.compile(r"(\d+)\s+(pytest|vitest)\b|\b(pytest|vitest)\s+(\d+)")

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
    """One scanner, three assertions: every backticked citation in CITE_DOCS.

    Yields (path, lo, hi, token, where, line). The noise filters are the reason
    this can be strict at all — `+00:00`, `:11435`, `127.0.0.1:8042` and
    `StatusEnum` must never reach the checks, so a token only counts when its
    last segment carries a plausible (non-numeric, short) extension. `line` is
    the doc's own text because the target leg must read the claim the citation
    travels with; a second scan of the docs would be a second opinion, not the
    same one, and the two could drift apart.
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
                       "%s:%d" % (rel, n), line)


def leg_citations(log):
    missing, revived = [], []
    scanned, resolved = [], set()
    for rel in CITE_DOCS:
        if (ROOT / rel).is_file():
            scanned.append(rel)
    for path, lo, hi, tok, where, line in citations():
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


def resolve_target(path, files):
    """Where a cited path actually IS, or why it cannot be known.

    One resolver, shared by the bounds leg and the target leg on purpose: two
    implementations of "which file did the doc mean" would be free to disagree,
    and a leg that checks a number against a different file than the leg that
    reads the number is a verdict about nothing.

    Returns (absolute, kind, state, version) with kind in ("repo", "site", None),
    state one of "ok", "bare", "ambiguous", "absent", "not-installed",
    "not-in-package". A bare filename is NEVER guessed: the same basename exists
    in this repo and in site-packages, so the resolver reports it and stops.
    """
    if (ROOT / path).is_file():
        return str(ROOT / path), "repo", "ok", None
    if "/" in path:
        suffix = [f for f in files if f.endswith("/" + path)]
        if len(suffix) == 1:
            return str(ROOT / suffix[0]), "repo", "ok", None
        cand, ver, state = site_file(path)
        if state == "ok":
            return cand, "site", "ok", ver
        if state in ("not-installed", "not-in-package"):
            return None, None, state, ver
        return None, None, "ambiguous" if len(suffix) > 1 else "absent", ver
    return None, None, "bare", None


def cited_window(absolute, lo, hi):
    """The text the citation points at: lo..hi, or lo..lo+2 for a single line."""
    text = Path(absolute).read_text(errors="replace").split("\n")
    upper = int(hi) if hi else int(lo) + 2
    return "\n".join(text[max(0, int(lo) - 1):upper])


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
    for path, lo, hi, tok, where, line in citations():
        if lo is None:
            continue
        absolute, kind, state, ver = resolve_target(path, files)
        if state == "bare":
            hits = [f for f in files if f.rsplit("/", 1)[-1] == path]
            bare.append((tok, where, len(hits)))
            continue
        if state != "ok":
            unresolved.append((tok, where, state))
            continue
        if kind == "site":
            site_versions.add("%s %s" % (path.split("/")[0], ver))
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


def symbol_claims(files):
    """Every (citation token, symbol) claim the docs make, with its resolution.

    Yields dicts so each caller reads the same derived population — the count
    check, the witness check and the verdict check must never scan differently.
    A claim exists only when the citation and a `name()` spelling sit on the SAME
    doc line: prose that names the symbol on the following wrapped line would
    cross-attribute claims between two citations on that line, and a leg that
    fires on a correct citation is worse than no leg.
    """
    for path, lo, hi, tok, where, line in citations():
        if lo is None:
            continue
        syms = sorted({s for s in SYM_CLAIM.findall(line)
                       if s not in SYM_STOPWORDS})
        if not syms:
            continue
        absolute, kind, state, _ver = resolve_target(path, files)
        for sym in syms:
            yield {"path": path, "tok": tok, "where": where, "sym": sym,
                   "lo": lo, "hi": hi, "absolute": absolute, "state": state}


def leg_citation_targets(log):
    """In range is not on target: a cited line must carry the symbol its prose names.

    This is the class the bounds leg structurally cannot see — the number is
    inside the file, so the citation is green while it sends the reader to
    unrelated code. Measured on this repo's own DEVGUIDE, which cited
    `scripts/csv_twin_diff.py:109` for `run()` while that line was the closing
    triple-quote of `CLIENT_SPEC`.
    """
    files = repo_files()
    claims = list(symbol_claims(files))
    if len(claims) != EXPECTED_CLAIMS:
        raise CannotRun("this leg does not understand its own input: %d symbol "
                        "claim(s) scanned against a pinned population of %d — a "
                        "claim that vanished silently would make the leg green "
                        "over less coverage, so a deliberate change is a two-place "
                        "edit (release_readiness.py:EXPECTED_CLAIMS)"
                        % (len(claims), EXPECTED_CLAIMS))
    seen = set()
    claim_toks = set()
    off, unverified, exempt, stale_exempt = [], [], [], []
    for c in claims:
        claim_toks.add(c["tok"])
        if c["state"] != "ok":
            unverified.append("%s %s (%s)" % (c["tok"], c["sym"], c["state"]))
            continue
        total = line_count(c["absolute"])
        upper = int(c["hi"] or c["lo"])
        if upper > total:
            unverified.append("%s %s (past end of %d lines)"
                              % (c["tok"], c["sym"], total))
            continue
        hits = c["sym"] in cited_window(c["absolute"], c["lo"], c["hi"])
        if c["tok"] in CITE_TARGET_ALLOWLIST:
            # An exempted claim never enters `seen`: the witness is the claim this
            # leg PROVES, and a historical quote the leg refuses to judge cannot
            # count as proof that the live pointer is still there (measured — a
            # doc that dropped the live `run()` claim stayed GREEN rc 0 while the
            # historical quote beside it still spelled the symbol).
            if hits:
                stale_exempt.append(
                    "%s — %s: the cited range NOW carries `%s`, so the "
                    "historical-quote exemption has outlived its reason and the "
                    "prose reads as a live pointer (%s)"
                    % (c["tok"], c["where"], c["sym"], CITE_TARGET_ALLOWLIST[c["tok"]]))
            else:
                exempt.append(c["tok"])
            continue
        seen.add((c["path"], c["sym"]))
        if not hits:
            found = [i + 1 for i, ln in
                     enumerate(Path(c["absolute"]).read_text(errors="replace")
                              .split("\n")) if c["sym"] in ln]
            off.append("%s cites %s for `%s()`, but line %s of that file is not "
                       "it — the name appears at %s (in-range, WRONG target: a "
                       "bounds check cannot see this)"
                       % (c["where"], c["tok"], c["sym"], c["lo"],
                          ", ".join(str(n) for n in found[:4]) or "nowhere"))
    # Every finding is reported, not just the first. A leg that raises on one door
    # hides the others and has to be run again to see them (measured: with
    # first-failure raises, the wrong-target verdict masked the lost witness, and
    # the lost witness masked the wrong target, depending on which mutation the
    # control applied) — so each door appends, and the leg's one verdict lists all.
    findings = []
    if off:
        findings.append("%d citation(s) land inside the file but NOT on the symbol "
                        "the prose names: %s"
                        % (len(off), "; ".join(sorted(set(off)))))
    lost = ["(%s, `%s()`) — %s" % (path, sym, REQUIRED_CLAIMS[(path, sym)])
            for (path, sym) in sorted(REQUIRED_CLAIMS) if (path, sym) not in seen]
    if lost:
        findings.append("the target leg lost its witness — the claim it was proven "
                        "on is no longer verifiably scanned, so the leg would stay "
                        "green over a reintroduced drift: %s" % "; ".join(lost))
    # An exemption that matches nothing is as dangerous as one that matches too
    # much: it reads as "handled" while covering a claim that no longer exists,
    # and would silently cover whatever is written into its place.
    unused = sorted(set(CITE_TARGET_ALLOWLIST) - claim_toks)
    if unused:
        findings.append("target exemption(s) match no scanned claim — %s: the "
                        "historical quote they exempted is gone, so the exemption "
                        "covers nothing the leg reads (%s)"
                        % (", ".join(unused),
                           "; ".join(sorted(CITE_TARGET_ALLOWLIST[k] for k in unused))))
    if stale_exempt:
        findings.append("target exemption is stale — %s" % "; ".join(sorted(stale_exempt)))
    if findings:
        raise LegRed("; ".join(findings))
    log("targets   %d symbol claim(s) over %d citation(s): every cited range "
        "carries the name its own doc line spells (%d exempted as a historical "
        "quote, %d not verifiable), population pinned against a literal of %d"
        % (len(claims), len(set(c["tok"] for c in claims)), len(exempt),
           len(unverified), EXPECTED_CLAIMS))


def doc_nums(line):
    """Every (number, kind) count claim on one doc line, either word order."""
    pairs = []
    for m in DOC_NUM.finditer(line):
        if m.group(1):
            pairs.append((int(m.group(1)), m.group(2)))
        else:
            pairs.append((int(m.group(4)), m.group(3)))
    return pairs


def section_span(text, header, rel):
    """The 1-based line span of one `## ` section, or CANNOT RUN.

    Sections, not regexes over the whole file: a heuristic "is this count claim
    live or historical?" scan was measured to fire on narrative that is true as
    written (DEVGUIDE's own control records, AGENTS.md's dated state log), and a
    leg that fires on a correct sentence is worse than no leg. A header is
    structural and does not move when prose is re-wrapped.
    """
    lines = text.split("\n")
    starts = [n for n, ln in enumerate(lines, 1) if ln.strip() == header]
    if len(starts) != 1:
        raise CannotRun("%s: header %r matched %d line(s) — this leg tells a live "
                        "instruction from narrative by the section it sits in, so a "
                        "duplicated or vanished header leaves it unable to say which "
                        "claims it is grading" % (rel, header, len(starts)))
    first = starts[0]
    for n in range(first + 1, len(lines) + 1):
        if lines[n - 1].startswith("## ") and not lines[n - 1].startswith("### "):
            return (first, n - 1)
    return (first, len(lines))


def section_claims(text, lo, hi):
    out = []
    lines = text.split("\n")
    for n in range(lo, hi + 1):
        for num, kind in doc_nums(lines[n - 1]):
            out.append((n, num, kind))
    return out


def gate_pins():
    """The landing gate's pins, read TWO independent ways and never re-spelled here.

    Source text first (a pin that stops being a plain literal is a pin a doc cannot
    quote as one number), then the imported module — and the two views must agree,
    which is the same "two copies of one intent are the weakest pin" law the twin
    roster applies against the filesystem instead of a second list.
    """
    src = read("scripts/landing_gate.py")
    names = sorted(set(DOC_PIN_NAMES.values()))
    parsed = {}
    for name in names:
        m = re.search(r"^%s\s*=\s*(\d+)\s*$" % name, src, re.M)
        if not m:
            raise CannotRun("scripts/landing_gate.py does not assign %s as a plain "
                            "integer literal — a doc that quotes ONE number has no "
                            "single pin to be graded against" % name)
        parsed[name] = int(m.group(1))
    try:
        spec = importlib.util.spec_from_file_location(
            "_landing_gate_pins", str(ROOT / "scripts" / "landing_gate.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:
        raise CannotRun("scripts/landing_gate.py cannot be imported to read its own "
                        "pins (%s: %s)" % (type(exc).__name__, exc))
    for name in names:
        live = getattr(mod, name, None)
        if live != parsed[name]:
            raise CannotRun("%s reads %r from the source text but %r from the "
                            "imported module — the pin is computed, so the number the "
                            "gate enforces is not the number the docs could quote"
                            % (name, parsed[name], live))
    return parsed


def leg_doc_counts(log):
    """What the docs TELL A READER the suites hold must equal what the gate OWES.

    The population pins in scripts/landing_gate.py are graded against the runners,
    and their own comment says those literals "are also quoted in AGENTS.md and the
    CI header". Nothing compared the quotes to the literals, so the last link of
    the chain was prose: bump a pin without bumping the docs (or the reverse) and
    every report written from the doc cites a suite size no gate owes — measured
    pre-fix on this tree, AGENTS.md's `npm test` line retyped to a different number
    answered RELEASE READINESS GREEN, rc 0.
    """
    if len(DOC_COUNT_CLAIMS) != EXPECTED_DOC_CLAIMS:
        raise CannotRun("DOC_COUNT_CLAIMS lists %d live claim(s), EXPECTED_DOC_CLAIMS "
                        "pins %d — a row deleted from the table drops that number out "
                        "of the compare and the doc drifts unmeasured, so a deliberate "
                        "change is a two-place edit (release_readiness.py:"
                        "EXPECTED_DOC_CLAIMS)" % (len(DOC_COUNT_CLAIMS),
                                                  EXPECTED_DOC_CLAIMS))
    kinds = {kind for _rel, _anchor, kind in DOC_COUNT_CLAIMS}
    if kinds != set(DOC_PIN_NAMES):
        raise CannotRun("the live-claim table grades %s but not %s — a suite whose pin "
                        "no doc row is compared against would silently leave the "
                        "compare" % (", ".join(sorted(kinds)),
                                     ", ".join(sorted(set(DOC_PIN_NAMES) - kinds))))
    pins = gate_pins()
    docs = sorted({rel for rel, _a, _k in DOC_COUNT_CLAIMS})
    texts = {}
    for rel in docs:
        texts[rel] = read(rel)
    graded = []
    findings = []
    for rel, anchor, kind in DOC_COUNT_CLAIMS:
        lines = texts[rel].split("\n")
        hits = [n for n, ln in enumerate(lines, 1) if anchor in ln]
        if len(hits) != 1:
            raise CannotRun("anchor %r matched %d line(s) in %s — this leg reads a "
                            "particular sentence, and an anchor that no longer names "
                            "exactly one of them has no claim to grade"
                            % (anchor, len(hits), rel))
        at = hits[0]
        nums = {num for num, k in doc_nums(lines[at - 1]) if k == kind}
        if not nums:
            findings.append("%s:%d still carries the anchor but states no %s count — "
                            "the live claim left the compare, so a reader follows an "
                            "instruction with the number missing" % (rel, at, kind))
            continue
        if len(nums) > 1:
            findings.append("%s:%d states two %s counts (%s) in the one sentence a "
                            "reader must follow — nothing here can say which is the "
                            "live claim" % (rel, at, kind,
                                            ", ".join(str(x) for x in sorted(nums))))
            continue
        stated = nums.pop()
        graded.append((rel, at, kind))
        owe = pins[DOC_PIN_NAMES[kind]]
        if stated != owe:
            why = ("the doc is stale: it was not bumped when the pin moved"
                   if stated < owe else
                   "the doc is ahead of the gate: the pin was never bumped to match")
            findings.append("%s:%d says `%d %s`, the gate owes %d — %s. Bump the doc, "
                            "the pin and every report citing them in the SAME commit "
                            "as the diff that changes the suite"
                            % (rel, at, stated, kind, owe, why))
    table = {(rel, at, kind) for rel, at, kind in graded}
    ungraded = []
    for rel in docs:
        for header in DOC_LIVE_SECTIONS:
            lo, hi = section_span(texts[rel], header, rel)
            for (at, num, kind) in section_claims(texts[rel], lo, hi):
                if (rel, at, kind) not in table:
                    ungraded.append("%s:%d `%d %s`" % (rel, at, num, kind))
    if ungraded:
        findings.append("live count claim(s) inside the graded sections that the table "
                        "does not read: %s — a number a reader follows and no compare "
                        "grades is the drift this leg exists for, so add the row, or "
                        "move the sentence out of ## Layout / ## Commands if it is a "
                        "historical record" % ", ".join(sorted(set(ungraded))))
    if findings:
        raise LegRed("; ".join(findings))
    log("doc-counts %d live claim(s) over %d doc(s) equal the gate's own pins (%s); "
        "%d claim(s) scanned inside %s, none ungraded, no number re-spelled in this "
        "harness"
        % (len(graded), len(docs),
           ", ".join("%s=%d" % (k, pins[DOC_PIN_NAMES[k]]) for k in sorted(DOC_PIN_NAMES)),
           len(graded) + len(ungraded), " and ".join(DOC_LIVE_SECTIONS)))


def control_roster(harness_rel):
    """One harness's own control truth, read THREE ways and never re-spelled here.

    Returns (EXPECTED_CONTROLS literal, len(CONTROLS) from its AST, is the pin
    actually compared inside that harness).
    """
    src = read(harness_rel)
    m = CONTROL_PIN_ASSIGN.search(src)
    if not m:
        raise CannotRun("%s publishes no `EXPECTED_CONTROLS = <int>` literal — the doc "
                        "quotes a control count that the harness itself never pins, so "
                        "there is nothing here to compare it against. Add the pin AND the "
                        "`len(CONTROLS) != EXPECTED_CONTROLS` guard at the top of its "
                        "selftest, like the other harnesses in this family" % harness_rel)
    pin = int(m.group(1))
    try:
        tree = ast.parse(src, filename=harness_rel)
    except SyntaxError as exc:
        raise CannotRun("%s does not parse (line %s: %s) — its roster cannot be counted"
                        % (harness_rel, exc.lineno, exc.msg))
    roster = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "CONTROLS" for t in node.targets):
            if not isinstance(node.value, (ast.Tuple, ast.List)):
                raise CannotRun("%s: CONTROLS is not a literal roster, so its length is "
                                "computed — the number `SELFTEST OK` prints is then not "
                                "the number the doc could quote" % harness_rel)
            roster = len(node.value.elts)
    if roster is None:
        raise CannotRun("%s has a control pin but no module-level CONTROLS roster — the "
                        "pin grades nothing" % harness_rel)
    return pin, roster, (CONTROL_PIN_ASSERTED in src)


def leg_control_counts(log):
    """A control count a reader follows must equal the roster that produces it.

    Measured before this leg existed: the AGENTS.md `## Commands` block published
    `12 controls` for scripts/chat_feature_check.py, which carried no
    `EXPECTED_CONTROLS` at all — delete a control there, `SELFTEST OK` prints 11, and
    nothing in the tree notices, while the doc still instructs 12. The suite counts got
    this treatment in the leg above; the roster counts are the same class and were the
    remaining published-but-ungraded number.
    """
    claims = []
    for rel in CONTROL_DOCS:
        text = read(rel)
        for header in CONTROL_SECTIONS:
            lo, hi = section_span(text, header, rel)
            lines = text.split("\n")
            for n in range(lo, hi + 1):
                line = lines[n - 1]
                for m in CONTROL_NUM.finditer(line):
                    harnesses = CONTROL_TOKEN.findall(line)
                    if not harnesses:
                        raise CannotRun("%s:%d states `%s controls` on a line that names "
                                        "no scripts/*.py — the number has no harness to be "
                                        "graded against, and guessing the nearest one above "
                                        "or below would invent a verdict"
                                        % (rel, n, m.group(1)))
                    if len(harnesses) > 1:
                        raise CannotRun("%s:%d names %d harness(es) on the one line that "
                                        "states `%s controls` — the leg cannot say which "
                                        "roster the number claims"
                                        % (rel, n, len(harnesses), m.group(1)))
                    claims.append((rel, n, int(m.group(1)), harnesses[0]))
    if len(claims) != EXPECTED_CONTROL_CLAIMS:
        raise CannotRun("the live sections carry %d control claim(s), the pin says %d — a "
                        "claim moved out of %s (or was added) and the compare now covers a "
                        "different population than it claims; bump "
                        "EXPECTED_CONTROL_CLAIMS in the SAME commit as the deliberate "
                        "change" % (len(claims), EXPECTED_CONTROL_CLAIMS,
                                    " / ".join(CONTROL_SECTIONS)))
    findings = []
    by_harness = {}
    structural = set()
    for rel, at, stated, harness in claims:
        harness_rel = "scripts/%s" % harness
        if harness_rel not in by_harness:
            by_harness[harness_rel] = control_roster(harness_rel)
        pin, roster, asserted = by_harness[harness_rel]
        if harness_rel not in structural:
            structural.add(harness_rel)
            if not asserted:
                findings.append("%s: `EXPECTED_CONTROLS = %d` is never compared against "
                                "`len(CONTROLS)` in the harness, so the pin is a second "
                                "number nothing reads and a vanished roster entry stays "
                                "invisible" % (harness_rel, pin))
            if pin != roster:
                findings.append("%s pins %d control(s) but its CONTROLS roster holds %d — "
                                "the harness's own selftest refuses to run, so the count it "
                                "prints and the count the docs quote cannot both be true"
                                % (harness_rel, pin, roster))
        if stated != pin:
            why = ("the doc is stale: a control was added without the doc"
                   if stated < pin else
                   "the doc is ahead of the harness: a control left the roster without the "
                   "pin")
            findings.append("%s:%d says `%d controls`, %s pins %d — %s. Bump the doc, the "
                            "pin and the roster in the SAME commit as the control"
                            % (rel, at, stated, harness_rel, pin, why))
    if findings:
        raise LegRed("; ".join(findings))
    log("controls  %d live claim(s) over %d harness(es) equal each harness's own pin "
        "(%s), every pin compared against its roster, population pinned against a literal "
        "of %d, no number re-spelled in this harness"
        % (len(claims), len(by_harness),
           ", ".join("%s=%d" % (h, p) for h, (p, _r, _a) in sorted(by_harness.items())),
           EXPECTED_CONTROL_CLAIMS))


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
            (leg_citation_targets, (log,)), (leg_doc_counts, (log,)),
            (leg_control_counts, (log,)),
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
    print("RELEASE READINESS GREEN — carriers, tag, citations (paths, line "
          "numbers and targets), doc-quoted suite counts, doc-quoted control "
          "rosters, harness grammar and release inputs each asserted their own "
          "fact")
    return GREEN


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # a crash is not a verdict: 2, never 1
        print("CANNOT RUN — harness failure %s: %s" % (type(exc).__name__, exc))
        sys.exit(CANNOT)
